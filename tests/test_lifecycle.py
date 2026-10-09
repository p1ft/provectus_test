import copy
import json
import sqlite3
import subprocess
import sys

import pytest
from conftest import SyntheticTransport

from workspace.evidence import fingerprint, json_text
from workspace.gemini import Gemini, ReplayTransport
from workspace.service import ReviewBlocked, Service
from workspace.store import Store, now


def supported_check(draft):
    """Synthetic checker result, used only with explicitly documented test wording."""
    return {
        "question_id": draft["question_id"], "full_answer": draft["answer"],
        "all_claims_covered": True, "answers_question": True, "citations_relevant": True,
        "omitted_claims": [], "conflicts": draft["conflicts"], "claims": [{
            "start": 0, "end": len(draft["answer"]), "text": draft["answer"],
            "supporting_passage_ids": [c["passage_id"] for c in draft["citations"]],
            "verdict": "supported", "explanation": "Synthetic support assessment for test",
        }],
    }


def service_with(store, *responses):
    return Service(store, Gemini(store, SyntheticTransport(*responses)))


def approve(service, revision):
    return service.approve(revision, reviewer_name="Test reviewer",
                           reviewer_role="Product reviewer", evidence_confirmed=True,
                           note="Synthetic lifecycle test approval")


def approved_export(store, synthetic):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    revision = service.generate("Q1")
    approve(service, revision)
    return service, revision


