"""Local evidence workspace. Model work occurs only on explicit form/button actions."""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from workspace.gemini import (
    REAL_REPLAY_DIRECTORY,
    REAL_REPLAY_MODEL,
    FileReplayTransport,
    Gemini,
    LiveTransport,
)
from workspace.schemas import Draft
from workspace.service import ReviewBlocked, Service, same_sources
from workspace.store import Store

ROOT = Path(__file__).resolve().parent
STATUS_LABELS = {"pending": "To draft", "answered": "Awaiting approval", "unresolved": "Unresolved",
                 "approved": "Approved", "review_required": "Needs fresh review"}


def changed(message):
    st.session_state["flash"] = message
    st.rerun()


def evidence_view(citations):
    grouped = {}
    for citation in citations:
        key = (citation["source_revision"], citation["passage_id"])
        group = grouped.setdefault(key, {"citation": citation, "roles": set()})
        group["roles"].add(citation["role"])
        if citation["role"] == "supporting":
            group["citation"] = citation
    for group in grouped.values():
        citation = group["citation"]
        document = json.loads(citation["document"])
        with st.container(border=True):
            roles = ", ".join(role for role in ("supporting", "replaced", "conflicting") if role in group["roles"])
            st.caption(f"{roles.capitalize()} · {citation['passage_id']} · "
                       f"version {document['version']}")
            passage = next(p for p in document["passages"] if p["id"] == citation["passage_id"])
            st.text(passage["text"])
            if citation["excerpt"] != passage["text"]:
                with st.expander("Cited excerpt"):
                    st.text(citation["excerpt"])


def source_controls(store):
    with st.expander("Edit or remove a working source"):
        st.caption("Changes affect working sources only. Every corpus change requires fresh approval.")
        snapshot = store.snapshot()
        selected = st.selectbox("Source", [d["id"] for d in snapshot["documents"]], key="source")
        document = next(d for d in snapshot["documents"] if d["id"] == selected)
        revision = snapshot["revision_ids"][selected]
        available = snapshot["availability"][selected]
        origin = store.one("SELECT origin FROM source_revisions WHERE id=?", (revision,))["origin"]
        st.caption(f"{origin.capitalize()} source · {'available' if available else 'unavailable'}")
        with st.form(f"source_update_{revision}_{available}"):
            content = st.text_area("Document JSON (edit or add a new document ID)",
                                   json.dumps(document, indent=2), height=280, key=f"source_json_{revision}")
            consistent = st.checkbox("This working source follows the exercise rules", key="consistent")
            if st.form_submit_button("Save working source", key="save_source"):
                if not consistent:
                    st.error("Confirm that the working source follows the exercise rules.")
                else:
                    try:
                        store.update_source(json.loads(content))
                        changed("Working source saved. Affected approvals require fresh review.")
                    except (ValueError, ValidationError) as exc:
                        st.error(f"Source update rejected: {exc}")
        with st.form(f"remove_source_{selected}"):
            confirmed = st.checkbox("Mark this source unavailable", key="remove_confirm")
            if st.form_submit_button("Remove source", key="remove_source", disabled=not available):
                if not confirmed:
                    st.error("Confirm source removal.")
                else:
                    store.remove_source(selected)
                    changed("Source unavailable. Old evidence is retained; reuse is blocked.")


def generate_answer(service, question_id, enabled, label="Create answer"):
    if st.button(label, key="generate", disabled=not enabled, type="primary"):
        try:
            with st.spinner("Drafting and checking evidence…"):
                revision = service.generate(question_id)
            if revision is not None:
                changed("Draft saved. Review its evidence before approval.")
            else:
                st.rerun()
        except ReviewBlocked as exc:
            st.error(str(exc))


