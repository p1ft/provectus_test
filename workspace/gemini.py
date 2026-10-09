"""Direct Gemini transport, raw capture, and offline exact-request replay."""

import json
import os
import re
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from google import genai
from google.genai import types
from google.genai.errors import APIError
from httpx import HTTPError
from pydantic import ValidationError

from workspace.prompts import (
    CHECK_PROMPT,
    DRAFT_PROMPT,
    EMPTY_ANSWER_CHECK_PROMPT,
    RULES,
    request_prompt,
)
from workspace.schemas import (
    CapturedRun,
    Draft,
    Response,
    SemanticCheck,
    fingerprint,
    json_text,
)

__all__ = [
    "API_BASE_URL",
    "API_VERSION",
    "CHECK_PROMPT",
    "DRAFT_PROMPT",
    "EMPTY_ANSWER_CHECK_PROMPT",
    "REAL_REPLAY_DIRECTORY",
    "REAL_REPLAY_MODEL",
    "RULES",
    "FileReplayTransport",
    "Gemini",
    "LiveTransport",
    "ModelFailure",
    "ReplayMiss",
    "ReplayTransport",
    "Response",
    "capture_bundle",
    "request_prompt",
    "wire_schema",
]

API_BASE_URL = "https://generativelanguage.googleapis.com"
API_VERSION = "v1beta"
REAL_REPLAY_MODEL = "gemini-3.1-flash-lite"
REAL_REPLAY_DIRECTORY = "examples/real-replay"

class ModelFailure(RuntimeError):
    def __init__(self, message, run_id):
        super().__init__(message)
        self.run_id = run_id


class ReplayMiss(RuntimeError):
    pass


def wire_schema(contract):
    """Derive a small native schema; validation constraints remain in the shared Pydantic contract."""
    local_constraints = {"additionalProperties", "pattern", "minLength", "maxLength",
                         "minItems", "maxItems", "minimum", "maximum"}
    def supported(value):
        if isinstance(value, dict):
            return {key: supported(item) for key, item in value.items() if key not in local_constraints}
        if isinstance(value, list):
            return [supported(item) for item in value]
        return value

    return supported(contract.model_json_schema())


class LiveTransport:
    origin = "live"

    def send(self, request, contract):
        # Credential access and client creation happen only on explicit live invocation.
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Missing Gemini configuration")
        with genai.Client(api_key=key, enterprise=False, http_options=types.HttpOptions(
            base_url=API_BASE_URL, api_version=API_VERSION,
            timeout=request["timeout_ms"], retry_options=types.HttpRetryOptions(attempts=1)
        )) as client:
            response = client.models.generate_content(
                model=request["model"],
                contents=[types.Content(role="user", parts=[
                    types.Part.from_text(text=part) for part in request["contents"]
                ])],
                config=types.GenerateContentConfig(
                    system_instruction=request["system_instruction"],
                    response_schema=wire_schema(contract), response_mime_type="application/json",
                    **request["settings"]
                ),
            )
            return Response(response.text or "", {
                "response_id": response.response_id,
                "model_version": response.model_version,
                "usage": response.usage_metadata.model_dump(mode="json")
                if response.usage_metadata else None,
                "finish_reasons": [str(c.finish_reason) for c in response.candidates or []],
            })


class ReplayTransport:
    """Replay captured real runs by default. Test replay must opt in to synthetic origin."""

    def __init__(self, capture_store, *, synthetic=False):
        self.store = capture_store
        self.source_origin = "synthetic" if synthetic else "live"
        self.origin = "replay_synthetic" if synthetic else "replay_real"

    def send(self, request, contract):
        run = self.store.one(
            "SELECT * FROM model_runs WHERE request_fingerprint=? AND origin=? "
            "AND error IS NULL ORDER BY id DESC LIMIT 1",
            (fingerprint(request), self.source_origin),
        )
        if run is None or json.loads(run["request"]) != request:
            raise ReplayMiss("No exact captured request; replay cannot call the API")
        return Response(run["raw_response"], json.loads(run["metadata"]), run["id"])


def capture_bundle(store, run_id):
    bundle = store.one("SELECT * FROM model_runs WHERE id=?", (run_id,))
    bundle["request"] = json.loads(bundle["request"])
    bundle["metadata"] = json.loads(bundle["metadata"])
    return CapturedRun.model_validate(bundle)


