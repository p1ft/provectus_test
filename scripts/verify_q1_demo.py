"""Capture the authorized Q1 draft/correction or replay its isolated review lifecycle."""

import argparse
import json
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
from scripts.verify_reference_cases import matches_question
from workspace.gemini import (
    REAL_REPLAY_DIRECTORY,
    REAL_REPLAY_MODEL,
    FileReplayTransport,
    Gemini,
    LiveTransport,
)
from workspace.schemas import Draft
from workspace.service import Service
from workspace.store import Store, now

CORRECTION_TEXT = "Free-plan users cannot export CSV; CSV export is available on paid plans only."
CORRECTION_FILE = ROOT / "examples/q1-correction.json"


def draft_and_correction(service, correction=None):
    revision = service.generate("Q1")
    if revision is None:
        return [{"case": "Q1", "result": "fail", "error": service.store.question("Q1")["last_error"]}], None
    record = service.store.revision(revision)
    validation = service.store.one("SELECT * FROM answer_validations WHERE answer_revision=? ORDER BY id DESC LIMIT 1",
                                   (revision,))
    definition = {"id": "Q1", "source": "EXPORT-v2:p1", "show_conflict_with": "EXPORT-v1:p1"}
    findings = json.loads(validation["errors"])
    passed = matches_question(definition, service.store.question("Q1"), record) and not findings
    rows = [{"case": "Q1", "result": "pass" if passed else "fail", "findings": findings,
             "draft": record["draft"].model_dump(mode="json")}]
    if not passed:
        return rows, None
    correction = Draft.model_validate(correction or {**record["draft"].model_dump(), "answer": CORRECTION_TEXT})
    if correction.question_id != "Q1" or correction.answer == record["draft"].answer:
        raise ValueError("Q1 demonstration requires different reviewer wording")
    edited = service.edit("Q1", correction, note="Local demonstration wording correction")
    errors = service.validate(edited)
    rows.append({"case": "corrected-wording-check", "result": "fail" if errors else "pass", "findings": errors,
                 "answer": correction.answer, "revision_id": edited})
    return rows, correction


def lifecycle(service, correction, rows):
    store = service.store
    revision = rows[-1]["revision_id"]
    exact = store.question("Q1")["text"]

    def record(case, passed):
        rows.append({"case": case, "result": "pass" if passed else "fail"})

    record("unapproved-correction-excluded", not service.reuse(exact)["eligible"])
    service.approve(revision, reviewer_name="Q1 replay demonstration reviewer", reviewer_role="Product reviewer",
                    evidence_confirmed=True, note="Isolated demonstration approval; not a working approval")
    expected = service.reuse(exact)
    record("approval-reuse", expected["eligible"] and expected["answer"] == correction.answer
           and bool(expected["approval"]) and bool(expected["evidence"]))
    service.edit("Q1", {**correction.model_dump(), "answer": "Unapproved demonstration edit awaiting review."})
    record("unapproved-edit-excluded", service.reuse(exact) == expected)
    record("novel-edit-replay-miss", service.validate(store.question("Q1")["working_revision"]) == ["No exact replay match"])
    reopened = Store(store.db.execute("PRAGMA database_list").fetchone()[2])
    try:
        record("reload", Service(reopened, service.gemini).reuse(exact) == expected)
    finally:
        reopened.close()
    evidence = store.revision(revision)["citations"]
    document = next(d for d in store.snapshot()["documents"] if d["id"] == "EXPORT-v2")
    store.update_source({**document, "version": document["version"] + 1})
    record("source-change", store.question("Q1")["status"] == "review_required"
           and not service.reuse(exact)["eligible"] and store.revision(revision)["citations"] == evidence)
    store.remove_source("EXPORT-v2")
    record("source-removal", not service.reuse(exact)["eligible"] and store.revision(revision)["citations"] == evidence)


def verify(output, *, live=False, captures=ROOT / REAL_REPLAY_DIRECTORY, correction_path=CORRECTION_FILE):
    output = Path(output).resolve()
    if not any(output.is_relative_to(ROOT / p) for p in (".tmp", "artifacts/verification")):
        raise ValueError("Q1 verification requires an isolated output directory")
    output.mkdir(parents=True, exist_ok=True)
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    session = uuid4().hex
    captures = ROOT / "artifacts/real-runs" / session if live else Path(captures)
    report = {"generated_at": now(), "model": REAL_REPLAY_MODEL, "capture_directory": str(captures),
              "working_database_touched": False, "live_rows": [], "replay_rows": [],
              "provenance": "Authorized Q1 real draft/check and correction check" if live else "Saved real Q1 replay only"}
    correction = None
    live_store = None
    try:
        if live:
            local_configuration()
            live_store = Store(output / f"q1-live-{session}.sqlite3")
            live_store.import_seed(seed)
            question = next(q for q in seed["questions"] if q["id"] == "Q1")
            engine = Gemini(live_store, ApprovedSeedTransport([question], live_store.snapshot()),
                            model=REAL_REPLAY_MODEL, capture_dir=captures)
            (output / f"q1-request-{session}.json").write_text(
                json.dumps(engine.request("draft", question, live_store.snapshot()), indent=2), encoding="utf-8")
            report["live_rows"], correction = draft_and_correction(Service(live_store, engine))
            report["generation_requests"] = len(live_store.rows("SELECT * FROM model_runs"))
            if correction is not None:
                correction_path = output / f"q1-correction-{session}.json"
                correction_path.write_text(correction.model_dump_json(indent=2), encoding="utf-8")
        else:
            correction = Draft.model_validate_json(Path(correction_path).read_text(encoding="utf-8"))
        if correction is not None:
            store = Store(output / f"q1-replay-{session}.sqlite3")
            store.import_seed(seed)
            try:
                service = Service(store, Gemini(store, FileReplayTransport(captures), model=REAL_REPLAY_MODEL))
                with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
                    LiveTransport, "send", side_effect=AssertionError("Replay attempted a live call")
                ):
                    rows, replay_correction = draft_and_correction(service, correction)
                    if all(row["result"] == "pass" for row in rows):
                        lifecycle(service, replay_correction, rows)
                exact = replay_correction == correction and (not live or rows[0].get("draft") == report["live_rows"][0].get("draft"))
                report.update(replay_rows=rows, replay_matches_live=exact,
                              replay_credential_access="prohibited and not used", replay_network_fallback="prohibited and not used")
            finally:
                store.close()
        report["correction_file"] = str(correction_path)
        phases = [report["replay_rows"], *([report["live_rows"]] if live else [])]
        report["result"] = "pass" if report.get("replay_matches_live") is True and all(
            rows and all(row["result"] == "pass" for row in rows) for rows in phases) else "fail"
        path = output / f"q1-results-{session}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["result_file"] = str(path)
        return report
    finally:
        if live_store is not None:
            live_store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification/q1-demo")
    parser.add_argument("--live", action="store_true", help="Make up to three authorized real Q1 requests")
    parser.add_argument("--captures", type=Path, default=ROOT / REAL_REPLAY_DIRECTORY)
    parser.add_argument("--correction", type=Path, default=CORRECTION_FILE)
    args = parser.parse_args()
    result = verify(args.output, live=args.live, captures=args.captures, correction_path=args.correction)
    print(json.dumps(result, indent=2))
    raise SystemExit(result["result"] != "pass")
