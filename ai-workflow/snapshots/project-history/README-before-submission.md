# Questionnaire Evidence & Review Workspace

Junior AI Engineer test assignment, variant C. The application, real seed verification and offline replay are implemented and exercised. Current Q1–Q8 real responses and the fixed Q1 reviewer correction replay exactly on `gemini-3.1-flash-lite`. Fresh Q1 draft/check and correction checking pass with zero findings. Q2 correctly remains unresolved because JSON export is undocumented; its fresh empty-answer checker passes. Earlier checker failures remain historical records.

Start with the [reviewer walkthrough](WALKTHROUGH.md) for the written presentation, credential-free setup, guided scenarios and expected results.

## Starter data and preparation scope

`tasks/evidence/` was copied unchanged from `client-ai-starter-pack (1).zip`, under `client-ai-starter-pack/tasks/evidence/`:

- `domain.md`: authoritative fictional exercise rules.
- `seed.json`: five documents, eight questions, passage IDs, versions, explicit supersession, and topic-to-reviewer mapping.
- `expected-seed-results.json`: independent supplied expectations for Q1, Q2, Q3, approval/reuse, and source changes.
- `document.template.json`: the supplied document format.

The assignment brief was read from `client-ai-project-research.html`, Alternative C. The four original evidence files were imported and checked byte-for-byte against the archive; their supplied expectations remain unchanged. A separate fixed extension under `exercises/evidence/` adds questions/passages and independent expected results, with explicitly synthetic verification. Other assignments were not imported.

Only supplied product passages count as evidence. Undocumented features remain unknown; authority follows explicit `supersedes`, not date order. Q1 must use `EXPORT-v2:p1` and show the conflict with `EXPORT-v1:p1`; Q2 remains unresolved with the Product reviewer; Q3 uses `SUPPORT-v1:p1` for Monday to Friday, 09:00–17:00 UTC. Unapproved edits remain drafts; approved reuse requires exact question matching and current referenced versions. Source changes require review, and replaced text stays visible. No additional domain rules were introduced.

## Selected stack for implementation

The application uses Python 3.12.14, Streamlit 1.65.0, SQLite 3.53.1, Pydantic v2, and the official Google Gen AI SDK. Dependencies are pinned and installed in the project-local `.venv`.

