"""Save the exact outbound payload specification locally; never initialize a model client."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workspace.gemini import Gemini
from workspace.prompts import CHECK_PROMPT
from workspace.schemas import Draft, SemanticCheck, fingerprint
from workspace.store import Store


def prepare(output):
    store = Store(":memory:")
    store.import_seed(json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8")))
    try:
        engine = Gemini(store, None)
        requests = [engine.request("draft", {k: q[k] for k in ("id", "topic", "text")}, store.snapshot())
                    for q in store.rows("SELECT * FROM questions ORDER BY id")]
        proposal = {
            "status": "Pending explicit user approval; no credentials accessed and no requests sent",
            "destination": requests[0]["destination"],
            "transport": "Official google-genai SDK over HTTPS; synchronous generate_content",
            "payload_scope": "Eight supplied question texts/topics and the complete five-document corpus, "
                             "including passage text, IDs, versions, dates, status, supersedes and availability",
            "draft_requests": requests,
            "semantic_check": {
                "system_instruction": CHECK_PROMPT, "schema": SemanticCheck.model_json_schema(),
                "contents": "The same question and full source corpus, plus the exact generated answer, "
                            "citations, unresolved reason and conflict labels. Generated content is unknown "
                            "until drafting; no generated answer is represented as known here.",
                "model": requests[0]["model"], "settings": requests[0]["settings"],
                "timeout_ms": requests[0]["timeout_ms"], "calls": "Up to eight checks after supported drafts",
            },
            "reviewer_edit_check": "An optional follow-up check sends the exact reviewer-edited answer "
                                  "and citations with the same source corpus; it needs approval for that payload.",
            "schema_contracts": {"draft": Draft.model_json_schema(), "check": SemanticCheck.model_json_schema()},
            "credential_handling": "Read GEMINI_API_KEY only when an approved live action is invoked; "
                                   "the key is sent as SDK authentication and never written to captures.",
        }
        proposal["review_fingerprint"] = fingerprint(proposal)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
        markdown = output.with_suffix(".md")
        markdown.write_text(
            "# Pending Gemini request approval\n\nNo requests have been sent. No credentials have been accessed.\n\n"
            f"Destination: `{proposal['destination']}`.\n\n"
            "Eight draft calls would send all eight supplied question texts and all five source documents, "
            "including replaced EXPORT text. Up to eight checker calls would additionally send the generated "
            "answer and citations. Edited wording requires a separate exact-payload check.\n\n"
            "The JSON companion contains every initial question/source value, both prompts, shared Pydantic "
            "schemas, SDK version, model, temperature (0), output limit (8192), and timeout (30000 ms). "
            "Native JSON structured output is used. Generated answers do not yet exist and are described "
            "as future checker content rather than fabricated.\n\n"
            f"Review fingerprint: `{proposal['review_fingerprint']}`.\n", encoding="utf-8")
        return output
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification/pending-live-request.json")
    print(prepare(parser.parse_args().output))
