import json
import sys

import pytest
from conftest import SyntheticTransport

from scripts import verify_live, verify_reference_cases, verify_remaining
from scripts.verification_results import verification_failed
from workspace.gemini import Gemini
from workspace.service import Service


@pytest.mark.parametrize("checker,request_result,semantic_result", [
    (TimeoutError("Synthetic checker timeout"), "fail", "unverified"),
    ("{malformed synthetic response", "fail", "unverified"),
    ({"question_id": "Q2", "full_answer": "", "all_claims_covered": True,
      "answers_question": False, "citations_relevant": False,
      "omitted_claims": [], "claims": [], "conflicts": []}, "pass", "pass"),
    ({"question_id": "Q2", "full_answer": "Invented answer", "all_claims_covered": True,
      "answers_question": True, "citations_relevant": True,
      "omitted_claims": [], "claims": [{"start": 0, "end": 15, "text": "Invented answer",
       "supporting_passage_ids": ["missing:p1"], "verdict": "supported", "explanation": "Synthetic error"}],
      "conflicts": []}, "pass", "fail"),
])
@pytest.mark.parametrize("runner", ["remaining", "live"])
def test_unresolved_disposition_does_not_mask_checker_failure(
        store, monkeypatch, checker, request_result, semantic_result, runner):
    draft = {"question_id": "Q2", "disposition": "unresolved", "answer": "", "citations": [],
             "conflicts": [], "unresolved_reason": "JSON export is undocumented"}
    definitions = {"Q2": {"id": "Q2", "status": "unresolved", "owner": "Product reviewer"}}
    service = Service(store, Gemini(store, SyntheticTransport(draft, checker)))
    if runner == "remaining":
        monkeypatch.setattr(verify_remaining, "QUESTION_IDS", ["Q2"])
        rows, _ = verify_remaining.inspect(service, definitions)
    else:
        original_rows = store.rows
        monkeypatch.setattr(store, "rows", lambda sql, params=():
                            [r for r in original_rows(sql, params) if r["id"] == "Q2"]
                            if sql == "SELECT id,topic,text FROM questions ORDER BY id"
                            else original_rows(sql, params))
        rows, _, _ = verify_live.run_scenarios(service, definitions)
    row = rows[0]
    assert row["question_result"] == "pass"
    assert row["checker"]["request_result"] == request_result
    assert row["checker"]["semantic_result"] == semantic_result
    assert row["result"] == ("pass" if semantic_result == "pass" else "fail")
    assert store.question("Q2")["status"] == "unresolved"
    assert not store.rows("SELECT * FROM approvals")


@pytest.mark.parametrize("change", [
    {"live_rows": [{"result": "fail"}]}, {"replay_rows": [{"result": "fail"}]},
    {"replay_rows": [{"result": "unverified"}]}, {"replay_rows": []},
    {"replay_matches_live": False}, {"replay_matches_live": None},
    {"blocker": "Synthetic live blocker"}, {"replay_blocker": "Synthetic replay blocker"},
])
def test_live_success_gate_requires_both_phases_and_exact_replay(change):
    success = {"live_rows": [{"result": "pass"}], "replay_rows": [{"result": "pass"}],
               "replay_matches_live": True}
    assert not verification_failed(success)
    assert verification_failed({**success, **change})


@pytest.mark.parametrize("fresh_failure", [False, True])
def test_reference_entrypoint_gates_current_failures_independently_of_saved_rows(
        tmp_path, monkeypatch, fresh_failure):
    output = tmp_path / "report"
    output.mkdir()
    (output / "q2-q8-results.json").write_text(json.dumps({
        "provenance": "Synthetic historical report input",
        "live_rows": [{"case": "Q2", "result": "pass", "invocation": "current",
                       "checker": {"request_result": "pass", "semantic_result": "pass"}}],
        "replay_rows": [{"case": "Q3", "result": "fail"}],
    }))
    original = verify_reference_cases.matches_question
    if fresh_failure:
        monkeypatch.setattr(verify_reference_cases, "matches_question", lambda definition, q, record:
                            False if definition["id"] == "Q3" else original(definition, q, record))
    monkeypatch.setattr(sys, "argv", ["verify_reference_cases.py", "--output", str(output),
                                    "--replay-dir", str(tmp_path / "missing")])
    assert verify_reference_cases.main() == fresh_failure
    report = json.loads((output / "reference-results.json").read_text())
    assert report["current_failures"] == (["Q3"] if fresh_failure else [])
    assert any(r["case"] == "Q3" and r["result"] == "fail" and r["invocation"] == "historical"
               for r in report["rows"])
    historical_q2 = next(r for r in report["rows"] if r["case"] == "Q2" and r.get("checker"))
    assert historical_q2["result"] == "pass"
    assert historical_q2["invocation"] == "historical"
    assert report["retained_outcomes_scope"].startswith("Historical")
    assert "Q2" not in report["completion_checklist"]["real_draft_and_edited_answer_validation"]["current_replay"]
    assert "do not certify current checker success" in (output / "reference-results.md").read_text()