def edit_answer(service, question_id, revision, snapshot, enabled):
    draft = revision["draft"]
    passages = [p["id"] for d in snapshot["documents"] for p in d["passages"]]
    with st.form(f"edit_{revision['id']}"):
        answer = st.text_area("Answer wording", draft.answer, key=f"answer_{revision['id']}", height=120)
        st.caption("Choose source passages and copy exact excerpts. Saving creates an unapproved draft.")
        citations = st.data_editor(
            pd.DataFrame([c.model_dump() for c in draft.citations],
                         columns=["passage_id", "excerpt"], dtype=str), hide_index=True, num_rows="dynamic",
            column_order=["passage_id", "excerpt"], key=f"citations_{revision['id']}",
            column_config={
                "passage_id": st.column_config.SelectboxColumn("Source passage", options=passages, required=True),
                "excerpt": st.column_config.TextColumn("Exact excerpt", required=True),
            })
        disposition = st.selectbox("Answer status", ["answered", "unresolved"],
                                   index=0 if draft.disposition == "answered" else 1,
                                   format_func=lambda s: "Ready for review" if s == "answered" else "Unresolved",
                                   key=f"disposition_{revision['id']}")
        reason = st.text_input("Reason if unresolved", draft.unresolved_reason, key=f"reason_{revision['id']}")
        with st.expander("Optional edit note"):
            edit_note = st.text_input("Edit note", key="edit_note")
        if st.form_submit_button("Save and check" if enabled else "Save draft", key="save_edit", type="primary"):
            try:
                value = draft.model_dump()
                value.update(answer=answer, citations=citations.to_dict("records"), disposition=disposition,
                             unresolved_reason=reason)
                edited = service.edit(question_id, Draft.model_validate(value), note=edit_note)
                if enabled:
                    with st.spinner("Checking edited wording…"):
                        findings = service.validate(edited)
                    changed("Edit saved. Evidence needs review." if findings else
                            "Edit checked. Review its evidence and approve explicitly.")
                else:
                    changed("Edit saved as a draft. Evidence checking is unavailable in this mode.")
            except (ValueError, ValidationError) as exc:
                st.error(f"Edit rejected: {exc}")


