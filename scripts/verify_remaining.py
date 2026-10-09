"""Authorized real Q2–Q8 verification with isolated review and credential-free replay."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verification_results import inspect_checker, verification_failed
from scripts.verify_live import (
    ApprovedSeedTransport,
    ForbiddenEnvironment,
    local_configuration,
    verification_approval,
)
from scripts.verify_reference_cases import matches_question
from workspace.gemini import FileReplayTransport, Gemini, LiveTransport
from workspace.service import Service
from workspace.store import Store, now

QUESTION_IDS = [f"Q{i}" for i in range(2, 9)]


def inspect(service, definitions):
    rows = []
    drafts = {}
    for question_id in QUESTION_IDS:
        q = service.store.question(question_id)
        question = {k: q[k] for k in ("id", "topic", "text")}
        revision = service.generate(question_id)
        current = service.store.question(question_id)
        if revision is None:
            rows.append({"case": question_id, "result": "fail", "observed": {"error": current["last_error"]}})
            print(f"{question_id}: generation failed: {current['last_error']}", flush=True)
            continue
        record = service.store.revision(revision)
        draft = record["draft"]
        drafts[question_id] = draft.model_dump(mode="json")
        checker = inspect_checker(service, question, revision)
        observed = {"answer": draft.answer, "disposition": draft.disposition, "status": current["status"],
                    "owner": current["reviewer"], "unresolved_reason": draft.unresolved_reason,
                    "passages": [c["passage_id"] for c in record["citations"]], "checker_findings": checker["findings"]}
        question_passed = matches_question(definitions[question_id], current, record)
        passed = question_passed and checker["request_result"] == checker["semantic_result"] == "pass"
        rows.append({"case": question_id, "result": "pass" if passed else "fail", "observed": observed,
                     "question_result": "pass" if question_passed else "fail", "checker": checker,
                     "revision_id": revision, "run_ids": [record["draft_run"], checker["run_id"]]})
        if current["status"] == "answered":
            verification_approval(service, revision)
        else:
            service.leave_unresolved(question_id, "Local verification disposition: unsupported or undocumented wording remains unresolved.")
        print(f"{question_id}: {rows[-1]['result']} / {current['status']} / {draft.answer or draft.unresolved_reason}", flush=True)
    return rows, drafts


def verify():
    local_configuration()
    model = "gemini-3.1-flash-lite"
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    supplied = json.loads((ROOT / "tasks/evidence/expected-seed-results.json").read_text(encoding="utf-8"))
    independent = json.loads((ROOT / "tests/reference-cases.json").read_text(encoding="utf-8"))["cases"]
    definitions = {c["id"]: {**c, "origin": "Supplied expected-seed-results.json"} for c in supplied}
    definitions.update({c["id"]: c for c in independent})
    session = uuid4().hex
    output = ROOT / "artifacts/verification"
    output.mkdir(parents=True, exist_ok=True)
    database = output / f"q2-q8-live-{session}.sqlite3"
    capture_dir = ROOT / "artifacts/real-runs" / session
    store = Store(database)
    store.import_seed(seed)
    result = {"generated_at": now(), "model": model, "database": str(database),
              "capture_directory": str(capture_dir), "provenance": "real Gemini Q2–Q8 verification",
              "settings": {"temperature": 0, "max_output_tokens": 8192, "timeout_ms": 30000},
              "working_database_touched": False}
    try:
        service = Service(store, Gemini(store, ApprovedSeedTransport(seed["questions"], store.snapshot()),
                                       model=model, capture_dir=capture_dir))
        rows, live_drafts = inspect(service, definitions)
        result["live_rows"] = rows
        result["generation_requests"] = len(store.rows("SELECT * FROM model_runs"))
        result["provider_model_versions"] = sorted({json.loads(r["metadata"])["model_version"]
                                                   for r in store.rows("SELECT metadata FROM model_runs")
                                                   if json.loads(r["metadata"]).get("model_version")})
        replay_store = Store(output / f"q2-q8-replay-{session}.sqlite3")
        replay_store.import_seed(seed)
        replay_service = Service(replay_store, Gemini(replay_store, FileReplayTransport(capture_dir), model=model))
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        try:
            with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
                LiveTransport, "send", side_effect=AssertionError("Replay attempted a live call")
            ):
                replay_rows, replay_drafts = inspect(replay_service, definitions)
            result.update(replay_rows=replay_rows, replay_matches_live=live_drafts == replay_drafts,
                          replay_credential_access="prohibited and not used", replay_network_fallback="prohibited and not used")
        finally:
            replay_store.close()
        (output / "q2-q8-results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return result
    finally:
        store.close()


if __name__ == "__main__":
    result = verify()
    print(json.dumps({"model": result["model"], "replay_matches_live": result["replay_matches_live"],
                      "generation_requests": result["generation_requests"],
                      "live_results": {r["case"]: r["result"] for r in result["live_rows"]}}, indent=2))
    sys.exit(verification_failed(result))
