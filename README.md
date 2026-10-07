# Questionnaire Evidence & Review Workspace

Junior AI Engineer test assignment, variant C. This repository contains the original evidence starter data and a small Codex workflow foundation; the application has not been implemented.

## Starter data and preparation scope

`tasks/evidence/` was copied unchanged from `client-ai-starter-pack (1).zip`, under `client-ai-starter-pack/tasks/evidence/`:

- `domain.md`: authoritative fictional exercise rules.
- `seed.json`: five documents, eight questions, passage IDs, versions, explicit supersession, and topic-to-reviewer mapping.
- `expected-seed-results.json`: independent supplied expectations for Q1, Q2, Q3, approval/reuse, and source changes.
- `document.template.json`: the supplied document format.

The assignment brief was read from `client-ai-project-research.html`, Alternative C. Only the four evidence files were imported. No generated data, random seed, other assignments, or changes to supplied expectations were added. The imported files were checked byte-for-byte against the archive.

Only supplied product passages count as evidence. Undocumented features remain unknown; authority follows explicit `supersedes`, not date order. Q1 must use `EXPORT-v2:p1` and show the conflict with `EXPORT-v1:p1`; Q2 remains unresolved with the Product reviewer; Q3 uses `SUPPORT-v1:p1` for Monday to Friday, 09:00–17:00 UTC. Unapproved edits remain drafts; approved reuse requires exact question matching and current referenced versions. Source changes require review, and replaced text stays visible. No additional domain rules were introduced.

## Selected stack for implementation

Python is required by the user; LangChain and Gemini API are the preferred model integration. The following is a selected implementation plan, not installed or exercised application code:

- **Python with `venv` and `pip`**: one language for data loading, evidence checks, persistence, model calls, and UI. Exact Python and dependency versions will be pinned and verified when implementation begins.
- **Streamlit**: a single local browser workspace with status filters, counts, side-by-side answer/evidence, and explicit reviewer edit/approve forms. This avoids maintaining a separate frontend and API within the one-day limit. Model calls should follow an explicit action, not ordinary widget reruns.
- **SQLite through Python's `sqlite3`**: durable drafts, evidence and source versions, reviewer edits, approval records, and exact-match reuse. The reviewer queue is a filtered set of persisted questions; it needs no background worker or message broker. Streamlit Session State can hold temporary UI selections, but cannot satisfy reload persistence on its own ([Streamlit documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)). SQLite needs no separate database server ([Python documentation](https://docs.python.org/3/library/sqlite3.html)).
- **Gemini API through `langchain-google-genai`**: use the LangChain chat-model integration for a direct request with the five documents and structured draft output. This keeps the user's preference without adding agents, LangGraph, embeddings, or a vector database. The integration is documented in the [official LangChain Google repository](https://github.com/langchain-ai/langchain-google). The actual Gemini model and settings remain unselected until access is confirmed; save them with real responses for replay without an API key.

A direct Google Gen AI SDK call would reduce dependencies further; the selected LangChain integration adds a small adapter while preserving the requested preference. A separate FastAPI/JavaScript frontend offers more layout control but adds implementation and verification work unnecessary for this local review queue.

## Current execution status and next stage

There is no application entry point, dependency manifest, test suite, or verified install/build/test/lint/typecheck/run command yet. No dependency or configuration scaffold was added solely to represent the planned stack. The Windows `py` launcher reported no registered Python installations during preparation; this does not establish that no other Python environment exists. Runtime selection and dependency installation remain for implementation.

Next stage: implement loading, real model drafting and evidence validation, reviewer actions, durable state, exact approved reuse, and source-version review. Then exercise the five independent reference checks with expected versus observed results, including malformed model output, missing references, and API failures. Save real responses and settings, verify API-key-free replay, and complete setup instructions, a short walkthrough, the LLM usage note, and the actually used `ai-workflow/` configuration. These final-submission requirements are not completed by this preparation commit.

## Working with Codex

- `AGENTS.md` contains the standing work loop and verified project boundaries.
- `$feature-review` tests and reviews the change against the requested behavior.
- `$evidence-review` supplies the domain checklist when source evidence, approval, reuse, or source versions are involved.
- Add setup, run, and test commands here after the implementation makes them real.

The skills live in `.agents/skills/` and can be invoked by name, for example: `Use $feature-review to review the answer review screen against the starter-pack rules.` They may also be selected when their descriptions match the task.

The assignment's final submission will document the AI configuration actually used in `ai-workflow/manifest.json` and here. Those entries are intentionally deferred until there is real usage to report.
