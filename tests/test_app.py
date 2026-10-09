import json
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from scripts.prepare_verification import prepare
from workspace.evidence import Draft
from workspace.gemini import (
    REAL_REPLAY_MODEL,
    FileReplayTransport,
    Gemini,
    capture_bundle,
)
from workspace.service import Service
from workspace.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ui(tmp_path, monkeypatch):
    captures = prepare(tmp_path / "captures")
    database = tmp_path / "ui.sqlite3"
    monkeypatch.setenv("WORKSPACE_DB", str(database))
    monkeypatch.setenv("WORKSPACE_VERIFICATION", "1")
    monkeypatch.setenv("WORKSPACE_REPLAY_DIR", str(captures))
    monkeypatch.delenv("WORKSPACE_ALLOW_LIVE", raising=False)
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    return app, database


def draft(ui):
    app, _ = ui
    app.button(key="generate").click().run()
    assert not app.exception
    return app


def approve_q1(app):
    app.button(key="open_approval").click().run()
    app.text_input(key="reviewer").set_value("Demonstration reviewer")
    app.checkbox(key="evidence_confirmed").check()
    app.button(key="approve").click().run()
    assert not app.exception


def test_queue_filters_and_reruns_make_no_calls(ui):
    app, path = ui
    assert any("8 to draft" in c.value and "0 approved" in c.value for c in app.caption)
    assert not app.metric
    assert [tab.label for tab in app.tabs] == ["Review", "Reuse approved answer", "Sources", "History & diagnostics"]
    assert not any(a.label in ("Answer wording", "Unresolved review note") for a in app.text_area)
    assert not any(b.key == "approve" for b in app.button)
    app.selectbox(key="reviewer_filter").select("Support reviewer").run()
    assert app.radio(key="question").value == "Q3"
    app.selectbox(key="status_filter").select("approved").run()
    assert any("No questions match" in item.value for item in app.info)
    app.run()
    store = Store(path)
    assert not store.rows("SELECT * FROM model_runs")
    store.close()


def test_edit_approve_reuse_pending_draft_and_reload(ui):
    app, path = ui
    draft(ui)
    assert any("EXPORT-v1:p1" in item.value and "Replaced" in item.value for item in app.caption)
    assert any("every plan" in item.value for item in app.text)
    app.button(key="open_approval").click().run()
    app.button(key="approve").click().run()
    assert any("explicit evidence confirmation" in item.value for item in app.error)
    store = Store(path)
    revision = store.question("Q1")["working_revision"]
    fixture = json.loads((ROOT / "tests/fixtures/synthetic/seed-responses.json").read_text())
    correction = fixture["edited_answers"][0]["answer"]
    store.close()
    app.button(key="edit").click().run()
    app.text_area(key=f"answer_{revision}").set_value(correction)
    app.button(key="save_edit").click().run()
    assert not any(b.key == "validate" for b in app.button)
    store = Store(path)
    assert store.question("Q1")["status"] == "answered"
    assert not store.rows("SELECT * FROM approvals")
    store.close()
    approve_q1(app)
    app.text_input(key="repeat_text").set_value("Can free-plan users export CSV?")
    app.session_state["workspace_tabs"] = "Reuse approved answer"
    app.button(key="reuse").click().run()
    assert app.session_state["workspace_tabs"] == "Reuse approved answer"
    assert any("Eligible approved answer" in item.value for item in app.success)
    store = Store(path)
    approved = store.question("Q1")["working_revision"]
    runs_before = len(store.rows("SELECT * FROM model_runs"))
    store.close()
    app.button(key="edit").click().run()
    app.text_area(key=f"answer_{approved}").set_value("Pending unsupported wording")
    app.button(key="save_edit").click().run()
    assert not app.session_state["evidence_confirmed"]
    assert app.button(key="open_approval").disabled
    assert any("No exact replay match" in w.value for w in app.warning)
    assert any(item.value == correction for item in app.text)
    assert any("pending edit" in item.value for item in app.info)
    restarted = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not restarted.exception
    assert any("Demonstration reviewer" in item.value for item in restarted.caption)
    store = Store(path)
    assert len(store.rows("SELECT * FROM model_runs")) == runs_before + 1
    assert store.question("Q1")["status"] == "approved"
    store.close()


