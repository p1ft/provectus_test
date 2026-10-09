"""SQLite persistence. Revisions are append-only; seed import never resets state."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from workspace.evidence import validate_seed
from workspace.schemas import Document, Draft, fingerprint, json_text


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS topics (id TEXT PRIMARY KEY, reviewer TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, current_revision INTEGER REFERENCES source_revisions(id),
    available INTEGER NOT NULL CHECK(available IN (0,1)) DEFAULT 1
);
CREATE TABLE IF NOT EXISTS source_revisions (
    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    document TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'supplied'
);
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY, text TEXT NOT NULL, topic TEXT NOT NULL REFERENCES topics(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','answered','unresolved','approved','review_required')),
    working_revision INTEGER REFERENCES answer_revisions(id),
    active_approval INTEGER REFERENCES approvals(id), last_error TEXT
);
CREATE TABLE IF NOT EXISTS model_runs (
    id INTEGER PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id),
    purpose TEXT NOT NULL, request TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
    raw_response TEXT, error TEXT, origin TEXT NOT NULL, original_run INTEGER,
    metadata TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answer_revisions (
    id INTEGER PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id),
    draft TEXT NOT NULL, origin TEXT NOT NULL,
    parent_revision INTEGER REFERENCES answer_revisions(id),
    draft_run INTEGER REFERENCES model_runs(id), note TEXT NOT NULL,
    source_snapshot TEXT NOT NULL, source_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citations (
    answer_revision INTEGER NOT NULL REFERENCES answer_revisions(id),
    source_revision INTEGER NOT NULL REFERENCES source_revisions(id),
    passage_id TEXT NOT NULL, excerpt TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('supporting','replaced','conflicting')),
    PRIMARY KEY(answer_revision, passage_id, role)
);
CREATE TABLE IF NOT EXISTS answer_validations (
    id INTEGER PRIMARY KEY, answer_revision INTEGER NOT NULL REFERENCES answer_revisions(id),
    check_run INTEGER REFERENCES model_runs(id), source_fingerprint TEXT NOT NULL,
    errors TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_evidence (
    validation_id INTEGER NOT NULL REFERENCES answer_validations(id),
    source_revision INTEGER NOT NULL REFERENCES source_revisions(id),
    passage_id TEXT NOT NULL, excerpt TEXT NOT NULL, explanation TEXT NOT NULL,
    PRIMARY KEY(validation_id, passage_id, explanation)
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY, answer_revision INTEGER NOT NULL REFERENCES answer_revisions(id),
    validation_id INTEGER NOT NULL REFERENCES answer_validations(id),
    reviewer_name TEXT NOT NULL, reviewer_role TEXT NOT NULL, note TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL, invalidation_reason TEXT
);
CREATE INDEX IF NOT EXISTS question_text ON questions(text);
"""


