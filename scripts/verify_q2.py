"""User-authorized fresh Q2 draft/check capture and exact credential-free replay."""

import argparse
import json
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
)
from scripts.verify_reference_cases import matches_question
from workspace.evidence import reference_errors
from workspace.gemini import (
    REAL_REPLAY_MODEL,
    FileReplayTransport,
    Gemini,
    LiveTransport,
)
from workspace.service import Service
from workspace.store import Store, now


def inspect(service, question, definition):
    revision = service.generate(question["id"])
    current = service.store.question(question["id"])
    if revision is None:
        return {"case": "Q2", "result": "fail", "error": current["last_error"]}, None
    record = service.store.revision(revision)
    draft = record["draft"]
    findings = [e for e in reference_errors(draft, question["id"], service.store.snapshot())
                if e != draft.unresolved_reason]
    if draft.answer or draft.citations:
        findings.append("Undocumented Q2 must not invent answer wording or cited support")
    checker = inspect_checker(service, question, revision)
    question_passed = matches_question(definition, current, record)
    passed = question_passed and not findings and checker["request_result"] == checker["semantic_result"] == "pass"
    return {"case": "Q2", "result": "pass" if passed else "fail",
            "question_result": "pass" if question_passed else "fail",
            "draft_findings": findings, "checker": checker,
            "observed": {"status": current["status"], "owner": current["reviewer"],
                         "answer": draft.answer, "reason": draft.unresolved_reason},
            "revision_id": revision, "run_ids": [record["draft_run"], checker["run_id"]]}, draft.model_dump(mode="json")


def verify(output):
    output = Path(output).resolve()
    if not any(output.is_relative_to(ROOT / p) for p in (".tmp", "artifacts/verification")):
        raise ValueError("Q2 verification requires isolated output under .tmp or artifacts/verification")
    output.mkdir(parents=True, exist_ok=True)
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    question = next(q for q in seed["questions"] if q["id"] == "Q2")
    definition = next(c for c in json.loads((ROOT / "tasks/evidence/expected-seed-results.json").read_text()) if c["id"] == "Q2")
    session = uuid4().hex
    captures = ROOT / "artifacts/real-runs" / session
    database = output / f"q2-live-{session}.sqlite3"
    store = Store(database)
    store.import_seed(seed)
    engine = Gemini(store, ApprovedSeedTransport([question], store.snapshot()),
                    model=REAL_REPLAY_MODEL, capture_dir=captures)
    # Concrete outbound draft request contains only the original fictional question/corpus.
    (output / f"q2-request-{session}.json").write_text(
        json.dumps(engine.request("draft", question, store.snapshot()), indent=2), encoding="utf-8")
    report = {"generated_at": now(), "model": REAL_REPLAY_MODEL, "database": str(database),
              "capture_directory": str(captures), "provenance": "Fresh user-authorized Q2-only real draft/check",
              "working_database_touched": False, "human_approvals": 0, "live_rows": [], "replay_rows": []}
    try:
        try:
            local_configuration()
        except ValueError as exc:
            report["blocker"] = str(exc)
        else:
            row, draft = inspect(Service(store, engine), question, definition)
            report["live_rows"] = [row]
            report["generation_requests"] = len(store.rows("SELECT * FROM model_runs"))
            report["runs"] = [{k: r[k] for k in ("id", "question_id", "purpose", "origin", "error")}
                              for r in store.rows("SELECT * FROM model_runs ORDER BY id")]
            replay_store = Store(output / f"q2-replay-{session}.sqlite3")
            replay_store.import_seed(seed)
            try:
                replay = Service(replay_store, Gemini(replay_store, FileReplayTransport(captures),
                                                       model=REAL_REPLAY_MODEL))
                with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
                    LiveTransport, "send", side_effect=AssertionError("Replay attempted a live call")
                ):
                    replay_row, replay_draft = inspect(replay, question, definition)
                report.update(replay_rows=[replay_row], replay_matches_live=draft is not None and draft == replay_draft,
                              replay_credential_access="prohibited and not used",
                              replay_network_fallback="prohibited and not used")
            finally:
                replay_store.close()
        report["result"] = "fail" if verification_failed(report) else "pass"
        path = output / f"q2-results-{session}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        report["result_file"] = str(path)
        return report
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification/q2-fix")
    args = parser.parse_args()
    result = verify(args.output)
    print(json.dumps({k: result.get(k) for k in ("result", "blocker", "model", "generation_requests", "live_rows", "replay_rows", "replay_matches_live", "result_file")}, indent=2))
    raise SystemExit(result["result"] != "pass")