def test_source_update_remove_and_failed_update(ui):
    app, path = ui
    draft(ui)
    approve_q1(app)
    app.selectbox(key="source").select("EXPORT-v2").run()
    app.text_area(key="source_json_2").set_value("{bad")
    app.checkbox(key="consistent").check()
    app.button(key="save_source").click().run()
    assert any("Source update rejected" in item.value for item in app.error)
    store = Store(path)
    document = next(d for d in store.snapshot()["documents"] if d["id"] == "EXPORT-v2")
    assert store.question("Q1")["status"] == "approved"
    store.close()
    document["version"] = 3
    app.text_area(key="source_json_2").set_value(json.dumps(document))
    app.button(key="save_source").click().run()
    assert any("Reuse is blocked" in item.value for item in app.warning)
    app.text_input(key="repeat_text").set_value("Can free-plan users export CSV?")
    app.button(key="reuse").click().run()
    assert any("No eligible approval" in item.value for item in app.warning)
    # A fresh revision uses the new snapshot and a matching synthetic checking capture.
    app.button(key="edit").click().run()
    app.button(key="save_edit").click().run()
    approve_q1(app)
    store = Store(path)
    assert store.question("Q1")["status"] == "approved"
    store.close()
    app.checkbox(key="remove_confirm").check()
    app.button(key="remove_source").click().run()
    assert any("Old evidence" in item.value for item in app.success)
    assert any("EXPORT-v2:p1" in item.value for item in app.caption)
    store = Store(path)
    assert not store.snapshot()["availability"]["EXPORT-v2"]
    assert store.question("Q1")["status"] == "review_required"
    store.close()


def test_unsupported_question_review_note(ui):
    app, path = ui
    app.radio(key="question").set_value("Q2").run()
    draft(ui)
    assert any("undocumented" in item.value for item in app.warning)
    assert app.button(key="open_approval").disabled
    assert not any(b.key == "validate" for b in app.button)
    app.button(key="edit").click().run()
    assert not app.exception
    editor = app.dataframe[0].value
    assert editor.empty
    assert list(editor.columns) == ["passage_id", "excerpt"]
    app.button(key="cancel_review").click().run()
    app.button(key="open_unresolved").click().run()
    app.button(key="leave_unresolved").click().run()
    assert any("requires a note" in item.value for item in app.error)
    app.text_area(key="unresolved_note_Q2").set_value("Ask the Product reviewer to document JSON export.")
    app.button(key="leave_unresolved").click().run()
    store = Store(path)
    question = store.question("Q2")
    assert question["status"] == "unresolved"
    assert store.revision(question["working_revision"])["note"]
    assert not store.rows("SELECT * FROM approvals")
    store.close()


def test_review_panels_cancel_and_question_change_make_no_calls(ui):
    app, path = ui
    draft(ui)
    store = Store(path)
    runs = len(store.rows("SELECT * FROM model_runs"))
    store.close()
    app.button(key="open_approval").click().run()
    app.checkbox(key="evidence_confirmed").check().run()
    app.button(key="edit").click().run()
    assert not any(b.key == "approve" for b in app.button)
    app.button(key="cancel_review").click().run()
    assert not any(b.key == "save_edit" for b in app.button)
    app.button(key="open_unresolved").click().run()
    app.radio(key="question").set_value("Q3").run()
    assert app.session_state["review_action"] is None
    assert not app.session_state["evidence_confirmed"]
    assert not any(b.key == "leave_unresolved" for b in app.button)
    store = Store(path)
    assert len(store.rows("SELECT * FROM model_runs")) == runs
    assert not store.rows("SELECT * FROM approvals")
    store.close()


def test_edit_with_model_actions_blocked_saves_unvalidated_draft(ui):
    app, path = ui
    draft(ui)
    store = Store(path)
    original = store.question("Q1")["working_revision"]
    runs = len(store.rows("SELECT * FROM model_runs"))
    store.close()
    app.selectbox(key="mode").select("Live Gemini").run()
    app.button(key="edit").click().run()
    app.text_area(key=f"answer_{original}").set_value("Reviewer wording awaiting evidence checks")
    assert app.button(key="save_edit").label == "Save draft"
    app.button(key="save_edit").click().run()
    assert not app.exception
    assert app.button(key="open_approval").disabled
    assert app.button(key="validate").disabled
    store = Store(path)
    edited = store.question("Q1")["working_revision"]
    assert edited != original
    assert not store.rows("SELECT * FROM answer_validations WHERE answer_revision=?", (edited,))
    assert len(store.rows("SELECT * FROM model_runs")) == runs
    assert not store.rows("SELECT * FROM approvals")
    store.close()


def test_api_failure_and_replay_miss_visible_preserve_approval(ui, monkeypatch):
    app, path = ui
    draft(ui)
    approve_q1(app)

    def failure(*args):
        raise TimeoutError("Synthetic provider failure; Authorization=DO-NOT-PERSIST")

    monkeypatch.setattr(FileReplayTransport, "send", failure)
    app.button(key="generate").click().run()
    assert any("TimeoutError" in item.value for item in app.error)
    assert not app.exception
    store = Store(path)
    assert store.question("Q1")["status"] == "approved"
    assert "DO-NOT-PERSIST" not in store.question("Q1")["last_error"]
    store.close()