class Store:
    def __init__(self, path="data/workspace.sqlite3"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        # Foreign-key enforcement must be enabled before the schema transaction.
        self.db.execute("PRAGMA foreign_keys = ON")
        with self.db:
            self.db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
            if "origin" not in {r["name"] for r in self.db.execute("PRAGMA table_info(source_revisions)")}:
                self.db.execute("ALTER TABLE source_revisions ADD COLUMN origin TEXT NOT NULL DEFAULT 'supplied'")
            for table in ("source_revisions", "answer_revisions", "citations",
                          "answer_validations", "validation_evidence", "model_runs"):
                for operation in ("UPDATE", "DELETE"):
                    self.db.execute(f"""CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation}
                        BEFORE {operation} ON {table} BEGIN
                        SELECT RAISE(ABORT, 'Immutable history'); END""")

    def close(self):
        self.db.close()

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def import_seed(self, value):
        seed = validate_seed(value)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.one("SELECT id FROM questions LIMIT 1") or self.one(
                "SELECT id FROM sources LIMIT 1"
            ):
                return False
            self.db.executemany("INSERT INTO topics VALUES (?,?)", seed["owners"].items())
            for doc in seed["documents"]:
                self.db.execute("INSERT INTO sources(id) VALUES (?)", (doc["id"],))
            for doc in seed["documents"]:
                revision = self.db.execute(
                    "INSERT INTO source_revisions(source_id,document,fingerprint,created_at) "
                    "VALUES (?,?,?,?)", (doc["id"], json_text(doc), fingerprint(doc), now())
                ).lastrowid
                self.db.execute("UPDATE sources SET current_revision=? WHERE id=?",
                                (revision, doc["id"]))
            self.db.executemany("INSERT INTO questions(id,text,topic) VALUES (?,?,?)",
                                [(q["id"], q["text"], q["topic"]) for q in seed["questions"]])
        return True

    def snapshot(self):
        rows = self.rows("SELECT s.id,s.available,r.id AS revision,r.document "
                         "FROM sources s JOIN source_revisions r ON r.id=s.current_revision "
                         "ORDER BY s.id")
        value = {"documents": [json.loads(r["document"]) for r in rows],
                 "availability": {r["id"]: bool(r["available"]) for r in rows},
                 "revision_ids": {r["id"]: r["revision"] for r in rows}}
        # Content, versions and availability bind checks; local row IDs do not affect replay.
        value["fingerprint"] = fingerprint({k: value[k] for k in ("documents", "availability")})
        return value

    def question(self, question_id):
        result = self.one("SELECT q.*,t.reviewer FROM questions q JOIN topics t ON t.id=q.topic "
                          "WHERE q.id=?", (question_id,))
        if result is None:
            raise ValueError("Unknown question")
        return result

    def revision(self, revision_id):
        result = self.one("SELECT * FROM answer_revisions WHERE id=?", (revision_id,))
        if result is None:
            raise ValueError("Unknown answer revision")
        result["draft"] = Draft.model_validate_json(result["draft"])
        result["source_snapshot"] = json.loads(result["source_snapshot"])
        result["citations"] = self.rows(
            "SELECT c.*,r.document FROM citations c JOIN source_revisions r "
            "ON r.id=c.source_revision WHERE c.answer_revision=?", (revision_id,))
        result["checker_evidence"] = self.rows(
            "SELECT e.*,r.document,'conflicting' AS role FROM validation_evidence e "
            "JOIN answer_validations v ON v.id=e.validation_id "
            "JOIN source_revisions r ON r.id=e.source_revision "
            "WHERE v.answer_revision=? ORDER BY e.validation_id,e.passage_id", (revision_id,))
        result["citations"].extend(result["checker_evidence"])
        return result

    def record_run(self, request, raw, error, origin, metadata, original_run=None):
        with self.db:
            return self.db.execute(
                "INSERT INTO model_runs(question_id,purpose,request,request_fingerprint,"
                "raw_response,error,origin,original_run,metadata,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (request["question"]["id"], request["purpose"], json_text(request),
                 fingerprint(request), raw, error, origin, original_run, json_text(metadata), now())
            ).lastrowid

    def record_failure(self, question_id, error):
        with self.db:
            self.db.execute("UPDATE questions SET last_error=?,status=CASE "
                            "WHEN working_revision IS NULL AND active_approval IS NULL "
                            "THEN 'unresolved' ELSE status END WHERE id=?", (error, question_id))

    def update_source(self, value):
        document = Document.model_validate(value).model_dump(mode="json")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            snapshot = self.snapshot()
            documents = [d for d in snapshot["documents"] if d["id"] != document["id"]]
            validate_seed({"documents": [*documents, document],
                           "questions": [{k: q[k] for k in ("id", "topic", "text")}
                                         for q in self.rows("SELECT * FROM questions")],
                           "owners": {r["id"]: r["reviewer"] for r in self.rows("SELECT * FROM topics")}})
            current = self.one("SELECT r.*,s.available FROM sources s JOIN source_revisions r "
                               "ON r.id=s.current_revision WHERE s.id=?", (document["id"],))
            if current and current["fingerprint"] == fingerprint(document) and current["available"]:
                return current["id"]
            self.db.execute("INSERT OR IGNORE INTO sources(id) VALUES (?)", (document["id"],))
            revision_id = self.db.execute(
                "INSERT INTO source_revisions(source_id,document,fingerprint,created_at,origin) "
                "VALUES (?,?,?,?,'working')",
                (document["id"], json_text(document), fingerprint(document), now())
            ).lastrowid
            self.db.execute("UPDATE sources SET current_revision=?,available=1 WHERE id=?",
                            (revision_id, document["id"]))
            self._invalidate_approvals("Source corpus updated; fresh review required")
        return revision_id

    def remove_source(self, source_id):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.one("SELECT * FROM sources WHERE id=?", (source_id,))
            if row is None:
                raise ValueError("Unknown source")
            if row["available"]:
                self.db.execute("UPDATE sources SET available=0 WHERE id=?", (source_id,))
                self._invalidate_approvals("Source unavailable; fresh review required")

    def _invalidate_approvals(self, reason):
        self.db.execute("UPDATE approvals SET invalidation_reason=COALESCE(invalidation_reason,?)",
                        (reason,))
        self.db.execute("UPDATE questions SET status='review_required' WHERE active_approval IS NOT NULL")
