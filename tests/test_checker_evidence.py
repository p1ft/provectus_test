import copy
import json
import sqlite3

import pytest
from conftest import SyntheticTransport
from test_lifecycle import supported_check

from workspace.gemini import Gemini
from workspace.service import ReviewBlocked, Service
from workspace.store import Store


@pytest.fixture
def checker_conflict(store):
    document = {"id": "SUPPORT-WORKING", "version": 1, "date": "2026-10-09",
                "status": "current", "supersedes": None,
                "passages": [{"id": "SUPPORT-WORKING:p1",
                              "text": "Email support is available Saturday and Sunday only."}]}
    store.update_source(document)
    draft = {"question_id": "Q3", "disposition": "answered",
             "answer": "Monday to Friday, 09:00 to 17:00 UTC.",
             "citations": [{"passage_id": "SUPPORT-v1:p1",
                            "excerpt": "Email support is available Monday to Friday, 09:00 to 17:00 UTC."}],
             "unresolved_reason": "", "conflicts": []}
    check = supported_check(draft)
    check["conflicts"] = [{"passage_ids": ["SUPPORT-v1:p1", "SUPPORT-WORKING:p1"],
                           "explanation": "Two independent current sources give incompatible support days."}]
    return document, draft, check


@pytest.mark.parametrize("edited", [False, True])
def test_checker_only_conflict_preserves_evidence_and_blocks_approval(store, checker_conflict, edited):
    document, draft, check = checker_conflict
    service = Service(store, Gemini(store, SyntheticTransport(draft, check)))
    if edited:
        revision = service.edit("Q3", draft)
        service.gemini.transport = SyntheticTransport(check)
        assert service.validate(revision)
    else:
        revision = service.generate("Q3")
    stored = store.revision(revision)
    assert stored["draft"].conflicts == []
    evidence = next(c for c in stored["citations"] if c["passage_id"] == "SUPPORT-WORKING:p1")
    assert evidence["role"] == "conflicting"
    assert evidence["excerpt"] == document["passages"][0]["text"]
    assert json.loads(evidence["document"]) == document
    assert evidence["source_revision"] == store.snapshot()["revision_ids"][document["id"]]
    validation = store.one("SELECT * FROM answer_validations WHERE id=?", (evidence["validation_id"],))
    assert "Unresolved source conflict" in validation["errors"]
    assert store.question("Q3")["status"] == "unresolved"
    with pytest.raises(ReviewBlocked, match="validation"):
        service.approve(revision, reviewer_name="Synthetic reviewer", reviewer_role="Support reviewer",
                        evidence_confirmed=True)
    with pytest.raises(sqlite3.IntegrityError, match="Immutable history"):
        store.db.execute("UPDATE validation_evidence SET excerpt='changed'")
    store.db.rollback()
    # A second checker run cannot erase the earlier captured finding.
    service.gemini.transport = SyntheticTransport(supported_check(draft))
    service.validate(revision)
    assert store.revision(revision)["checker_evidence"] == stored["checker_evidence"]
    changed = copy.deepcopy(document)
    changed["version"] = 2
    changed["passages"][0]["text"] = "Email support is available Monday to Friday."
    store.update_source(changed)
    service.validate(revision)
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    reopened = Store(path)
    try:
        assert reopened.revision(revision)["checker_evidence"] == stored["checker_evidence"]
    finally:
        reopened.close()


def test_invalid_checker_conflict_reference_stays_a_finding(store, checker_conflict):
    _, draft, check = checker_conflict
    check["conflicts"][0]["passage_ids"][1] = "ABSENT:p1"
    service = Service(store, Gemini(store, SyntheticTransport(draft, check)))
    revision = service.generate("Q3")
    validation = store.one("SELECT * FROM answer_validations WHERE answer_revision=?", (revision,))
    assert "Invalid conflicting passage references" in validation["errors"]
    assert all(c["passage_id"] != "ABSENT:p1" for c in store.revision(revision)["citations"])
