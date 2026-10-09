import json
from pathlib import Path

from conftest import SyntheticTransport

from scripts.prepare_verification import synthetic_check
from scripts.verify_q1_demo import CORRECTION_TEXT, draft_and_correction, verify
from workspace.evidence import Draft
from workspace.gemini import Gemini
from workspace.service import Service


def test_q1_correction_is_checked_without_implicit_approval(store, synthetic):
    correction = Draft.model_validate({**synthetic["draft"], "answer": CORRECTION_TEXT})
    transport = SyntheticTransport(synthetic["draft"], synthetic["check"], synthetic_check(correction).model_dump())
    rows, observed = draft_and_correction(Service(store, Gemini(store, transport)))
    assert all(row["result"] == "pass" for row in rows)
    assert observed == correction
    assert [r["purpose"] for r in transport.calls] == ["draft", "check", "check"]
    assert json.loads(transport.calls[-1]["contents"][-1])["proposed_answer"] == correction.model_dump()
    assert not store.rows("SELECT * FROM approvals")


def test_q1_demo_does_not_hide_bad_initial_check_or_request_correction(store, synthetic):
    check = {**synthetic["check"], "answers_question": False}
    transport = SyntheticTransport(synthetic["draft"], check)
    rows, correction = draft_and_correction(Service(store, Gemini(store, transport)))
    assert rows[0]["result"] == "fail"
    assert correction is None
    assert len(transport.calls) == 2
    assert not store.rows("SELECT * FROM approvals")


def test_saved_real_q1_correction_and_lifecycle_replay_without_credentials(tmp_path):
    report = verify(tmp_path / "real-q1-demo")
    assert report["result"] == "pass"
    assert report["live_rows"] == []
    assert report["replay_matches_live"] is True
    assert report["replay_credential_access"] == "prohibited and not used"
    assert {row["case"] for row in report["replay_rows"]} == {
        "Q1", "corrected-wording-check", "unapproved-correction-excluded", "approval-reuse",
        "unapproved-edit-excluded", "novel-edit-replay-miss", "reload", "source-change", "source-removal",
    }
    correction = json.loads(Path(report["correction_file"]).read_text(encoding="utf-8"))
    assert correction["answer"] == CORRECTION_TEXT