def test_correction_approval_pending_edit_and_reload(store, synthetic):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    generated = service.generate("Q1")
    assert store.question("Q1")["status"] == "answered"
    text = store.question("Q1")["text"]
    assert not service.reuse(text)["eligible"]
    correction = copy.deepcopy(synthetic["draft"])
    correction["answer"] = "Free-plan users cannot export CSV. CSV exports are available on paid plans only."
    edited = service.edit("Q1", correction, note="Reviewer correction")
    assert store.revision(edited)["parent_revision"] == generated
    with pytest.raises(ReviewBlocked, match="validation"):
        approve(service, edited)
    service.gemini.transport = SyntheticTransport(supported_check(correction))
    assert service.validate(edited) == []
    approval_id = approve(service, edited)
    expected = service.reuse(text)
    assert expected["answer"] == correction["answer"]
    assert expected["approval"]["id"] == approval_id
    assert expected["approval"]["reviewer_role"] == "Product reviewer"
    assert expected["approval"]["created_at"]
    assert any(c["passage_id"] == "EXPORT-v1:p1" and c["role"] == "replaced"
               for c in expected["evidence"])
    pending = service.edit("Q1", synthetic["draft"], note="Unapproved edit")
    assert service.reuse(text) == expected
    assert store.question("Q1")["working_revision"] == pending
    rows, counts = service.queue()
    assert sum(counts.values()) == 8
    assert counts["approved"] == 1
    assert next(row for row in rows if row["id"] == "Q1")["pending_edit"]
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    # A second connection sees committed approval/history without session state.
    reopened = Store(path)
    try:
        offline = Service(reopened, Gemini(reopened, ReplayTransport(reopened)))
        assert offline.reuse(text) == expected
        assert reopened.revision(pending)["note"] == "Unapproved edit"
        assert reopened.revision(edited)["draft"].answer == correction["answer"]
    finally:
        reopened.close()
    restarted = subprocess.run([sys.executable, "-c", """
import json,sys
from workspace.store import Store
from workspace.gemini import Gemini,ReplayTransport
from workspace.service import Service
store=Store(sys.argv[1])
print(json.dumps(Service(store,Gemini(store,ReplayTransport(store))).reuse(sys.argv[2])))
store.close()
""", path, text], check=True, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(restarted.stdout) == expected


def test_exact_question_only_and_no_unapproved_reuse(store, synthetic):
    service = service_with(store)
    service.edit("Q1", synthetic["draft"])
    text = store.question("Q1")["text"]
    assert not service.reuse(text)["eligible"]
    service, _ = approved_export(store, synthetic)
    for other in (text + " ", text.lower(), "Can users export CSV?"):
        assert not service.reuse(other)["eligible"]


@pytest.mark.parametrize("case", ["identity", "role", "confirmation", "old_revision"])
def test_explicit_approval_requirements(store, synthetic, case):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    revision = service.generate("Q1")
    args = {"reviewer_name": "Reviewer", "reviewer_role": "Product reviewer", "evidence_confirmed": True}
    if case == "identity":
        args["reviewer_name"] = " "
    elif case == "role":
        args["reviewer_role"] = "Billing reviewer"
    elif case == "confirmation":
        args["evidence_confirmed"] = False
    else:
        service.edit("Q1", synthetic["draft"])
    with pytest.raises(ReviewBlocked):
        service.approve(revision, **args)
    assert not store.rows("SELECT * FROM approvals")


def test_unknown_json_and_supported_hours(store):
    unknown = {"question_id": "Q2", "disposition": "unresolved", "answer": "",
               "citations": [], "conflicts": [], "unresolved_reason": "JSON export is undocumented"}
    hours = {"question_id": "Q3", "disposition": "answered",
             "answer": "Monday to Friday, 09:00 to 17:00 UTC.",
             "citations": [{"passage_id": "SUPPORT-v1:p1",
                            "excerpt": "Email support is available Monday to Friday, 09:00 to 17:00 UTC."}],
             "conflicts": [], "unresolved_reason": ""}
    service = service_with(store, unknown, hours, supported_check(hours))
    revision = service.generate("Q2")
    assert store.question("Q2")["status"] == "unresolved"
    assert store.question("Q2")["reviewer"] == "Product reviewer"
    assert len(service.gemini.transport.calls) == 1  # Unknown facts need no support check.
    with pytest.raises(ReviewBlocked):
        approve(service, revision)
    hours_revision = service.generate("Q3")
    assert store.question("Q3")["status"] == "answered"
    assert store.revision(hours_revision)["draft"].answer == hours["answer"]


@pytest.mark.parametrize("failure", [TimeoutError("secret key"), "{bad-json"])
def test_failed_generation_preserves_existing_approval_and_draft(store, synthetic, failure):
    service, revision = approved_export(store, synthetic)
    before = service.reuse(store.question("Q1")["text"])
    service.gemini.transport = SyntheticTransport(failure)
    assert service.generate("Q1") is None
    assert store.question("Q1")["working_revision"] == revision
    assert service.reuse(store.question("Q1")["text"]) == before
    assert store.question("Q1")["last_error"]
    assert "secret" not in store.question("Q1")["last_error"]


def test_failed_first_generation_is_visible_unresolved(store):
    service = service_with(store, TimeoutError("provider unavailable"))
    assert service.generate("Q2") is None
    question = store.question("Q2")
    assert question["status"] == "unresolved"
    assert question["last_error"]
    assert not store.rows("SELECT * FROM answer_revisions")


def test_failed_check_does_not_replace_previous_draft(store, synthetic):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    revision = service.generate("Q1")
    service.gemini.transport = SyntheticTransport(synthetic["draft"], TimeoutError())
    assert service.generate("Q1") is None
    assert store.question("Q1")["working_revision"] == revision
    assert len(store.rows("SELECT * FROM answer_revisions")) == 1


def test_unsupported_edited_claim_blocks_approval(store, synthetic):
    service = service_with(store)
    value = synthetic["draft"]
    value["answer"] += " JSON exports are available."
    revision = service.edit("Q1", value)
    check = supported_check(value)
    # The full answer span is covered, but the extra capability has no evidence.
    check["claims"][0]["verdict"] = "unsupported"
    check["claims"][0]["explanation"] = "JSON export is undocumented"
    service.gemini.transport = SyntheticTransport(check)
    assert any("Unsupported" in error for error in service.validate(revision))
    assert store.question("Q1")["status"] == "unresolved"
    with pytest.raises(ReviewBlocked):
        approve(service, revision)


def test_new_failed_validation_revokes_validation_eligibility(store, synthetic):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    revision = service.generate("Q1")
    service.gemini.transport = SyntheticTransport("{invalid")
    assert service.validate(revision)
    with pytest.raises(ReviewBlocked):
        approve(service, revision)


def test_unresolved_decision_needs_note_and_removes_active_approval(store, synthetic):
    service, original = approved_export(store, synthetic)
    with pytest.raises(ReviewBlocked, match="note"):
        service.leave_unresolved("Q1", "  ")
    decision = service.leave_unresolved("Q1", "Needs product clarification")
    assert not service.reuse(store.question("Q1")["text"])["eligible"]
    assert store.revision(decision)["note"] == "Needs product clarification"
    assert store.revision(original)["draft"].answer == synthetic["draft"]["answer"]
    assert store.one("SELECT * FROM approvals")["invalidation_reason"]
    assert store.question("Q1")["status"] == "unresolved"


def change_stored_source_for_test(store, *, version_change=True):
    """Simulate future source controls directly; no source-update UI/API is implemented."""
    row = store.one("SELECT r.* FROM sources s JOIN source_revisions r ON r.id=s.current_revision "
                    "WHERE s.id='EXPORT-v2'")
    document = json.loads(row["document"])
    if version_change:
        document["version"] += 1
    else:
        document["passages"][0]["text"] += " Additional synthetic working text."
    with store.db:
        revision = store.db.execute(
            "INSERT INTO source_revisions(source_id,document,fingerprint,created_at) VALUES (?,?,?,?)",
            (document["id"], json_text(document), fingerprint(document), now())
        ).lastrowid
        store.db.execute("UPDATE sources SET current_revision=? WHERE id=?",
                         (revision, document["id"]))
    return row["id"]


@pytest.mark.parametrize("change", ["version", "content", "unavailable", "other_document"])
def test_reuse_checks_current_sources_and_persists_invalidation(store, synthetic, change):
    service, original = approved_export(store, synthetic)
    if change in ("version", "content"):
        old = change_stored_source_for_test(store, version_change=change == "version")
    else:
        old = store.snapshot()["revision_ids"]["EXPORT-v2"]
        with store.db:
            store.db.execute("UPDATE sources SET available=0 WHERE id=?",
                             ("EXPORT-v2" if change == "unavailable" else "SUPPORT-v1",))
    assert not service.reuse(store.question("Q1")["text"])["eligible"]
    assert store.question("Q1")["status"] == "review_required"
    assert store.one("SELECT * FROM approvals")["invalidation_reason"]
    assert any(c["source_revision"] == old for c in store.revision(original)["citations"])
    with store.db:
        store.db.execute("UPDATE sources SET current_revision=?,available=1 WHERE id='EXPORT-v2'", (old,))
        store.db.execute("UPDATE sources SET available=1 WHERE id='SUPPORT-v1'")
    assert not service.reuse(store.question("Q1")["text"])["eligible"]


def test_changed_sources_block_approval_until_fresh_revision(store, synthetic):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    old_revision = service.generate("Q1")
    change_stored_source_for_test(store)
    with pytest.raises(ReviewBlocked, match="Sources changed"):
        approve(service, old_revision)
    assert service.validate(old_revision)
    fresh = service.edit("Q1", synthetic["draft"])
    service.gemini.transport = SyntheticTransport(synthetic["check"])
    assert not service.validate(fresh)
    approve(service, fresh)
    assert service.reuse(store.question("Q1")["text"])["eligible"]


def test_replay_missing_edited_check_stays_unresolved(store, synthetic):
    service = service_with(store)
    revision = service.edit("Q1", synthetic["draft"])
    service.gemini = Gemini(store, ReplayTransport(store))
    assert service.validate(revision) == ["No exact replay match"]
    with pytest.raises(ReviewBlocked):
        approve(service, revision)


def test_immutable_answer_citations_and_validation(store, synthetic):
    service, _ = approved_export(store, synthetic)
    for table in ("answer_revisions", "citations", "answer_validations"):
        with pytest.raises(sqlite3.IntegrityError, match="Immutable history"):
            store.db.execute(f"DELETE FROM {table}")
        store.db.rollback()
    assert service.reuse(store.question("Q1")["text"])["eligible"]


def test_wrong_question_response_is_recorded_without_overwriting(store, synthetic):
    synthetic["draft"]["question_id"] = "Q8"
    service = service_with(store, synthetic["draft"])
    assert service.generate("Q1") is None
    assert store.question("Q1")["last_error"] == "Response question ID does not match"
    assert store.question("Q8")["working_revision"] is None


def test_invalid_edit_is_atomic(store, synthetic):
    service, revision = approved_export(store, synthetic)
    value = synthetic["draft"]
    value["unexpected"] = True
    with pytest.raises(ValueError):
        service.edit("Q1", value)
    assert store.question("Q1")["working_revision"] == revision


def test_source_change_during_check_blocks_validation(store, synthetic):
    service = service_with(store)
    revision = service.edit("Q1", synthetic["draft"])

    class ChangingSyntheticTransport(SyntheticTransport):
        def send(self, request, contract):
            response = super().send(request, contract)
            change_stored_source_for_test(store)
            return response

    service.gemini.transport = ChangingSyntheticTransport(synthetic["check"])
    assert "Sources changed during validation" in service.validate(revision)
    with pytest.raises(ReviewBlocked):
        approve(service, revision)


def test_approval_rechecks_snapshot_inside_transaction(store, synthetic, monkeypatch):
    service = service_with(store, synthetic["draft"], synthetic["check"])
    revision = service.generate("Q1")
    refresh = service.refresh

    def refresh_then_change():
        refresh()
        change_stored_source_for_test(store)

    monkeypatch.setattr(service, "refresh", refresh_then_change)
    with pytest.raises(ReviewBlocked, match="Sources changed"):
        approve(service, revision)
    assert not store.rows("SELECT * FROM approvals")