def test_live_block_and_real_replay_miss_do_not_read_credentials(ui):
    app, _ = ui
    app.selectbox(key="mode").select("Live Gemini").run()
    assert app.button(key="generate").disabled
    assert any("blocked pending approval" in item.value for item in app.warning)
    app.selectbox(key="mode").select("Replay of real run").run()
    app.button(key="generate").click().run()
    assert any("No exact replay match" in item.value for item in app.error)
    assert not app.exception


def test_malformed_capture_and_missing_reference_visible(ui, monkeypatch):
    from workspace.gemini import Response

    app, _ = ui
    monkeypatch.setattr(FileReplayTransport, "send", lambda *args: Response("{malformed"))
    app.button(key="generate").click().run()
    assert any("Invalid Gemini output" in item.value for item in app.error)
    fixture = json.loads((ROOT / "tests/fixtures/synthetic/seed-responses.json").read_text())
    value = fixture["drafts"][0]
    value["citations"][0]["passage_id"] = "ABSENT:p1"
    monkeypatch.setattr(FileReplayTransport, "send", lambda *args: Response(json.dumps(value)))
    app.button(key="generate").click().run()
    assert any("Missing passage: ABSENT:p1" in item.value for item in app.warning)
    assert app.button(key="open_approval").disabled
    assert not any(b.key == "approve" for b in app.button)


def test_all_eight_questions_have_explicit_review_dispositions(ui):
    app, path = ui
    for number in range(1, 9):
        question_id = f"Q{number}"
        app.radio(key="question").set_value(question_id).run()
        draft(ui)
        if question_id == "Q2":
            app.button(key="open_unresolved").click().run()
            app.text_area(key="unresolved_note_Q2").set_value("Synthetic review: JSON export is undocumented.")
            app.button(key="leave_unresolved").click().run()
        else:
            app.button(key="open_approval").click().run()
            assert not app.checkbox(key="evidence_confirmed").value
            app.text_input(key="reviewer").set_value("Eight-question demonstration reviewer")
            app.checkbox(key="evidence_confirmed").check()
            app.button(key="approve").click().run()
        assert not app.exception
    store = Store(path)
    assert len(store.rows("SELECT * FROM approvals")) == 7
    assert store.question("Q2")["status"] == "unresolved"
    assert any("1 unresolved" in c.value and "7 approved" in c.value for c in app.caption)
    store.close()


def test_fresh_default_real_mode_opens_q1_and_reuses_checked_correction(tmp_path, monkeypatch):
    from scripts.prepare_verification import synthetic_check
    from scripts.verify_q1_demo import CORRECTION_TEXT

    # Labelled synthetic captures exercise real-mode configuration; no provider call is made.
    captures = tmp_path / "default-session"
    captures.mkdir()
    capture_store = Store(":memory:")
    capture_store.import_seed(json.loads((ROOT / "tasks/evidence/seed.json").read_text()))
    fixture = json.loads((ROOT / "tests/fixtures/synthetic/seed-responses.json").read_text())
    value = next(d for d in fixture["drafts"] if d["question_id"] == "Q1")
    draft_value = Draft.model_validate(value)
    correction = Draft.model_validate({**value, "answer": CORRECTION_TEXT})
    engine = Gemini(capture_store, None, model=REAL_REPLAY_MODEL)
    question = {k: capture_store.question("Q1")[k] for k in ("id", "topic", "text")}
    for label, purpose, proposal, response in (
        ("draft", "draft", None, draft_value),
        ("check", "check", draft_value, synthetic_check(draft_value)),
        ("correction", "check", correction, synthetic_check(correction)),
    ):
        request = engine.request(purpose, question, capture_store.snapshot(),
                                 proposal)
        run = capture_store.record_run(request, response.model_dump_json(), None, "live",
                                       {"provenance": "Synthetic test of default real-mode configuration"})
        (captures / f"{label}.json").write_text(capture_bundle(capture_store, run).model_dump_json())
    capture_store.close()
    monkeypatch.setattr("workspace.gemini.REAL_REPLAY_DIRECTORY", str(captures))
    monkeypatch.setenv("WORKSPACE_DB", str(tmp_path / "default-ui.sqlite3"))
    for name in ("WORKSPACE_VERIFICATION", "WORKSPACE_REPLAY_DIR", "GEMINI_MODEL", "WORKSPACE_ALLOW_LIVE"):
        monkeypatch.delenv(name, raising=False)
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    assert app.selectbox(key="mode").value == "Replay of real run"
    assert app.radio(key="question").value == "Q1"
    assert any("Q1–Q8" in item.value for item in app.info)
    assert not any("Q1's historical captures" in item.value for item in app.warning)
    app.button(key="generate").click().run()
    assert not app.exception
    assert any("EXPORT-v1:p1" in item.value and "Replaced" in item.value for item in app.caption)
    store = Store(tmp_path / "default-ui.sqlite3")
    revision = store.question("Q1")["working_revision"]
    assert store.question("Q1")["status"] == "answered"
    assert not store.rows("SELECT * FROM approvals")
    store.close()
    app.button(key="edit").click().run()
    app.text_area(key=f"answer_{revision}").set_value(CORRECTION_TEXT)
    app.button(key="save_edit").click().run()
    assert not app.exception
    approve_q1(app)
    app.session_state["workspace_tabs"] = "Reuse approved answer"
    app.text_input(key="repeat_text").set_value(question["text"])
    app.button(key="reuse").click().run()
    assert any(item.value == CORRECTION_TEXT for item in app.text)
    app.run()
    store = Store(tmp_path / "default-ui.sqlite3")
    assert Service(store, Gemini(store, FileReplayTransport(captures))).reuse(question["text"])["answer"] == CORRECTION_TEXT
    assert all(r["origin"] == "replay_real" for r in store.rows("SELECT * FROM model_runs"))
    assert len(store.rows("SELECT * FROM model_runs")) == 3
    store.close()


