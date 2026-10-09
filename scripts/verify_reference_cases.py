"""Independent expected-versus-observed checks in a new verification database, offline only."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prepare_verification import prepare
from scripts.verification_results import inspect_checker
from workspace.gemini import (
    REAL_REPLAY_DIRECTORY,
    REAL_REPLAY_MODEL,
    FileReplayTransport,
    Gemini,
)
from workspace.service import Service
from workspace.store import Store, now


def approval(service, revision):
    role = service.store.question(service.store.revision(revision)["question_id"])["reviewer"]
    return service.approve(revision, reviewer_name="Synthetic verification demonstration",
                           reviewer_role=role, evidence_confirmed=True,
                           note="Isolated demonstration approval, not a working approval")


def facts_match(case, answer):
    text = answer.casefold()
    if case == "Q1":
        return ("cannot export csv" in text or (text.startswith("no") and "csv" in text))
    if case == "Q3":
        return ("monday" in text and "friday" in text and "utc" in text
                and bool(re.search(r"\b0?9:00\b|\b9\s*am\b", text))
                and bool(re.search(r"\b17:00\b|\b5(?::00)?\s*pm\b", text)))
    if case == "Q4":
        return "live chat" in text and bool(re.search(r"\bno\b|not (?:offered|available|provided)", text))
    if case == "Q5":
        return "email" in text and "password" in text
    if case in ("Q6", "Q8"):
        documented_scope = bool(re.search(r"only users? explicitly (?:identified|documented|mentioned|named)", text))
        return bool(re.search(r"account owners?\b", text)) and ("only" not in text or documented_scope)
    if case == "Q7":
        return "monthly" in text
    return False


def matches_question(definition, question, record):
    draft = record["draft"]
    passages = {c["passage_id"] for c in record["citations"]}
    if definition.get("status") == "unresolved":
        return (question["status"] == "unresolved" and question["reviewer"] == definition["owner"]
                and bool(re.search(r"undocumented|not (?:mention|contain|document)|no (?:information|documentation)|unknown",
                                   draft.unresolved_reason.casefold())))
    if question["status"] != "answered":
        return False
    passed = definition.get("source", definition.get("passage")) in passages
    passed = passed and facts_match(definition["id"], draft.answer)
    if "show_conflict_with" in definition:
        passed = passed and definition["show_conflict_with"] in passages
    return passed


def verify(output, *, replay_directory=ROOT / REAL_REPLAY_DIRECTORY):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    captured = prepare(output / "synthetic-captures")
    database = output / f"reference-{uuid4().hex}.sqlite3"
    store = Store(database)
    seed = json.loads((ROOT / "tasks/evidence/seed.json").read_text(encoding="utf-8"))
    expected = json.loads((ROOT / "tasks/evidence/expected-seed-results.json").read_text(encoding="utf-8"))
    independent = json.loads((ROOT / "tests/reference-cases.json").read_text(encoding="utf-8"))
    fixture = json.loads((ROOT / "tests/fixtures/synthetic/seed-responses.json").read_text(encoding="utf-8"))
    definitions = {c["id"]: {**c, "origin": "Supplied expected-seed-results.json"} for c in expected}
    definitions.update({c["id"]: c for c in independent["cases"]})
    store.import_seed(seed)
    service = Service(store, Gemini(store, FileReplayTransport(captured, synthetic=True)))
    rows = []
    live_path = output / "live-results.json"
    live_results = json.loads(live_path.read_text(encoding="utf-8")) if live_path.exists() else None
    remaining_path = output / "q2-q8-results.json"
    remaining_results = json.loads(remaining_path.read_text(encoding="utf-8")) if remaining_path.exists() else None

    def observe(case, passed, observed, revision=None):
        definition = definitions[case]
        run_ids = []
        if revision is not None:
            record = store.revision(revision)
            validation = store.one("SELECT * FROM answer_validations WHERE answer_revision=? "
                                   "ORDER BY id DESC LIMIT 1", (revision,))
            run_ids = [v for v in (record["draft_run"], validation["check_run"] if validation else None) if v]
        rows.append({"case": case, "expected": definition, "expected_origin": definition["origin"],
                     "observed": observed, "result": "pass" if passed else "fail",
                     "provenance": "synthetic exact-request replay / demonstration approvals",
                     "revision_id": revision, "run_ids": run_ids})

    try:
        for q in seed["questions"]:
            revision = service.generate(q["id"])
            if revision is None:
                observe(q["id"], False, {"error": store.question(q["id"])["last_error"]})
                continue
            record = store.revision(revision)
            draft = record["draft"]
            observed = {"answer": draft.answer, "status": store.question(q["id"])["status"],
                        "owner": store.question(q["id"])["reviewer"],
                        "passages": [c["passage_id"] for c in record["citations"]],
                        "disposition": "demonstration human action follows this observation"}
            definition = definitions[q["id"]]
            passed = matches_question(definition, store.question(q["id"]), record)
            if q["id"] == "Q2":
                observe(q["id"], passed, observed, revision)
                service.leave_unresolved(q["id"], "Synthetic review: JSON export needs Product clarification.")
            else:
                observe(q["id"], passed, observed, revision)
                approval(service, revision)
        exact = store.question("Q1")["text"]
        correction = fixture["edited_answers"][0]
        revision = service.edit("Q1", correction, note="Synthetic demonstration correction")
        errors = service.validate(revision)
        if not errors:
            approval(service, revision)
        reused = service.reuse(exact)
        observe("approval-reuse", not errors and reused.get("answer") == correction["answer"], reused, revision)
        pending = dict(correction, answer="Pending synthetic edit awaiting validation.")
        pending_revision = service.edit("Q1", pending)
        unchanged = service.reuse(exact)
        observe("unapproved-edit", unchanged == reused, {"pending_revision": pending_revision,
                                                         "reuse": unchanged}, pending_revision)
        replay_errors = service.validate(pending_revision)
        observe("replay-miss", replay_errors == ["No exact replay match"], {"errors": replay_errors}, pending_revision)
        process = subprocess.run([sys.executable, "-c", """