- **Python with `venv` and `pip`**: one language for data loading, evidence checks, persistence, model calls, and UI.
- **Streamlit**: a single local browser workspace with status filters, counts, side-by-side answer/evidence, and explicit reviewer edit/approve forms. This avoids maintaining a separate frontend and API within the one-day limit. Model calls should follow an explicit action, not ordinary widget reruns.
- **SQLite through Python's `sqlite3`**: durable drafts, evidence and source versions, reviewer edits, approval records, and exact-match reuse. The reviewer queue is a filtered set of persisted questions; it needs no background worker or message broker. Streamlit Session State can hold temporary UI selections, but cannot satisfy reload persistence on its own ([Streamlit documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)). SQLite needs no separate database server ([Python documentation](https://docs.python.org/3/library/sqlite3.html)).
- **Gemini API through `google-genai`**: direct synchronous requests using shared Pydantic contracts for draft/check schemas and local parsing. The adapter captures raw responses before validation and supports exact-request replay without client initialization or network fallback. The app defaults to `gemini-3.1-flash-lite`, matching the saved Q1–Q8 examples; synthetic fixtures and the earlier live verifier retain their explicitly configured model settings. See the [official SDK documentation](https://googleapis.github.io/python-genai/).

The application runs as one local Streamlit process. Model actions use native JSON structured output and occur only on explicit drafting or validation actions. The wire schema is derived from the shared Pydantic model, while extra-field rejection, bounds and cross-field checks remain enforced locally. Unsupported/complex validation constraints are kept in the Pydantic contract rather than the native wire schema. A real Flash-Lite response exposed an off-by-one claim offset: the validator now reconstructs a span only from a unique exact occurrence of the claim text, retaining the raw response and continuing to reject unsupported, invented, ambiguous or uncovered text.

## Current execution status and next stage

`app.py` shows a question queue with status/reviewer filters and compact counts on the left, with the selected answer and source passages beside each other. Review actions open one form at a time. Citations are edited as source/excerpt rows; saving an edit checks its exact wording automatically when model actions are available. Failed checks keep the edit unapproved, and blocked model actions allow saving only an unchecked draft. Separate tabs hold exact-question reuse, source controls, and history/complete checker diagnostics. Model settings are collapsed, and real replay coverage is labelled in the queue. The backend lives in `workspace/evidence.py`, `store.py`, `gemini.py`, and `service.py`. Seed import is atomic and only initializes an empty database. Revisions, evidence and checks are immutable. Edits require validation and explicit reviewer approval; confirmation resets for each wording/source snapshot. Corpus changes immediately invalidate approvals, including same-version content changes, and historical evidence remains available. Approval also binds local source revision IDs, so restoring identical text requires fresh validation.

Local checks use explicitly labelled synthetic responses in `tests/fixtures/synthetic/`. Those earlier browser demonstrations drafted/reviewed all eight questions, corrected/reused Q1, excluded pending edits, retained approvals after restart/reload, and blocked reuse after source changes/removal. The first authorized live attempt loaded the key from local `.env` only for authentication, sent only the original seed records and application schemas/prompts, and captured two successful Q1 drafts plus redacted request failures. No semantic-check response succeeded at that stage; the later successful checks and current Q1 demo are recorded separately below. The working database was untouched.

Verified PowerShell commands from the repository root:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest tests/test_lifecycle.py -q
.venv/Scripts/python.exe -m pytest -q --basetemp=.tmp/final-suite
.venv/Scripts/python.exe -m ruff check app.py workspace tests scripts
.venv/Scripts/python.exe -m compileall -q app.py workspace tests scripts
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m streamlit run app.py
.venv/Scripts/python.exe scripts/verify_reference_cases.py
.venv/Scripts/python.exe scripts/prepare_live_request.py
```

For a fresh checkout, create `.venv` with an available Python 3.12 interpreter using `python -m venv .venv`, then install the requirements. The Windows `py` launcher is not configured on the checked host. Tests keep temporary files under ignored `.tmp/`. Streamlit AppTest requires localhost sockets; the Codex Windows sandbox blocks Python's fallback socketpair, so AppTest/server verification ran outside that sandbox. Streamlit binds to `127.0.0.1`, and usage-stat collection is disabled in `.streamlit/config.toml`.

Normal execution defaults to real replay against `examples/real-replay/` on `gemini-3.1-flash-lite`, opening Q1. These 17 captures contain the fresh Q1 draft/check and correction check, the verified Q2 pair, and byte-identical Q3–Q8 captures. All requests match current prompts. The original raw responses and request fingerprints are unchanged; `examples/capture-provenance.json` records their session IDs and byte hashes. Q2 remains unresolved. Human approval remains an explicit action.

SQLite state defaults to ignored `data/workspace.sqlite3`. Replay requires an exact request match (including prompts, schemas, SDK version, model, source fingerprint, and proposed wording), retains the original run ID, and never falls back to live calls. `WORKSPACE_DB`, `WORKSPACE_REPLAY_DIR`, and `GEMINI_MODEL` override configuration. The transport reads direct JSON files in the selected directory, not subdirectories. `.env.example` is documentation only and is not loaded automatically. The selected real captures under `examples/` are repository files; full historical runs and verification databases remain ignored artifacts. Missing captures, changed sources, incompatible SDK versions, and novel edits fail visibly.

To use the supported default in a fresh isolated database (choose a new database filename if it already exists):

```powershell
$env:WORKSPACE_DB='.tmp/real-replay-demo.sqlite3'
$env:WORKSPACE_VERIFICATION='0'
$env:WORKSPACE_ALLOW_LIVE='0'
Remove-Item Env:WORKSPACE_REPLAY_DIR, Env:GEMINI_MODEL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Q1 opens by default. Click **Create answer** and inspect the current paid-plan policy beside the replaced every-plan policy. Click **Edit answer**, change only the wording to `Free-plan users cannot export CSV; CSV export is available on paid plans only.`, and click **Save and check**. Keep the citations and other fields unchanged: the saved check matches this exact proposal in `examples/q1-correction.json`. Then use **Approve answer**, enter a demonstration reviewer name and confirm evidence review. On **Reuse approved answer**, repeat `Can free-plan users export CSV?` exactly; the approved correction and sources appear and survive reload. See `examples/README.md` for the complete demo and offline verification command. No key is required. Other novel edits need matching saved checks or live validation. Synthetic replay continues to use `gemini-3.8-flash` fixture requests; clear `GEMINI_MODEL` before the synthetic command below.

To reproduce the isolated synthetic browser demonstration:

```powershell
.venv/Scripts/python.exe scripts/prepare_verification.py
$env:WORKSPACE_VERIFICATION='1'
$env:WORKSPACE_ALLOW_LIVE='0'
$env:WORKSPACE_DB='${REPO_ROOT}/artifacts/verification/browser.sqlite3'
$env:WORKSPACE_REPLAY_DIR='${REPO_ROOT}/artifacts/verification/synthetic-captures'
Remove-Item Env:GEMINI_MODEL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Synthetic mode is restricted to databases under `.tmp/` or `artifacts/verification/` and visibly labels approvals as demonstrations. The saved browser database intentionally ends with source removal and review-required approvals; use a new filename in that directory for an empty demonstration.

Verification artifacts are under ignored `artifacts/verification/`: `reference-results.json` and `.md` contain the five supplied cases plus ten independently declared additions; `browser-checks.json` and screenshots record actual browser outcomes; `checks.json` records executed local checks. The report labels rows from this invocation as current and retained reports as historical. Its exit status includes all current failures and fixture-integrity failures; historical rows cannot mask a fresh failure. Missing captures are recorded as unverified. Fresh reference verification passes Q1–Q8 using the default examples. The report script always creates new verification databases and never invokes live Gemini. `scripts/verify_q1_demo.py` defaults to credential-free replay of the fixed Q1 correction and checks approval/reuse, pending-edit exclusion, reload and source invalidation. Its explicit `--live` option makes up to three Q1-only calls; ordinary replay never does.

`pending-live-request.json` and `.md` preserve the original reviewable payload specification. The user subsequently authorized the original Q1–Q8/five-source payload and proposed-answer checking at Google's API. `scripts/verify_live.py` is the explicit live verifier; it loads only known key/model settings from the process or local `.env`, guards the original seed scope, uses separate databases and captures under `artifacts/real-runs/<session>/`, and keeps identities/notes local. Normal app execution still reads an environment key only after an explicit live action; `.env` is not loaded by the app.

The configured key authenticated an API model-catalog read. Original checker errors and the later `gemini-3.8-flash` HTTP 503/high-demand response remain recorded. The working `gemini-3.1-flash-lite` response, local offset fix and isolated Q1 lifecycle were followed by explicit authorization to finish Q2–Q8. That earlier run captured 14 successful transports (one draft/check pair per question) and reproduced all drafts through replay with credential access and network fallback prohibited. Q3–Q8 pass checking. The earlier Q2 checker parsed successfully but produced four semantic findings; its recorded unresolved disposition alone did not certify checker success. The fresh Q2 fix and exact replay are recorded separately below. Strict parsing initially caught answered drafts with "none"/"null" reasons; the prompt now explicitly requires an empty string and prohibits unsupported exclusivity. No validators were weakened.

`q2-q8-results.json` retains the earlier live/replay results and original labels. `q2-fix/q2-results-8df5725a0e2849e7b2817e7016299049.json` records the fresh Q2-only real draft/check and exact replay; `q2-fix/capture-coverage.json` identifies the copied Q3–Q8 captures. Empty-answer checking now explicitly copies the empty answer rather than the unresolved reason and uses only relevant passage-level conflict references. Answered-check requests are unchanged. The reference report preserves earlier reports as historical evidence, including their original pass labels. Fresh replay separately records question disposition, checker request/parsing, and semantic acceptance; overall draft/check success requires all three. The live verifiers also require passing replay rows, no replay blocker, and an exact live/replay comparison to exit successfully. Six supported questions received labelled demonstration approvals in the earlier isolated verification database; fresh Q2 remains unresolved and unapproved. The key was not printed or stored in captures, and the working database was untouched. Source changes and user-added sources are tested locally and are not sent to Google. Presentation/submission materials and AI workflow records remain outside this task.

## Working with Codex

- `AGENTS.md` contains the standing work loop and verified project boundaries.
- `$feature-review` tests and reviews the change against the requested behavior.
- `$evidence-review` supplies the domain checklist when source evidence, approval, reuse, or source versions are involved.
- Executed setup, run, and test commands are recorded above and in the verification artifacts.

The skills live in `.agents/skills/` and can be invoked by name, for example: `Use $feature-review to review the answer review screen against the starter-pack rules.` They may also be selected when their descriptions match the task.

Development tools, selected original prompts, and a concrete correction/verification workflow are documented in [LLM_USAGE_NOTE.md](LLM_USAGE_NOTE.md).

The completed [AI workflow setup](ai-workflow/README.md) and [manifest](ai-workflow/manifest.json) record the development/application models, project instructions, skills, runtime subagents, manual scripts, applicable tool settings and permissions, named historical versions, and explained redactions or unavailable details. Active project configuration remains at its normal repository paths; snapshots are reference records, not automatically enabled hooks or host settings.
