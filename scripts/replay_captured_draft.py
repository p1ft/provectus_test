"""Replay an archived real draft request exactly, without credentials or network access."""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_live import ForbiddenEnvironment
from workspace.evidence import reference_errors
from workspace.gemini import FileReplayTransport, Gemini, LiveTransport
from workspace.schemas import CapturedRun, Draft
from workspace.store import Store


def replay(path):
    path = Path(path)
    captured = CapturedRun.model_validate_json(path.read_text(encoding="utf-8"))
    if captured.origin != "live" or captured.purpose != "draft" or captured.error:
        raise ValueError("A successful real draft capture is required")
    if captured.request["schema"] != Draft.model_json_schema():
        raise ValueError("Captured local output contract does not match the shared Draft contract")
    store = Store(":memory:")
    store.import_seed(json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8")))
    snapshot = store.snapshot()
    if captured.request["source_snapshot"] != {k: snapshot[k] for k in ("documents", "availability", "fingerprint")}:
        raise ValueError("Captured sources do not match current original seed sources")
    engine = Gemini(store, FileReplayTransport(path.parent), model=captured.request["model"])
    try:
        with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
            LiveTransport, "send", side_effect=AssertionError("Replay attempted network fallback")
        ), patch.object(engine, "request", return_value=captured.request):
            # Reconstruct the archived request exactly. Native wire constraints have changed,
            # while the shared local Draft contract remains identical to this capture.
            draft, run_id = engine.run("draft", captured.request["question"], snapshot)
        errors = reference_errors(draft, captured.question_id, snapshot)
        return {"case": captured.question_id, "result": "pass" if not errors else "fail",
                "scope": "real draft transport, strict Pydantic parsing and citation/authority checks only",
                "answer": draft.answer, "findings": errors, "original_run_id": captured.id,
                "replay_run_id": run_id, "capture_file": str(path),
                "credential_access": "prohibited and not used", "network_fallback": "prohibited and not used",
                "semantic_check": "unverified; no successful checker response exists"}
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    result = replay(parser.parse_args().capture)
    print(json.dumps(result, ensure_ascii=False))
