import copy

import pytest
from test_lifecycle import approved_export

from workspace.service import ReviewBlocked
from workspace.store import Store


def test_version_update_immediately_invalidates_and_preserves_history(store, synthetic):
    service, revision = approved_export(store, synthetic)
    snapshot = store.snapshot()
    document = next(d for d in snapshot["documents"] if d["id"] == "EXPORT-v2")
    new_revision = store.update_source({**document, "version": 3})
    assert store.question("Q1")["status"] == "review_required"
    assert store.one("SELECT * FROM approvals")["invalidation_reason"]
    assert not service.reuse(store.question("Q1")["text"])["eligible"]
    assert any(c["source_revision"] == snapshot["revision_ids"]["EXPORT-v2"]
               for c in store.revision(revision)["citations"])
    assert store.one("SELECT origin FROM source_revisions WHERE id=?", (new_revision,))["origin"] == "working"
    store.update_source(document)
    assert not service.reuse(store.question("Q1")["text"])["eligible"]
    with pytest.raises(ReviewBlocked):
        service.approve(revision, reviewer_name="Reviewer", reviewer_role="Product reviewer",
                        evidence_confirmed=True)


def test_noop_and_same_version_changes(store, synthetic):
    service, _ = approved_export(store, synthetic)
    document = next(d for d in store.snapshot()["documents"] if d["id"] == "EXPORT-v2")
    original_id = store.snapshot()["revision_ids"][document["id"]]
    assert store.update_source(document) == original_id
    assert service.reuse(store.question("Q1")["text"])["eligible"]
    changed = copy.deepcopy(document)
    changed["passages"][0]["text"] += " Synthetic working clarification."
    store.update_source(changed)
    assert store.question("Q1")["status"] == "review_required"
    assert not service.reuse(store.question("Q1")["text"])["eligible"]


def test_unavailable_persists_after_reopen(store, synthetic):
    service, revision = approved_export(store, synthetic)
    store.remove_source("EXPORT-v2")
    assert store.question("Q1")["status"] == "review_required"
    assert not store.snapshot()["availability"]["EXPORT-v2"]
    assert store.revision(revision)["citations"]
    path = store.db.execute("PRAGMA database_list").fetchone()[2]
    reopened = Store(path)
    try:
        assert not reopened.snapshot()["availability"]["EXPORT-v2"]
        assert reopened.question("Q1")["status"] == "review_required"
    finally:
        reopened.close()
    assert not service.reuse(store.question("Q1")["text"])["eligible"]


@pytest.mark.parametrize("case", ["cycle", "target", "passage", "type"])
def test_invalid_update_is_atomic(store, synthetic, case):
    approved_export(store, synthetic)
    snapshot = store.snapshot()
    document = copy.deepcopy(next(d for d in snapshot["documents"] if d["id"] == "EXPORT-v1"))
    if case == "cycle":
        document["supersedes"] = "EXPORT-v2"
    elif case == "target":
        document["supersedes"] = "absent"
    elif case == "passage":
        document["passages"][0]["id"] = "SUPPORT-v1:p1"
    else:
        document["version"] = "new"
    count = len(store.rows("SELECT * FROM source_revisions"))
    with pytest.raises(ValueError):
        store.update_source(document)
    assert store.snapshot() == snapshot
    assert len(store.rows("SELECT * FROM source_revisions")) == count
    assert store.question("Q1")["status"] == "approved"


def test_working_addition_conservatively_invalidates(store, synthetic):
    approved_export(store, synthetic)
    store.update_source({"id": "WORKING-v1", "version": 1, "date": "2026-10-08",
                         "status": "current", "supersedes": None,
                         "passages": [{"id": "WORKING-v1:p1", "text": "Synthetic exercise source addition."}]})
    assert store.question("Q1")["status"] == "review_required"
    assert len(store.snapshot()["documents"]) == 6