def review_question(service, question_id, model_actions_enabled):
    store = service.store
    question = store.question(question_id)
    snapshot = store.snapshot()
    confirmation_token = (question_id, question["working_revision"], snapshot["fingerprint"],
                          json.dumps(snapshot["revision_ids"], sort_keys=True))
    if st.session_state.get("confirmation_token") != confirmation_token:
        st.session_state["evidence_confirmed"] = False
        st.session_state["confirmation_token"] = confirmation_token
        st.session_state["review_action"] = None
    active_approval = store.one("SELECT * FROM approvals WHERE id=?", (question["active_approval"],))
    st.subheader(question["text"])
    st.caption(f"{question_id} · {question['reviewer']} · {STATUS_LABELS[question['status']]}")
    if question["last_error"]:
        st.error(question["last_error"])
    if question["status"] == "review_required":
        st.warning("Sources changed or became unavailable. Reuse is blocked until fresh review and approval.")
    if question["working_revision"] is None or question["status"] == "review_required" or question["last_error"]:
        generate_answer(service, question_id, model_actions_enabled,
                        "Create answer" if question["working_revision"] is None else "Create fresh draft")
    ready = approved_exact = False
    if question["working_revision"] is None:
        st.caption("Create a draft to review its answer and supporting passages.")
        revision = None
    else:
        revision = store.revision(question["working_revision"])
        draft = revision["draft"]
        validation = store.one("SELECT * FROM answer_validations WHERE answer_revision=? "
                               "ORDER BY id DESC LIMIT 1", (revision["id"],))
        errors = json.loads(validation["errors"]) if validation else []
        current = same_sources(revision["source_snapshot"], snapshot)
        ready = bool(validation and not errors and validation["check_run"] and current
                     and draft.disposition == "answered")
        approved_exact = bool(ready and active_approval and not active_approval["invalidation_reason"]
                              and active_approval["answer_revision"] == revision["id"])
        left, right = st.columns([1, 1], gap="large")
        with left:
            st.markdown("**Approved answer**" if approved_exact else "**Draft answer**")
            st.text(draft.answer or "No supported answer proposed.")
            origin = {"replay_real": "Saved real response", "replay_synthetic": "Synthetic test response",
                      "synthetic": "Synthetic test response", "live": "Live model response",
                      "reviewer_edit": "Reviewer edit", "reviewer_unresolved": "Reviewer decision"}
            st.caption(origin[revision["origin"]])
            findings = list(dict.fromkeys([draft.unresolved_reason, *errors]))
            if any(findings):
                st.warning("\n\n".join(f for f in findings if f))
            if revision["note"]:
                st.info(revision["note"])
            if validation is None:
                st.caption("Evidence has not been checked for this wording.")
            elif not current:
                st.warning("These passages belong to an older source snapshot. Create a fresh draft or save a fresh edit.")
            elif approved_exact:
                st.caption(f"Approved by {active_approval['reviewer_name']} · {active_approval['created_at']}")
            elif ready:
                st.caption("Evidence checks passed · Awaiting human approval")
        with right:
            st.markdown("**Sources**")
            evidence_view(revision["citations"])
            if not revision["citations"]:
                st.caption("No supporting passages cited.")
            for conflict in draft.conflicts:
                st.caption(conflict.explanation)
            for explanation in dict.fromkeys(e["explanation"] for e in revision["checker_evidence"]):
                if explanation not in {c.explanation for c in draft.conflicts}:
                    st.caption(f"Checker conflict · {explanation}")
        if active_approval and active_approval["answer_revision"] != revision["id"]:
            approval = active_approval
            approved = store.revision(approval["answer_revision"])
            st.info("The pending edit is a draft. Reuse returns only eligible approved wording.")
            with st.expander("Previously approved answer"):
                st.text(approved["draft"].answer)
                st.caption(f"{approval['reviewer_name']} · {approval['reviewer_role']} · "
                           f"{approval['created_at']}")
                if approval["note"]:
                    st.text(approval["note"])
                if approval["invalidation_reason"]:
                    st.warning(approval["invalidation_reason"])
                evidence_view(approved["citations"])
        if (not ready and current and draft.disposition == "answered" and revision["origin"] != "reviewer_unresolved"
                and st.button("Retry evidence check", key="validate", disabled=not model_actions_enabled)):
            with st.spinner("Checking evidence…"):
                findings = service.validate(revision["id"])
            changed("Evidence needs review." if findings else "Evidence checked. Human approval is required.")
    actions = st.columns(3 if revision is not None else 1)
    if revision is not None:
        if actions[0].button("Approve answer", key="open_approval", type="primary",
                             disabled=not ready or approved_exact):
            st.session_state["review_action"] = "approve"
        if actions[1].button("Edit answer", key="edit"):
            st.session_state["review_action"] = "edit"
    if actions[-1].button("Leave unresolved", key="open_unresolved"):
        st.session_state["review_action"] = "unresolved"
    action = st.session_state.get("review_action")
    if action == "edit" and revision is not None:
        edit_answer(service, question_id, revision, snapshot, model_actions_enabled)
    elif action == "approve" and ready and not approved_exact:
        with st.form(f"approve_{revision['id']}"):
            name = st.text_input("Reviewer name", key="reviewer")
            st.caption(f"Required role: {question['reviewer']}")
            with st.expander("Optional approval note"):
                note = st.text_input("Approval note", key="approval_note")
            confirmed = st.checkbox("I reviewed the displayed evidence and it supports this exact wording",
                                    key="evidence_confirmed")
            if st.form_submit_button("Confirm approval", key="approve", type="primary"):
                try:
                    service.approve(revision["id"], reviewer_name=name, reviewer_role=question["reviewer"],
                                    evidence_confirmed=confirmed, note=note)
                    st.session_state["review_action"] = None
                    changed("Approval saved for the exact wording and source snapshot.")
                except ReviewBlocked as exc:
                    st.error(str(exc))
    elif action == "unresolved":
        with st.form(f"unresolved_{question_id}"):
            note = st.text_area("Unresolved review note", key=f"unresolved_note_{question_id}")
            st.caption(f"Review route: {question['reviewer']}")
            if st.form_submit_button("Save unresolved note", key="leave_unresolved", type="primary"):
                try:
                    service.leave_unresolved(question_id, note)
                    changed("Unresolved decision saved. No approved answer is eligible for reuse.")
                except ReviewBlocked as exc:
                    st.error(str(exc))
    if action is not None and st.button("Cancel", key="cancel_review"):
        st.session_state["review_action"] = None
        st.rerun()