def test_empty_real_replay_configuration_is_visible_before_drafting(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DB", str(tmp_path / "missing-real-ui.sqlite3"))
    monkeypatch.setenv("WORKSPACE_REPLAY_DIR", str(tmp_path / "missing-captures"))
    monkeypatch.delenv("WORKSPACE_VERIFICATION", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    assert any("No saved real captures" in item.value for item in app.warning)
    app.button(key="generate").click().run()
    assert not app.exception
    assert any("No exact replay match" in item.value for item in app.error)


def test_checker_conflict_passage_and_explanation_visible_for_generation_and_edit(ui, monkeypatch):
    from conftest import SyntheticTransport
    from test_lifecycle import supported_check

    app, path = ui
    store = Store(path)
    document = {"id": "SUPPORT-WORKING", "version": 1, "date": "2026-10-09",
                "status": "current", "supersedes": None,
                "passages": [{"id": "SUPPORT-WORKING:p1",
                              "text": "Email support is available Saturday and Sunday only."}]}
    store.update_source(document)
    store.close()
    fixture = json.loads((ROOT / "tests/fixtures/synthetic/seed-responses.json").read_text())
    value = next(d for d in fixture["drafts"] if d["question_id"] == "Q3")
    check = supported_check(value)
    check["conflicts"] = [{"passage_ids": ["SUPPORT-v1:p1", "SUPPORT-WORKING:p1"],
                           "explanation": "Independent support schedules disagree."}]
    transport = SyntheticTransport(value, check, check)
    monkeypatch.setattr(FileReplayTransport, "send", transport.send)
    app.radio(key="question").set_value("Q3").run()
    draft(ui)
    assert any("Saturday and Sunday only" in item.value for item in app.text)
    assert any("Checker conflict" in item.value and "schedules disagree" in item.value for item in app.caption)
    app.button(key="edit").click().run()
    app.button(key="save_edit").click().run()
    assert not app.exception
    assert any("Saturday and Sunday only" in item.value for item in app.text)
    assert any("Unresolved source conflict" in item.value for item in app.warning)
    assert app.button(key="open_approval").disabled
    assert not any(b.key == "approve" for b in app.button)


def test_malformed_bundle_cannot_crash_ui_or_block_valid_capture(ui, monkeypatch):
    from workspace.evidence import fingerprint

    app, path = ui
    captures = Path(os.environ["WORKSPACE_REPLAY_DIR"])
    invalid = json.loads(next(captures.glob("*.json")).read_text())
    invalid["request"]["question"] = "not-an-object"
    invalid["request_fingerprint"] = fingerprint(invalid["request"])
    (captures / "000-invalid.json").write_text(json.dumps(invalid))
    draft(ui)
    store = Store(path)
    original = store.question("Q1")["working_revision"]
    assert original is not None
    store.close()
    invalid_only = captures.parent / "invalid-only"
    invalid_only.mkdir()
    (invalid_only / "invalid.json").write_text(json.dumps(invalid))
    monkeypatch.setenv("WORKSPACE_REPLAY_DIR", str(invalid_only))
    app.run()
    app.button(key="generate").click().run()
    assert not app.exception
    assert any("No exact replay match" in item.value for item in app.error)
    store = Store(path)
    assert store.question("Q1")["working_revision"] == original
    assert store.question("Q1")["last_error"] == "No exact replay match"
    assert store.one("SELECT * FROM model_runs ORDER BY id DESC LIMIT 1")["error"] == "No exact replay match"
    store.close()
