"""One explicitly authorized checker test, followed by credential-free exact replay."""

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_live import (
    ApprovedSeedTransport,
    ForbiddenEnvironment,
    local_configuration,
)
from workspace.evidence import reference_errors, semantic_errors
from workspace.gemini import FileReplayTransport, Gemini, LiveTransport, ModelFailure
from workspace.schemas import CapturedRun, Draft
from workspace.store import Store, now


def test_checker(model, capture):
    local_configuration()
    captured = CapturedRun.model_validate_json(Path(capture).read_text(encoding="utf-8"))
    if captured.origin != "live" or captured.error or captured.purpose != "draft":
        raise ValueError("A successful real draft capture is required")
    draft = Draft.model_validate_json(captured.raw_response)
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    session_id = uuid4().hex
    database = ROOT / f"artifacts/verification/checker-{session_id}.sqlite3"
    capture_dir = ROOT / "artifacts/real-runs" / session_id
    store = Store(database)
    store.import_seed(seed)
    snapshot = store.snapshot()
    question = next(q for q in seed["questions"] if q["id"] == draft.question_id)
    if captured.request["source_snapshot"] != {k: snapshot[k] for k in ("documents", "availability", "fingerprint")}:
        raise ValueError("Captured source content is outside the original approved seed")
    if reference_errors(draft, question["id"], snapshot):
        raise ValueError("Captured draft references are invalid")
    result = {"generated_at": now(), "model": model, "case": question["id"],
              "purpose": "check", "capture_directory": str(capture_dir), "database": str(database),
              "provenance": "real live checker retry explicitly authorized by the user",
              "settings": {"temperature": 0, "max_output_tokens": 8192, "timeout_ms": 30000},
              "working_database_touched": False, "generation_requests": 1}
    try:
        engine = Gemini(store, ApprovedSeedTransport(seed["questions"], snapshot), model=model,
                        capture_dir=capture_dir)
        try:
            check, run_id = engine.run("check", question, snapshot, draft)
        except ModelFailure as exc:
            result.update(result="fail", error=str(exc), run_id=exc.run_id,
                          replay="unverified; no successful checking response")
        else:
            findings = semantic_errors(draft, check, snapshot)
            result.update(result="pass" if not findings else "fail", findings=findings, run_id=run_id,
                          check=check.model_dump(mode="json"))
            replay_store = Store(":memory:")
            replay_store.import_seed(seed)
            replay_engine = Gemini(replay_store, FileReplayTransport(capture_dir), model=model)
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            try:
                with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
                    LiveTransport, "send", side_effect=AssertionError("Replay attempted a live call")
                ):
                    replayed, replay_id = replay_engine.run("check", question, replay_store.snapshot(), draft)
                result.update(replay="pass" if replayed == check else "fail", replay_run_id=replay_id,
                              replay_credential_access="prohibited and not used", replay_network="prohibited and not used")
            finally:
                replay_store.close()
        path = ROOT / f"artifacts/verification/checker-retry-{session_id}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["result_file"] = str(path)
        return result
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--capture", required=True, type=Path)
    args = parser.parse_args()
    result = test_checker(args.model, args.capture)
    print(json.dumps({k: result.get(k) for k in ("model", "result", "error", "findings", "replay", "result_file")}, indent=2))
    sys.exit(result["result"] != "pass")