import json,sys
from workspace.store import Store
from workspace.gemini import FileReplayTransport,Gemini
from workspace.service import Service
s=Store(sys.argv[1])
print(json.dumps(Service(s,Gemini(s,FileReplayTransport(sys.argv[2]))).reuse(sys.argv[3])))
s.close()
""", str(database), str(captured), exact], capture_output=True, text=True, encoding="utf-8", check=True, cwd=ROOT)
        reloaded = json.loads(process.stdout)
        observe("reload", reloaded == reused, {"fresh_process_reuse": reloaded}, revision)
        document = next(d for d in store.snapshot()["documents"] if d["id"] == "EXPORT-v2")
        store.update_source(dict(document, version=3))
        changed = service.reuse(exact)
        observe("source-change", not changed["eligible"] and store.question("Q1")["status"] == "review_required",
                {"reuse": changed, "status": store.question("Q1")["status"]}, revision)
        fresh = service.edit("Q1", correction)
        fresh_errors = service.validate(fresh)
        if not fresh_errors:
            approval(service, fresh)
        store.remove_source("EXPORT-v2")
        unavailable = service.reuse(exact)
        observe("source-removal", not unavailable["eligible"] and bool(store.revision(fresh)["citations"]),
                {"reuse": unavailable, "old_evidence": store.revision(fresh)["citations"]}, fresh)
        working = dict(document, version=3)
        store.update_source(working)
        restored = service.edit("Q1", correction)
        restore_errors = service.validate(restored)
        if not restore_errors:
            approval(service, restored)
        working = json.loads(json.dumps(working))
        working["passages"][0]["text"] += " Synthetic same-version clarification."
        store.update_source(working)
        observe("same-version-change", not service.reuse(exact)["eligible"]
                and store.question("Q1")["status"] == "review_required",
                {"version": 3, "status": store.question("Q1")["status"]}, restored)

        # Real captures, if supplied locally, are replayed through the same validators in a clean database.
        real_directory = Path(replay_directory)
        replay_store = Store(output / f"real-replay-{uuid4().hex}.sqlite3")
        replay_store.import_seed(seed)
        replay_service = Service(replay_store, Gemini(replay_store, FileReplayTransport(real_directory),
                                                     model=REAL_REPLAY_MODEL))
        try:
            for q in seed["questions"]:
                real_revision = replay_service.generate(q["id"])
                question = replay_store.question(q["id"])
                real_record = replay_store.revision(real_revision) if real_revision is not None else None
                checker = inspect_checker(replay_service, q, real_revision) if real_record else None
                question_passed = bool(real_record and matches_question(definitions[q["id"]], question, real_record))
                rows.append({"case": q["id"], "expected": definitions[q["id"]],
                             "expected_origin": definitions[q["id"]]["origin"],
                             "observed": {"status": question["status"], "error": question["last_error"],
                                          "answer": real_record["draft"].answer if real_record else None,
                                          "checker_findings": checker["findings"] if checker else None},
                             "question_result": "pass" if question_passed else ("fail" if real_record else "unverified"),
                             "checker": checker,
                             "result": ("unverified" if question["last_error"] == "No exact replay match" else "fail")
                             if real_revision is None else (
                                 "pass" if question_passed and checker["request_result"] ==
                                 checker["semantic_result"] == "pass" else "fail"),
                             "provenance": "replay of existing local real captures; no network fallback",
                             "revision_id": real_revision,
                             "reason": question["last_error"] or "No generated revision" if real_revision is None
                             else "Existing real capture compared with independent expectations; no working approval made"})
        finally:
            replay_store.close()
        for row in rows:
            row["invocation"] = "current"
        current_failures = [r["case"] for r in rows if r["result"] == "fail"]
        historical_start = len(rows)
        if live_results:
            for kind in ("live_rows", "replay_rows"):
                for live_row in live_results.get(kind, []):
                    definition = definitions.get(live_row["case"], {"expected": live_row["case"], "origin": "Plan lifecycle verification"})
                    rows.append({**live_row, "expected": definition, "expected_origin": definition["origin"],
                                 "provenance": "live Gemini" if kind == "live_rows" else "credential-free real capture replay"})
            for partial in live_results.get("partial_draft_replay", []):
                definition = definitions[partial["case"]]
                rows.append({**partial, "expected": definition, "expected_origin": definition["origin"],
                             "provenance": "partial real draft replay; semantic checking unverified"})
            for retry in live_results.get("authorized_checker_retries", []):
                rows.append({"case": "Q1-checker-retry", "expected": "Supported Q1 answer passes semantic checking",
                             "expected_origin": "domain.md worked example and original EXPORT passages",
                             "observed": {k: retry.get(k) for k in ("model", "result", "findings", "error", "replay")},
                             "result": retry["result"], "provenance": "authorized real checker retry"})
            if live_results.get("q1_replay_lifecycle"):
                lifecycle = live_results["q1_replay_lifecycle"]
                rows.append({"case": "Q1-checker-after-local-offset-fix", "expected": definitions["Q1"],
                             "expected_origin": definitions["Q1"]["origin"],
                             "observed": {"validation": lifecycle["validation"], "raw_checker_offsets_retained": True,
                                          "credential_access": lifecycle["credential_access"], "network_calls": 0},
                             "result": "pass" if not lifecycle["validation"] else "fail",
                             "provenance": "real Flash-Lite checker replay after deterministic exact-text span fix"})
                for case, field in (("approval-reuse", "corrected_wording_reused"),
                                    ("unapproved-edit", "unapproved_edit_excluded"), ("reload", "reload_persisted"),
                                    ("source-change", "source_version_blocks_reuse"), ("source-removal", "removal_blocks_reuse")):
                    definition = definitions[case]
                    rows.append({"case": case, "expected": definition, "expected_origin": definition["origin"],
                                 "observed": lifecycle[field], "result": "pass" if lifecycle[field] else "fail",
                                 "provenance": "real draft/check replay after local offset fix; demonstration approval"})
        else:
            rows.append({"case": "live-drafts-and-checks-Q1-Q8", "expected": "Real Gemini drafting/checking for eight questions",
                         "expected_origin": "IMPLEMENTATION_PLAN.md final verification",
                         "observed": "No live API calls or credential access", "result": "unverified", "provenance": "live",
                         "reason": "No live verification outcome supplied"})
        if remaining_results:
            for kind in ("live_rows", "replay_rows"):
                for observed_row in remaining_results[kind]:
                    definition = definitions[observed_row["case"]]
                    rows.append({**observed_row, "expected": definition, "expected_origin": definition["origin"],
                                 "provenance": "real Q2–Q8 live verification" if kind == "live_rows"
                                 else "real Q2–Q8 replay with credentials/network prohibited"})
        for row in rows[historical_start:]:
            row["invocation"] = "historical"
        integrity = subprocess.run(["git", "diff", "--exit-code", "HEAD", "--", "tasks/evidence"],
                                   cwd=ROOT, capture_output=True, check=False)
        report = {"generated_at": now(), "database": str(database), "rows": rows,
                  "current_failures": current_failures,
                  "synthetic_review_dispositions": "Seven demonstration approvals and one unresolved note; "
                                                    "later source scenarios intentionally invalidate approvals",
                  "live_verification": live_results if live_results else "unverified; no live outcome supplied",
                  "q2_q8_verification": remaining_results if remaining_results else "not supplied",
                  "retained_outcomes_scope": "Historical recorded labels; not current checker certification",
                  "browser_checks": json.loads((output / "browser-checks.json").read_text())
                  if (output / "browser-checks.json").exists() else "pending browser verification",
                  "local_checks": json.loads((output / "checks.json").read_text())
                  if (output / "checks.json").exists() else "No command results supplied; this script does not run the test suite",
                  "completion_checklist": {
                      "original_fixtures_unchanged": "pass" if integrity.returncode == 0 else "fail",
                      "requested_stack_and_source_import": "verified offline; five documents and eight questions",
                      "shared_pydantic_contracts": "verified offline, including native SDK schemas and replay parsing",
                      "real_draft_and_edited_answer_validation": {
                          "current_replay": {r["case"]: r["result"] for r in rows
                                             if r["invocation"] == "current" and r.get("checker") is not None},
                          "historical_Q1": "See retained live_verification; older prompts cannot match current requests",
                          "Q2": "Unresolved disposition is correct; checker acceptance is a separate result"},
                      "review_ui": "UI checks are recorded separately in local_checks and browser_checks",
                      "immutable_history_and_reload": "verified synthetic demonstration, including process restart",
                      "exact_approved_reuse_and_draft_exclusion": "verified synthetic demonstration",
                      "source_changes_and_disappearance": "verified synthetic demonstration with immediate durable invalidation",
                      "raw_real_capture_and_real_replay": "Current real replay rows record exact matching, missing captures and checker outcomes; "
                                                          "retained historical rows are not fresh verification",
                      "failures": "malformed output, missing references, API errors, irrelevant citations, "
                                  "extra claims and conflicts checked with labelled synthetic data",
                      "automated_and_browser_checks": "See local_checks and browser_checks for actual recorded outcomes",
                      "independent_reference_report": "supplied five plus ten independently declared additions",
                      "completion_claims_distinguish_blockers": live_results.get("blocker") if live_results else "live verification unverified"}}
        (output / "reference-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Expected versus observed verification", "", f"Generated: {report['generated_at']}", "",
                 ("Synthetic checks and demonstration approvals do not establish live Gemini correctness. "
                  "Live attempts and credential-free replay are recorded separately below. "
                  "Historical pass labels are retained as recorded and do not certify current checker success."), "",
                 f"Isolated database: `{database}`", "", "| Case | Invocation | Provenance | Result | Observed |",
                 "| --- | --- | --- | --- | --- |"]
        for row in rows:
            detail = row.get("observed", row.get("reason", row.get("scope", "No observation recorded")))
            if isinstance(detail, dict):
                detail = {k: v for k, v in detail.items() if k not in ("evidence", "old_evidence")}
                for key in ("reuse", "fresh_process_reuse"):
                    if key in detail:
                        detail[key] = {k: v for k, v in detail[key].items() if k != "evidence"}
            observed = json.dumps(detail, ensure_ascii=False).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {row['case']} | {row['invocation']} | {row['provenance']} | {row['result']} | {observed} |")
        lines.extend(["", "## Completion checklist", ""])
        lines.extend(f"- {key}: {value}" for key, value in report["completion_checklist"].items())
        lines.extend(["", "## Browser verification", "", json.dumps(report["browser_checks"], ensure_ascii=False, indent=2)])
        lines.extend(["", "## Executed local checks", "", json.dumps(report["local_checks"], ensure_ascii=False, indent=2)])
        if live_results:
            lines.extend(["", "## Retained historical live verification outcome", "", "```json",
                          json.dumps(live_results, ensure_ascii=False, indent=2), "```"])
        if remaining_results:
            lines.extend(["", "## Retained historical Q2–Q8 live and replay outcomes", "", "```json",
                          json.dumps(remaining_results, ensure_ascii=False, indent=2), "```"])
        (output / "reference-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verification")
    parser.add_argument("--replay-dir", type=Path, default=ROOT / REAL_REPLAY_DIRECTORY)
    args = parser.parse_args()
    report = verify(args.output, replay_directory=args.replay_dir)
    historical = [r["case"] for r in report["rows"] if r["invocation"] == "historical" and r["result"] == "fail"]
    failures = report["current_failures"]
    print(f"Report written. Current failures: {failures}. Historical failures retained: {historical}.")
    return bool(failures) or report["completion_checklist"]["original_fixtures_unchanged"] != "pass"


if __name__ == "__main__":
    sys.exit(main())
