"""Explicitly authorized live verification of original seed data, plus credential-free replay."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verification_results import inspect_checker, verification_failed
from scripts.verify_reference_cases import matches_question
from workspace.gemini import (
    FileReplayTransport,
    Gemini,
    LiveTransport,
    wire_schema,
)
from workspace.prompts import request_prompt
from workspace.schemas import Draft, SemanticCheck, fingerprint, json_text
from workspace.service import Service
from workspace.store import Store, now


def local_configuration():
    """Read only known config values; never print, capture, or write credential contents."""
    settings = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip().removeprefix("export ")
            name, separator, value = line.partition("=")
            if separator and name.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL"):
                parts = shlex.split(value, comments=True)
                if len(parts) > 1:
                    raise ValueError(f"Invalid local .env syntax for {name.strip()}")
                settings[name.strip()] = parts[0] if parts else ""
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
           or settings.get("GEMINI_API_KEY") or settings.get("GOOGLE_API_KEY"))
    model = os.environ.get("GEMINI_MODEL") or settings.get("GEMINI_MODEL") or "gemini-3.8-flash"
    if not re.fullmatch(r"gemini-[A-Za-z0-9.-]+", model):
        raise ValueError("Configured Gemini model identifier is invalid")
    if not key:
        raise ValueError("No configured API key found in the process or local .env")
    os.environ["GEMINI_API_KEY"] = key
    return model


class ApprovedSeedTransport(LiveTransport):
    def __init__(self, questions, snapshot):
        self.questions = {q["id"]: q for q in questions}
        self.source_snapshot = {k: snapshot[k] for k in ("documents", "availability", "fingerprint")}

    def send(self, request, contract):
        if (request["question"] != self.questions.get(request["question"]["id"])
                or request["source_snapshot"] != self.source_snapshot
                or not request["destination"].startswith("https://generativelanguage.googleapis.com/v1beta/models/")):
            raise ValueError("Request is outside the approved original seed payload")
        parts = [json_text({"question": request["question"]}),
                 json_text({"source_snapshot": request["source_snapshot"]})]
        draft = None
        if request["purpose"] == "check":
            proposal = json.loads(request["contents"][2])
            if set(proposal) != {"proposed_answer"}:
                raise ValueError("Checker payload contains fields outside the approved scope")
            draft = Draft.model_validate(proposal["proposed_answer"])
            parts.append(json_text({"proposed_answer": draft.model_dump(mode="json")}))
        expected_contract = Draft if request["purpose"] == "draft" else SemanticCheck
        prompt = request_prompt(request["purpose"], draft)
        if (request["contents"] != parts or request["system_instruction"] != prompt
                or request["schema"] != expected_contract.model_json_schema()
                or request["wire_schema"] != wire_schema(expected_contract)):
            raise ValueError("Request contents, prompt or schema is outside the approved application payload")
        return super().send(request, contract)


def verification_approval(service, revision):
    question = service.store.question(service.store.revision(revision)["question_id"])
    return service.approve(revision, reviewer_name="Real-response verification demonstration",
                           reviewer_role=question["reviewer"], evidence_confirmed=True,
                           note="Local verification approval only; not a working-database approval")


def run_scenarios(service, definitions, *, perform_live=False):
    store = service.store
    rows = []
    baseline = {}
    blocker = None
    for question in store.rows("SELECT id,topic,text FROM questions ORDER BY id"):
        question_id = question["id"]
        if blocker:
            rows.append({"case": question_id, "result": "unverified", "reason": blocker})
            continue
        revision = service.generate(question_id)
        current = store.question(question_id)
        if revision is None:
            error = current["last_error"] or "No generated revision"
            rows.append({"case": question_id, "result": "unverified" if error == "No exact replay match"
                         else "fail", "observed": {"error": error}})
            if "request failed" in error or "provider rejected" in error:
                blocker = error
            continue
        record = store.revision(revision)
        draft = record["draft"]
        # Unresolved drafts stop the approval pipeline locally, but this task also requests
        # a real checker response for them. Keep that response distinct from approval eligibility.
        checker = inspect_checker(service, question, revision)
        observed = {"answer": draft.answer, "disposition": draft.disposition, "status": current["status"],
                    "owner": current["reviewer"], "unresolved_reason": draft.unresolved_reason,
                    "passages": [c["passage_id"] for c in record["citations"]], "checker_findings": checker["findings"]}
        question_passed = matches_question(definitions[question_id], current, record)
        passed = question_passed and checker["request_result"] == checker["semantic_result"] == "pass"
        rows.append({"case": question_id, "result": "pass" if passed else "fail", "observed": observed,
                     "question_result": "pass" if question_passed else "fail", "checker": checker,
                     "revision_id": revision, "run_ids": [record["draft_run"], checker["run_id"]]})
        baseline[question_id] = draft.model_dump(mode="json")
        if draft.disposition == "unresolved":
            service.leave_unresolved(question_id, "Verification review: undocumented facts need the mapped reviewer.")
        elif current["status"] == "answered":
            verification_approval(service, revision)
        print(f"{('Live' if perform_live else 'Replay')} {question_id}: {rows[-1]['result']} / {current['status']}", flush=True)
    if blocker or "Q1" not in baseline or store.question("Q1")["active_approval"] is None:
        for case in ("approval-reuse", "unapproved-edit", "reload", "source-change", "source-removal", "replay-miss"):
            rows.append({"case": case, "result": "unverified", "reason": blocker or "Q1 did not pass validation"})
        return rows, baseline, blocker
    correction = dict(baseline["Q1"], answer="Free-plan users cannot export CSV; CSV export is available on paid plans only.")
    correction.update(disposition="answered", unresolved_reason="")
    revision = service.edit("Q1", Draft.model_validate(correction), note="Local verification wording correction")
    errors = service.validate(revision)
    if not errors:
        verification_approval(service, revision)
    exact = store.question("Q1")["text"]
    reused = service.reuse(exact)
    rows.append({"case": "approval-reuse", "result": "pass" if not errors and reused.get("answer") == correction["answer"] else "fail",
                 "observed": {"errors": errors, "answer": reused.get("answer"), "approval": reused.get("approval")},
                 "revision_id": revision})
    pending = dict(correction, answer="Unapproved verification edit awaiting review.")
    service.edit("Q1", pending)
    rows.append({"case": "unapproved-edit", "result": "pass" if service.reuse(exact) == reused else "fail",
                 "observed": "Pending edit excluded; previous approval retained"})
    # A separate process uses FileReplayTransport without initializing a live client.
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    process = subprocess.run([sys.executable, "-c", """
import json,sys
from workspace.store import Store
from workspace.gemini import Gemini,FileReplayTransport
from workspace.service import Service
s=Store(sys.argv[1])
print(json.dumps(Service(s,Gemini(s,FileReplayTransport(sys.argv[2]),model=sys.argv[3])).reuse(sys.argv[4])))
s.close()
""", path, str(service.gemini.capture_dir), service.gemini.model, exact], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True)
    rows.append({"case": "reload", "result": "pass" if json.loads(process.stdout) == reused else "fail",
                 "observed": "Approval wording, identity, timestamp and evidence compared in a new process"})
    if not perform_live:
        findings = service.validate(store.question("Q1")["working_revision"])
        rows.append({"case": "replay-miss", "result": "pass" if findings == ["No exact replay match"] else "fail",
                     "observed": findings})
    # Source-version changes are strictly local. Never send altered or added sources to Google.
    document = next(d for d in store.snapshot()["documents"] if d["id"] == "EXPORT-v2")
    store.update_source(dict(document, version=document["version"] + 1))
    rows.append({"case": "source-change", "result": "pass" if not service.reuse(exact)["eligible"]
                 and store.question("Q1")["status"] == "review_required" else "fail",
                 "observed": "Local version change invalidated approvals; historical evidence retained"})
    store.remove_source("EXPORT-v2")
    rows.append({"case": "source-removal", "result": "pass" if not service.reuse(exact)["eligible"]
                 and bool(store.revision(revision)["citations"]) else "fail",
                 "observed": "Local removal blocks reuse and preserves cited source revisions"})
    return rows, baseline, blocker


class ForbiddenEnvironment(dict):
    def get(self, *args):
        raise AssertionError("Offline replay attempted environment/credential access")


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    supplied = json.loads((ROOT / "tasks/evidence/expected-seed-results.json").read_text(encoding="utf-8"))
    extra = json.loads((ROOT / "tests/reference-cases.json").read_text(encoding="utf-8"))["cases"]
    definitions = {c["id"]: {**c, "origin": "Supplied expected-seed-results.json"} for c in supplied}
    definitions.update({c["id"]: c for c in extra})
    session_id = uuid4().hex
    capture_dir = ROOT / "artifacts/real-runs" / session_id
    database = output / f"live-{session_id}.sqlite3"
    store = Store(database)
    store.import_seed(seed)
    report = {"generated_at": now(), "database": str(database), "capture_directory": str(capture_dir),
              "provenance": "real Gemini responses; isolated verification demonstration approvals",
              "settings": {"temperature": 0, "max_output_tokens": 8192, "timeout_ms": 30000},
              "destination": "https://generativelanguage.googleapis.com", "working_database_touched": False}
    try:
        try:
            model = local_configuration()
        except ValueError as exc:
            report.update(model=None, blocker=str(exc), live_rows=[], replay_rows=[])
        else:
            report["model"] = model
            service = Service(store, Gemini(store, ApprovedSeedTransport(seed["questions"], store.snapshot()),
                                           model=model, capture_dir=capture_dir))
            live_rows, live_baseline, blocker = run_scenarios(service, definitions, perform_live=True)
            report.update(live_rows=live_rows, blocker=blocker)
            report["runs"] = [{k: row[k] for k in ("id", "purpose", "question_id", "origin", "error")}
                              for row in store.rows("SELECT * FROM model_runs ORDER BY id")]
            report["provider_model_versions"] = sorted({json.loads(row["metadata"])["model_version"]
                                                       for row in store.rows("SELECT metadata FROM model_runs")
                                                       if json.loads(row["metadata"]).get("model_version")})
            replay_store = Store(output / f"credential-free-replay-{session_id}.sqlite3")
            replay_store.import_seed(seed)
            replay = Service(replay_store, Gemini(replay_store, FileReplayTransport(capture_dir),
                                                 model=model, capture_dir=capture_dir))
            saved_credentials = {name: os.environ.pop(name, None)
                                 for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}

            def forbidden_send(*args):
                raise AssertionError("Offline replay attempted a live call")

            try:
                with patch("workspace.gemini.os.environ", ForbiddenEnvironment()), patch.object(
                    LiveTransport, "send", forbidden_send
                ):
                    replay_rows, replay_baseline, replay_blocker = run_scenarios(replay, definitions)
                report.update(replay_rows=replay_rows, replay_blocker=replay_blocker,
                              replay_matches_live=(live_baseline == replay_baseline)
                              if len(live_baseline) == len(seed["questions"]) else None,
                              replay_credential_access="prohibited and not used", replay_network_fallback="prohibited and not used")
            finally:
                for name, value in saved_credentials.items():
                    if value is not None:
                        os.environ[name] = value
                replay_store.close()
        report["seed_fingerprint"] = fingerprint(seed)
        (output / "live-results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification")
    result = verify(parser.parse_args().output)
    print(json.dumps({k: result.get(k) for k in ("model", "blocker", "capture_directory", "replay_matches_live")}, indent=2))
    sys.exit(verification_failed(result))
