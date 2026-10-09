import copy
import sqlite3

import pytest
from pydantic import ValidationError

from workspace.evidence import json_text, replaces, validate_seed
from workspace.store import SCHEMA, Store


def test_schema_initialization_failure_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "initialization.db"
    monkeypatch.setattr("workspace.store.SCHEMA", SCHEMA + "CREATE TABLE broken (")
    with pytest.raises(sqlite3.OperationalError):
        Store(path)
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_legacy_source_origin_migration_preserves_history(tmp_path, seed):
    path = tmp_path / "legacy.db"
    legacy_schema = SCHEMA.replace(",\n    origin TEXT NOT NULL DEFAULT 'supplied'", "")
    document = seed["documents"][0]
    with sqlite3.connect(path) as database:
        database.executescript(legacy_schema)
        database.execute("INSERT INTO sources(id) VALUES (?)", (document["id"],))
        database.execute("INSERT INTO source_revisions VALUES (1,?,?,?,?)",
                         (document["id"], json_text(document), "legacy-fingerprint", "legacy-time"))
        database.execute("UPDATE sources SET current_revision=1 WHERE id=?", (document["id"],))
    store = Store(path)
    try:
        revision = store.one("SELECT * FROM source_revisions WHERE id=1")
        assert revision["document"] == json_text(document)
        assert revision["origin"] == "supplied"
        assert store.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
            store.db.execute("DELETE FROM source_revisions WHERE id=1")
        store.db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            store.db.execute("INSERT INTO questions(id,text,topic) VALUES ('invalid','Question','absent')")
        store.db.rollback()
    finally:
        store.close()


def test_import_reload_and_authority(tmp_path, seed):
    path = tmp_path / "workspace.db"
    store = Store(path)
    assert store.import_seed(seed)
    assert len(store.snapshot()["documents"]) == 5
    assert len(store.rows("SELECT * FROM questions")) == 8
    assert store.question("Q2")["reviewer"] == "Product reviewer"
    snapshot = store.snapshot()
    assert replaces(snapshot, "EXPORT-v2", "EXPORT-v1")
    assert not replaces(snapshot, "SUPPORT-v1", "EXPORT-v1")
    with store.db:
        store.db.execute("UPDATE questions SET last_error='retained' WHERE id='Q2'")
    store.close()
    reopened = Store(path)
    assert not reopened.import_seed(seed)
    assert reopened.question("Q2")["last_error"] == "retained"
    assert reopened.snapshot() == snapshot
    reopened.close()


@pytest.mark.parametrize("case", ["type", "extra", "document", "passage", "question",
                                 "missing", "cycle", "owner", "date", "blank"])
def test_invalid_seed_is_atomic(tmp_path, seed, case):
    value = copy.deepcopy(seed)
    if case == "type":
        value["documents"][0]["version"] = "1"
    elif case == "extra":
        value["documents"][0]["unknown"] = True
    elif case == "document":
        value["documents"].append(value["documents"][0])
    elif case == "passage":
        value["documents"][1]["passages"][0]["id"] = "EXPORT-v1:p1"
    elif case == "question":
        value["questions"].append(value["questions"][0])
    elif case == "missing":
        value["documents"][1]["supersedes"] = "absent"
    elif case == "cycle":
        value["documents"][0]["supersedes"] = "EXPORT-v2"
    elif case == "owner":
        del value["owners"]["exports"]
    elif case == "date":
        value["documents"][0]["date"] = "yesterday"
    else:
        value["owners"]["exports"] = "   "
    store = Store(tmp_path / "invalid.db")
    with pytest.raises((ValueError, ValidationError)):
        store.import_seed(value)
    assert not store.rows("SELECT * FROM sources")
    assert not store.rows("SELECT * FROM topics")
    store.close()


def test_dates_and_status_do_not_define_authority(seed):
    seed["documents"][1]["supersedes"] = None
    assert not replaces(validate_seed(seed), "EXPORT-v2", "EXPORT-v1")


def test_source_history_is_immutable(store):
    with pytest.raises(sqlite3.IntegrityError, match="Immutable"):
        store.db.execute("UPDATE source_revisions SET document='{}'")
    store.db.rollback()