class FileReplayTransport:
    def __init__(self, directory, *, synthetic=False):
        self.directory = Path(directory)
        self.source_origin = "synthetic" if synthetic else "live"
        self.origin = "replay_synthetic" if synthetic else "replay_real"

    def send(self, request, contract):
        for path in sorted(self.directory.glob("*.json")):
            try:
                run = CapturedRun.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValidationError, OSError, UnicodeError):
                continue  # An invalid bundle cannot satisfy a replay request.
            if (run.origin == self.source_origin and run.error is None
                    and run.raw_response is not None and run.request == request):
                return Response(run.raw_response, {**run.metadata, "capture_file": path.name}, run.id)
        raise ReplayMiss("No exact captured request; replay cannot call the API")


class Gemini:
    def __init__(self, store, transport, *, model="gemini-3.8-flash",
                 capture_dir="artifacts/real-runs"):
        self.store = store
        self.transport = transport
        self.model = model
        self.capture_dir = Path(capture_dir)

    def request(self, purpose, question, snapshot, draft=None):
        contract = Draft if purpose == "draft" else SemanticCheck
        source_data = {k: snapshot[k] for k in ("documents", "availability", "fingerprint")}
        parts = [json_text({"question": question}), json_text({"source_snapshot": source_data})]
        if draft is not None:
            parts.append(json_text({"proposed_answer": draft.model_dump(mode="json")}))
        return {
            "purpose": purpose, "question": question, "source_snapshot": source_data,
            "contents": parts, "system_instruction": request_prompt(purpose, draft),
            "schema": contract.model_json_schema(),
            "model": self.model, "settings": {"temperature": 0, "max_output_tokens": 8192},
            "destination": f"{API_BASE_URL}/{API_VERSION}/models/{self.model}:generateContent",
            "api_version": API_VERSION,
            "structured_output": "response_schema",
            "wire_schema": wire_schema(contract),
            "timeout_ms": 30000, "sdk_version": version("google-genai"),
        }

    def run(self, purpose, question, snapshot, draft=None):
        contract = Draft if purpose == "draft" else SemanticCheck
        request = self.request(purpose, question, snapshot, draft)
        try:
            response = self.transport.send(request, contract)
        except (APIError, HTTPError, OSError, RuntimeError, ValueError) as exc:
            # Provider exception strings can include URLs, keys, headers, and payloads.
            error = "No exact replay match" if isinstance(exc, ReplayMiss) else (
                f"Gemini request failed ({type(exc).__name__}); retry explicitly"
            )
            if isinstance(exc, APIError):
                statuses = {"INVALID_ARGUMENT", "FAILED_PRECONDITION", "UNAUTHENTICATED",
                            "PERMISSION_DENIED", "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL",
                            "UNAVAILABLE", "DEADLINE_EXCEEDED", "UNKNOWN", "ABORTED"}
                status = exc.status if exc.status in statuses else "UNKNOWN"
                code = exc.code if isinstance(exc.code, int) and 100 <= exc.code <= 599 else "unknown"
                error = f"Gemini provider rejected request: HTTP {code} / {status}; retry explicitly"
                message = exc.message if isinstance(exc.message, str) else ""
                for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                    secret = os.environ.get(name)
                    if secret:
                        message = message.replace(secret, "[REDACTED]")
                message = re.sub(r"AIza[A-Za-z0-9_-]+", "[REDACTED]", message)
                message = re.sub(r"(?i)(authorization|x-goog-api-key|api_key|key)\s*[:=]\s*[^\s,}]+",
                                 r"\1=[REDACTED]", message)
                if message:
                    error += ": " + message[:1000]
            run_id = self.store.record_run(request, None, error, self.transport.origin, {})
            if self.transport.origin == "live":
                self._capture(run_id)
            raise ModelFailure(error, run_id) from None
        run_id = self.store.record_run(request, response.raw, None, self.transport.origin,
                                       response.metadata, response.original_run)
        if self.transport.origin == "live":
            self._capture(run_id)
        try:
            return contract.model_validate_json(response.raw), run_id
        except ValidationError as exc:
            errors = [f"{'.'.join(map(str, e['loc'])) or 'response'}: {e['type']}"
                      for e in exc.errors(include_input=False, include_url=False)]
            raise ModelFailure("Invalid Gemini output: " + "; ".join(errors), run_id) from None

    def _capture(self, run_id):
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        bundle = capture_bundle(self.store, run_id)
        (self.capture_dir / f"run-{run_id}-{uuid4().hex}.json").write_text(
            bundle.model_dump_json(), encoding="utf-8")
