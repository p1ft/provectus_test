"""Explicit review actions and eligible exact-question approval reuse."""

import json

from workspace.evidence import (
    passage_index,
    reference_errors,
    replaced_evidence,
    semantic_errors,
)
from workspace.gemini import ModelFailure
from workspace.schemas import Draft, json_text
from workspace.store import now


class ReviewBlocked(ValueError):
    pass


def same_sources(left, right):
    return (left["fingerprint"] == right["fingerprint"]
            and left["revision_ids"] == right["revision_ids"])


class Service:
    def __init__(self, store, gemini):
        self.store = store
        self.gemini = gemini

    def _question_contract(self, question_id):
        row = self.store.question(question_id)
        return {k: row[k] for k in ("id", "text", "topic")}

    def _invalidate_stale(self, snapshot):
        stale = self.store.rows(
            "SELECT q.id,a.id AS approval FROM questions q JOIN approvals a "
            "ON a.id=q.active_approval WHERE a.invalidation_reason IS NOT NULL "
            "OR a.source_fingerprint != ?", (snapshot["fingerprint"],))
        for row in stale:
            self.store.db.execute("UPDATE approvals SET invalidation_reason=COALESCE("
                                  "invalidation_reason,'Source corpus changed; fresh review required') "
                                  "WHERE id=?", (row["approval"],))
            self.store.db.execute("UPDATE questions SET status='review_required' WHERE id=?",
                                  (row["id"],))

    def refresh(self):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self._invalidate_stale(self.store.snapshot())

    def _append(self, draft, snapshot, origin, note="", draft_run=None):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            if not same_sources(self.store.snapshot(), snapshot):
                raise ReviewBlocked("Sources changed while drafting; retry")
            question = self.store.question(draft.question_id)
            revision_id = self.store.db.execute(
                "INSERT INTO answer_revisions(question_id,draft,origin,parent_revision,draft_run,"
                "note,source_snapshot,source_fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (draft.question_id, draft.model_dump_json(), origin, question["working_revision"],
                 draft_run, note, json_text(snapshot), snapshot["fingerprint"], now())
            ).lastrowid
            index = passage_index(snapshot)
            evidence = [{**c.model_dump(), "role": "supporting"} for c in draft.citations]
            evidence.extend(replaced_evidence(draft, snapshot))
            # Also preserve all model-identified conflicts, even unresolved ones.
            for conflict in draft.conflicts:
                for passage_id in conflict.passage_ids:
                    if passage_id in index:
                        evidence.append({"passage_id": passage_id,
                                         "excerpt": index[passage_id][1]["text"],
                                         "role": "conflicting"})
            for citation in evidence:
                if citation["passage_id"] not in index:
                    continue  # Invalid references remain in the draft and its findings.
                document = index[citation["passage_id"]][0]
                self.store.db.execute("INSERT OR IGNORE INTO citations VALUES (?,?,?,?,?)",
                                      (revision_id, snapshot["revision_ids"][document["id"]],
                                       citation["passage_id"], citation["excerpt"], citation["role"]))
            self.store.db.execute("UPDATE questions SET working_revision=?,last_error=NULL,"
                                  "status=CASE WHEN active_approval IS NULL THEN 'unresolved' "
                                  "ELSE status END WHERE id=?", (revision_id, draft.question_id))
            if origin == "reviewer_unresolved":
                if question["active_approval"] is not None:
                    self.store.db.execute("UPDATE approvals SET invalidation_reason="
                                          "'Reviewer left question unresolved' WHERE id=?",
                                          (question["active_approval"],))
                self.store.db.execute("UPDATE questions SET active_approval=NULL,status='unresolved' "
                                      "WHERE id=?", (draft.question_id,))
        return revision_id

    def _record_validation(self, revision_id, snapshot, errors, check_run, conflicts=()):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            self._invalidate_stale(self.store.snapshot())
            if not same_sources(self.store.snapshot(), snapshot):
                errors = [*errors, "Sources changed during validation"]
            validation_id = self.store.db.execute(
                "INSERT INTO answer_validations(answer_revision,check_run,source_fingerprint,"
                "errors,created_at) VALUES (?,?,?,?,?)",
                (revision_id, check_run, snapshot["fingerprint"], json_text(errors), now())
            ).lastrowid
            index = passage_index(snapshot)
            for conflict in conflicts:
                for passage_id in conflict.passage_ids:
                    if passage_id in index:
                        document, passage = index[passage_id]
                        self.store.db.execute(
                            "INSERT OR IGNORE INTO validation_evidence VALUES (?,?,?,?,?)",
                            (validation_id, snapshot["revision_ids"][document["id"]], passage_id,
                             passage["text"], conflict.explanation))
            revision = self.store.revision(revision_id)
            self.store.db.execute("UPDATE questions SET status=? WHERE id=? "
                                  "AND working_revision=? AND active_approval IS NULL",
                                  ("unresolved" if errors else "answered",
                                   revision["question_id"], revision_id))
        return validation_id, errors

    def _check(self, draft, snapshot):
        errors = reference_errors(draft, draft.question_id, snapshot)
        if errors:
            return errors, None, ()
        check, run_id = self.gemini.run("check", self._question_contract(draft.question_id),
                                         snapshot, draft)
        return semantic_errors(draft, check, snapshot), run_id, check.conflicts

    def generate(self, question_id):
        self.refresh()
        question = self._question_contract(question_id)
        snapshot = self.store.snapshot()
        try:
            draft, run_id = self.gemini.run("draft", question, snapshot)
            if draft.question_id != question_id:
                self.store.record_failure(question_id, "Response question ID does not match")
                return None
            errors, check_run, conflicts = self._check(draft, snapshot)
        except ModelFailure as exc:
            self.store.record_failure(question_id, str(exc))
            return None
        revision_id = self._append(draft, snapshot, self.gemini.transport.origin,
                                    draft_run=run_id)
        self._record_validation(revision_id, snapshot, errors, check_run, conflicts)
        return revision_id

    def edit(self, question_id, value, *, note=""):
        draft = Draft.model_validate(value)
        if draft.question_id != question_id:
            raise ValueError("Edited question ID does not match")
        self.refresh()
        return self._append(draft, self.store.snapshot(), "reviewer_edit", note)

    def validate(self, revision_id):
        revision = self.store.revision(revision_id)
        draft = revision["draft"]
        snapshot = self.store.snapshot()
        conflicts = ()
        if not same_sources(revision["source_snapshot"], snapshot):
            errors, run_id = ["Sources changed; create a fresh reviewed revision"], None
        else:
            try:
                errors, run_id, conflicts = self._check(draft, snapshot)
            except ModelFailure as exc:
                errors, run_id = [str(exc)], exc.run_id
                self.store.record_failure(draft.question_id, str(exc))
        return self._record_validation(revision_id, snapshot, errors, run_id, conflicts)[1]

    def approve(self, revision_id, *, reviewer_name, reviewer_role, evidence_confirmed, note=""):
        if evidence_confirmed is not True or not reviewer_name.strip():
            raise ReviewBlocked("Approval requires reviewer identity and explicit evidence confirmation")
        self.refresh()
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            snapshot = self.store.snapshot()
            revision = self.store.revision(revision_id)
            question = self.store.question(revision["question_id"])
            if reviewer_role != question["reviewer"]:
                raise ReviewBlocked("Reviewer role must match the topic mapping")
            if question["working_revision"] != revision_id:
                raise ReviewBlocked("Approve only the currently reviewed revision")
            validation = self.store.one("SELECT * FROM answer_validations "
                                        "WHERE answer_revision=? ORDER BY id DESC LIMIT 1",
                                        (revision_id,))
            if (validation is None or json.loads(validation["errors"])
                    or validation["check_run"] is None):
                raise ReviewBlocked("Exact wording must pass evidence validation before approval")
            if (not same_sources(revision["source_snapshot"], snapshot)
                    or validation["source_fingerprint"] != snapshot["fingerprint"]):
                raise ReviewBlocked("Sources changed; fresh review and validation required")
            errors = reference_errors(revision["draft"], question["id"], snapshot)
            if errors:
                raise ReviewBlocked("; ".join(errors))
            approval_id = self.store.db.execute(
                "INSERT INTO approvals(answer_revision,validation_id,reviewer_name,reviewer_role,"
                "note,source_fingerprint,created_at) VALUES (?,?,?,?,?,?,?)",
                (revision_id, validation["id"], reviewer_name.strip(), reviewer_role, note,
                 snapshot["fingerprint"], now())
            ).lastrowid
            self.store.db.execute("UPDATE questions SET active_approval=?,status='approved',"
                                  "last_error=NULL WHERE id=?", (approval_id, question["id"]))
        return approval_id

    def leave_unresolved(self, question_id, note):
        if not note.strip():
            raise ReviewBlocked("An unresolved decision requires a note")
        self.refresh()
        question = self.store.question(question_id)
        if question["working_revision"] is None:
            value = {"question_id": question_id, "disposition": "unresolved", "answer": "",
                     "citations": [], "conflicts": [], "unresolved_reason": note}
        else:
            value = self.store.revision(question["working_revision"])["draft"].model_dump()
            value.update(disposition="unresolved", unresolved_reason=note)
        return self._append(Draft.model_validate(value), self.store.snapshot(),
                            "reviewer_unresolved", note)

    def reuse(self, exact_text):
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            snapshot = self.store.snapshot()
            self._invalidate_stale(snapshot)
            approval = self.store.one(
                "SELECT a.*,q.id AS question_id FROM questions q JOIN approvals a "
                "ON a.id=q.active_approval WHERE q.text=? AND q.status='approved' "
                "AND a.invalidation_reason IS NULL AND a.source_fingerprint=? "
                "ORDER BY a.id DESC LIMIT 1", (exact_text, snapshot["fingerprint"]))
            if approval is None:
                return {"eligible": False, "reason": "No eligible approval for this exact question"}
            revision = self.store.revision(approval["answer_revision"])
            errors = reference_errors(revision["draft"], approval["question_id"], snapshot)
            if errors:
                return {"eligible": False, "reason": "; ".join(errors)}
            return {"eligible": True, "answer": revision["draft"].answer,
                    "approval": approval, "evidence": revision["citations"]}

    def queue(self):
        self.refresh()
        rows = self.store.rows("SELECT q.*,t.reviewer,a.answer_revision AS approved_revision "
                               "FROM questions q JOIN topics t ON t.id=q.topic "
                               "LEFT JOIN approvals a ON a.id=q.active_approval ORDER BY q.id")
        counts = dict.fromkeys(("pending", "answered", "unresolved", "approved", "review_required"), 0)
        for row in rows:
            counts[row["status"]] += 1
            row["pending_edit"] = (row["status"] == "approved"
                                   and row["working_revision"] != row["approved_revision"])
        return rows, counts
