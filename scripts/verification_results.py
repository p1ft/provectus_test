"""Separate reference dispositions from checker requests and semantic acceptance."""

import json

from workspace.evidence import semantic_errors
from workspace.gemini import ModelFailure


def inspect_checker(service, question, revision):
    draft = service.store.revision(revision)["draft"]
    if draft.disposition == "unresolved":
        try:
            check, run_id = service.gemini.run("check", question, service.store.snapshot(), draft)
        except ModelFailure as exc:
            return {"request_result": "fail", "semantic_result": "unverified",
                    "findings": [str(exc)], "run_id": exc.run_id}
        findings = semantic_errors(draft, check, service.store.snapshot())
        # An empty unresolved proposal is expected not to answer the question or cite evidence.
        # This is verification of the checker response, never approval validation.
        if not draft.answer:
            findings = [f for f in findings if f not in (
                "Answer does not answer the question", "Citations are irrelevant to the answer")]
            if check.full_answer == "" and check.answers_question:
                findings.append("Checker claims an empty answer answers the question")
    else:
        validation = service.store.one("SELECT * FROM answer_validations WHERE answer_revision=? "
                                       "ORDER BY id DESC LIMIT 1", (revision,))
        run_id, findings = validation["check_run"], json.loads(validation["errors"])
        if run_id is None:
            return {"request_result": "unverified", "semantic_result": "unverified",
                    "findings": findings, "run_id": None}
    return {"request_result": "pass", "semantic_result": "fail" if findings else "pass",
            "findings": findings, "run_id": run_id}


def verification_failed(report):
    """Both phases and an explicit exact replay comparison are required for success."""
    return (bool(report.get("blocker") or report.get("replay_blocker"))
            or report.get("replay_matches_live") is not True
            or any(not report.get(kind) or any(row["result"] != "pass" for row in report[kind])
                   for kind in ("live_rows", "replay_rows")))