def main():
    st.set_page_config(page_title="Evidence Review", layout="wide")
    verification = os.environ.get("WORKSPACE_VERIFICATION") == "1"
    default_db = "artifacts/verification/browser.sqlite3" if verification else "data/workspace.sqlite3"
    path = Path(os.environ.get("WORKSPACE_DB", str(ROOT / default_db))).resolve()
    if verification and not any(path.is_relative_to(ROOT / p) for p in ("artifacts/verification", ".tmp")):
        st.error("Synthetic verification requires an isolated database under artifacts/verification or .tmp.")
        st.stop()
    store = Store(path)
    try:
        seed_path = Path(os.environ.get("WORKSPACE_SEED", str(ROOT / "tasks/evidence/seed.json")))
        store.import_seed(json.loads(seed_path.read_text(encoding="utf-8")))
        st.subheader("Questionnaire review")
        if verification:
            st.warning("Synthetic verification only. Approvals here are demonstrations, not working approvals.")
        if "flash" in st.session_state:
            st.success(st.session_state.pop("flash"))
        modes = ["Replay of real run", "Live Gemini"]
        if verification:
            modes.insert(0, "Synthetic test replay")
        queue_panel = st.sidebar.container()
        with st.sidebar.expander("Model settings"):
            mode = st.selectbox("Response mode", modes, key="mode")
        live_allowed = os.environ.get("WORKSPACE_ALLOW_LIVE") == "1"
        if mode == "Live Gemini" and not live_allowed:
            st.warning("Live Gemini is blocked pending approval of the external payload and destination.")
        capture_dir = Path(os.environ.get("WORKSPACE_REPLAY_DIR", str(ROOT / (
            "artifacts/verification/synthetic-captures" if mode == "Synthetic test replay"
            else REAL_REPLAY_DIRECTORY))))
        transport = LiveTransport() if mode == "Live Gemini" else FileReplayTransport(
            capture_dir, synthetic=mode == "Synthetic test replay")
        model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash" if mode == "Synthetic test replay"
                               else REAL_REPLAY_MODEL)
        service = Service(store, Gemini(store, transport, model=model))
        st.caption(f"{mode} · {model}")
        default_replay = (mode == "Replay of real run"
                          and capture_dir.resolve() == (ROOT / REAL_REPLAY_DIRECTORY).resolve())
        if mode == "Replay of real run" and not any(capture_dir.glob("*.json")):
            st.warning("No saved real captures in this directory. Replay is unavailable.")
        rows, counts = service.queue()
        with queue_panel:
            st.subheader("Questions")
            st.caption(" · ".join(f"{count} {STATUS_LABELS[status].lower()}" for status, count in counts.items()))
            status = st.selectbox("Status filter", ["All", *counts], key="status_filter",
                                  format_func=lambda s: STATUS_LABELS.get(s, s))
            with st.expander("Filter by reviewer"):
                reviewer = st.selectbox("Reviewer filter", ["All", *sorted({r['reviewer'] for r in rows})],
                                        key="reviewer_filter")
            visible = [r for r in rows if (status == "All" or r["status"] == status)
                       and (reviewer == "All" or r["reviewer"] == reviewer)]
            by_id = {r["id"]: r for r in visible}
            question_id = None
            if visible:
                choices = list(by_id)
                if st.session_state.get("question") not in choices:
                    st.session_state["question"] = choices[0]
                question_id = st.radio("Question", choices, key="question", label_visibility="collapsed",
                                       format_func=lambda q: f"{q} · {by_id[q]['text']}",
                                       captions=[STATUS_LABELS[r["status"]] + (" · Pending edit" if r["pending_edit"] else "")
                                                 for r in visible])
            else:
                st.info("No questions match these filters.")
            if default_replay:
                st.caption("Saved responses: Q1–Q8, including the Q1 demonstration correction.")
        review, reuse, sources, details = st.tabs(
            ["Review", "Reuse approved answer", "Sources", "History & diagnostics"],
            key="workspace_tabs", on_change="rerun")
        enabled = mode != "Live Gemini" or live_allowed
        with review:
            if question_id is not None:
                review_question(service, question_id, enabled)
            else:
                st.info("Select a different filter to review a question.")
        with reuse:
            st.caption("Repeat a question exactly to retrieve its approved wording, reviewer and sources.")
            with st.form("reuse"):
                exact = st.text_input("Repeat an exact question", key="repeat_text")
                if st.form_submit_button("Look up approved answer", key="reuse"):
                    st.session_state["repeat_lookup"] = exact
            if "repeat_lookup" in st.session_state:
                result = service.reuse(st.session_state["repeat_lookup"])
                if result["eligible"]:
                    st.success("Eligible approved answer")
                    st.text(result["answer"])
                    approval = result["approval"]
                    st.caption(f"{approval['reviewer_name']} · {approval['reviewer_role']} · {approval['created_at']}")
                    evidence_view(result["evidence"])
                else:
                    st.warning(result["reason"])
        with sources:
            st.caption("Working documents. Source changes require fresh review; historical evidence is retained.")
            snapshot = store.snapshot()
            for document in snapshot["documents"]:
                with st.expander(f"{document['id']} · version {document['version']}"):
                    st.caption(f"Replaces: {document['supersedes'] or 'None'} · "
                               f"{'Available' if snapshot['availability'][document['id']] else 'Unavailable'}")
                    for passage in document["passages"]:
                        st.caption(passage["id"])
                        st.text(passage["text"])
            source_controls(store)
        with details:
            with st.expander("Model and replay details"):
                st.caption(f"{mode} · {model} · {capture_dir.as_posix()}")
                if mode == "Replay of real run":
                    st.caption("Replay cannot call the API. Novel edits or changed sources need matching saved checks.")
                    if default_replay:
                        st.info("Saved real replay covers Q1–Q8 and the documented Q1 correction. "
                                "Q2 remains unresolved. Other new wording needs a matching saved check.")
                    st.caption("Override the saved session with WORKSPACE_REPLAY_DIR and its GEMINI_MODEL.")
            if question_id is not None:
                question = store.question(question_id)
                st.caption(f"History for {question_id}")
                if question["working_revision"] is not None:
                    revision = store.revision(question["working_revision"])
                    if question["status"] != "review_required" and not question["last_error"]:
                        generate_answer(service, question_id, enabled, "Create another draft")
                    with st.expander("Complete checker findings"):
                        for validation in store.rows("SELECT * FROM answer_validations WHERE answer_revision=? "
                                                     "ORDER BY id DESC", (revision["id"],)):
                            st.caption(f"Validation {validation['id']} · {validation['created_at']}")
                            st.code(validation["errors"], language="json")
                            if validation["check_run"]:
                                run = store.one("SELECT * FROM model_runs WHERE id=?", (validation["check_run"],))
                                st.caption(f"Check run {run['id']} · {run['origin']} · original run {run['original_run']}")
                                st.code(run["raw_response"] or run["error"], language="json")
                if question["active_approval"]:
                    approval = store.one("SELECT * FROM approvals WHERE id=?", (question["active_approval"],))
                    with st.expander("Approval record"):
                        st.json(approval)
                for row in store.rows("SELECT id,origin,note,created_at FROM answer_revisions "
                                      "WHERE question_id=? ORDER BY id DESC", (question_id,)):
                    with st.expander(f"Revision {row['id']} · {row['created_at']} · {row['origin']}"):
                        historical = store.revision(row["id"])
                        st.text(historical["draft"].answer)
                        st.caption(row["note"])
                        evidence_view(historical["citations"])
    finally:
        store.close()


if __name__ == "__main__":
    main()
