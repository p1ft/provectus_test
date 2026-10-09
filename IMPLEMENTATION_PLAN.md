# Questionnaire Evidence & Review: implementation plan

## Instructions for the implementation agent

This document is a plan, not evidence that the application has been implemented or tested. Begin implementation only when the user requests it. Once implementation is authorized, complete the required end-to-end flow and verification below; do not stop at a scaffold or a plausible-looking diff.

1. Read `AGENTS.md`, `README.md`, both project skills, this plan, and every file in `tasks/evidence/`. Recheck the repository and runtime before editing because the assessment below is a planning snapshot.
2. Use **Python, Streamlit, SQLite, Gemini through the official `google-genai` Python SDK, and Pydantic v2 for schemas**. This explicit user choice overrides the older LangChain selection in `README.md` and `AGENTS.md`. Do not use LangChain or an agent framework. Define contracts once as Pydantic models and reuse them for Gemini output schemas and local validation.
3. Treat `tasks/evidence/domain.md` as the authority for domain behavior. Preserve all original evidence fixtures, IDs, policies, authority metadata, reviewer mappings, and supplied expected results.
4. Follow the numbered implementation steps in dependency order. Build focused tests alongside the behavior they verify, and run each step's checks before moving on.
5. Keep the application small: one local Streamlit process, synchronous model calls, and SQLite. Do not add retrieval infrastructure, a separate API/frontend, authentication, background workers, or optional features.
6. Keep presentation materials, submission documentation, and AI workflow records out of this phase. Real-response captures and the expected-versus-observed report are required application verification artifacts and remain in scope.
7. Never hardcode answers by question ID or use `expected-seed-results.json` as application logic. A coding agent's review does not substitute for the application's explicit human approval action.
8. Report actual test and runtime outcomes. If an external blocker prevents real verification, identify the blocked cases as unverified; do not substitute mocked success.

**Success criterion:** complete and verify the source -> Gemini draft -> evidence validation -> human review -> durable approval -> identical-question reuse -> source-change invalidation flow.

## A. Repository assessment

At planning time, the repository contains preparation material only: `README.md`, `AGENTS.md`, two project skills, and four original files in `tasks/evidence/`. There is no application, dependency manifest, database, or test suite. Git reported a clean working tree before this plan was saved.

The seed contains five documents, five passages, eight questions, and three reviewer roles. The supplied expectations cover Q1-Q3, approved reuse, and source changes.

Verified tooling during planning:

| Tool | Observed availability |
| --- | --- |
| Python | Bundled Python **3.12.14**; `venv` available |
| SQLite | **3.53.1**, through Python |
| pip / pytest | **26.2.1 / 8.4.2** in the bundled runtime |
| Pydantic | **2.13.5** in the bundled runtime |
| Streamlit / google-genai | Not installed in the checked runtime |
| Ruff / mypy / python-dotenv | Not installed in the checked runtime |
| Git / ripgrep | **2.53.0 / 15.2.0** |
| Windows Python launcher | No registered installations |

The working interpreter is `C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`. The PATH entries for `python` are Windows aliases; the directory containing `pip.exe` has no adjacent Python executable. Use the verified interpreter to create a project-local `.venv`; do not install into the bundled runtime.

No dependencies were installed, secrets inspected, or model APIs called during planning. Dependency pins and application commands remain unverified until implementation.

## B. Architecture and file layout

Use one Streamlit process, synchronous Google SDK calls, and SQLite. Send the entire small source corpus; retrieval infrastructure is unnecessary.

All proposed paths are relative to the repository root, `D:\work\provectus-test`.

| Proposed file | Responsibility |
| --- | --- |
| `app.py` | Queue, counts, question/answer/evidence columns, review forms, repeat-question form, source-update controls, live/replay selection |
| `workspace/__init__.py` | Package marker |
| `workspace/store.py` | SQLite schema, transactions, seed import, immutable revisions, approval/reuse queries |
| `workspace/evidence.py` | Shared Pydantic source/draft/check schemas, source integrity, supersession graph, citation/excerpt checks |
| `workspace/gemini.py` | Draft and semantic-check prompts, direct `google-genai` calls, raw run capture, exact-request replay |
| `workspace/service.py` | Coordinate drafting, editing, validation, approval, unresolved decisions, reuse, and invalidation |
| `tests/test_sources.py`, `tests/test_validation.py`, `tests/test_lifecycle.py`, `tests/test_app.py` | Meaningful domain, persistence, failure, and Streamlit tests |
| `tests/fixtures/synthetic/` | Explicitly labelled synthetic responses and source variants |
| `tests/reference-cases.json` | Independently specified additions to supplied expectations |
| `scripts/verify_reference_cases.py` | Produce expected-versus-observed results from a verification database |
| `requirements.txt`, `requirements-dev.txt`, `.env.example` | Verified dependency pins and secret-free configuration example |

Use runtime dependencies `streamlit`, `google-genai`, and `pydantic`; development dependencies `pytest` and `ruff`. SQLite, JSON, hashes, and timestamps use the standard library.

Keep the Pydantic models in `workspace/evidence.py`, matching the implementation already started there. `store.py`, `gemini.py`, and `service.py` must reuse these contracts rather than maintain separate handwritten schemas or duplicate field/type checks. SQLite table definitions remain SQL; Pydantic does not replace database constraints or evidence-support checks.

Keep the database under ignored `data/`, real-response bundles under `artifacts/real-runs/`, and observed results under `artifacts/verification/`. Update `.gitignore` for local database files, including SQLite sidecar files. Preserve every original evidence file.

For the smallest setup, read credentials from an environment variable; omit `.env` loading and its additional dependency. `.env.example` documents variable names and contains no credential values.

## C. Data model and answer lifecycle

Use SQLite foreign keys and transactions, with these tables:

| Table | Essential contents |
| --- | --- |
| `topics` | Original topic-to-reviewer mapping |
| `questions` | ID, exact text, topic, queue status, working revision, active approval |
| `sources` | Document ID, current stored revision, availability |
| `source_revisions` | Immutable version, date, status, supersedes, passages JSON, content fingerprint |
| `model_runs` | Purpose, question ID, exact request/prompt/schema/settings, source snapshot, raw response or failure, origin |
| `answer_revisions` | Immutable wording, origin, parent revision, unresolved reason/note, validation result and associated runs |
| `citations` | Answer revision, exact source revision, passage ID, excerpt, role: supporting or replaced/conflicting |
| `approvals` | Exact answer revision, reviewer name/role, timestamp, reviewed source fingerprint, invalidation reason |

Import the seed only into an empty database. Reloading must not overwrite working sources or review history. Validate before committing an import or source update.

Lifecycle:

- Supported, validated output becomes **answered**, awaiting human approval.
- Unknown facts, unsupported claims, unresolved conflicts, and validation failures become **unresolved**, with a visible reason and mapped reviewer.
- Editing creates another immutable draft and clears its prior validation. It never changes an approved revision.
- Approval requires fresh validation of the exact wording/citations, current sources, and an explicit reviewer action. Store reviewer identity and mapped role. Recheck the source fingerprint inside the approval transaction so a changed source cannot acquire a stale approval.
- Leaving an answer unresolved requires a note and removes its active approval from reuse eligibility.
- An unapproved edit may coexist with a previously approved revision. Reuse can return that previous approved wording, never the pending edit.
- Source invalidation produces **review_required** and blocks reuse until fresh review and approval.
- API failures record a failed attempt and visible error without overwriting existing draft or approval state. For a question without a prior answer, show the failure and leave it unresolved.

Queue counts are disjoint: answered awaiting approval, unresolved, and currently approved. Show pending and review-required separately. An approved question with an unapproved edit retains its approved status and displays a pending-edit indicator.

Reuse matches question text exactly and checks eligibility at lookup time. Return approved wording, reviewer, timestamp, and evidence. No fuzzy matching or automatic approval. Asking again should look up an existing question and its approval rather than overwrite its working draft. If no eligible approval exists, explain why and offer an explicit drafting action.

Source updates append revisions or mark a source unavailable. Preserve old passages and citations. Compare versions **and content fingerprints**, preventing unnoticed same-version text changes. Conservatively require review after any corpus change because another document may introduce a conflict. Persist this invalidation; restoring an old version must not silently restore approval.

## D. Gemini integration and validation

### Request and output

Use `genai.Client` and `client.models.generate_content`, with instructions in `system_instruction` and question/source records in separate JSON content parts. Treat source text as evidence data, including instruction-like text it contains. Set `response_mime_type` to `application/json` and use the appropriate Pydantic model as `response_schema` for each call. See the [official SDK documentation](https://googleapis.github.io/python-genai/).

Define Pydantic v2 `BaseModel` contracts for passages, documents, questions, seed data, citations, conflicts, drafts, individual claim checks, and semantic-check results. Use `ConfigDict(extra="forbid", strict=True)`, typed nested models, `Literal` values for dispositions/verdicts, and `Field` constraints for required IDs, positive versions, and bounded strings/lists. Use field/model validators for local cross-field rules, such as an answered draft requiring evidence. Source relationships and semantic support still require the explicit evidence checks below.

The same models are the source of truth for SDK output schemas and local parsing. After saving the raw response, call the corresponding model's `model_validate_json()` for both live and replay responses; use `model_validate()` for reviewer-edited data. Do not rely solely on SDK parsing. Catch `ValidationError`, retain the raw response, and surface a specific validation outcome. Serialize validated values with `model_dump(mode="json")` or `model_dump_json()`. Capture `model_json_schema()` with each run so its contract is identifiable. See [Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/).

Verify that both output models work with the installed SDK and selected model. If Gemini cannot express a local validator or constraint, retain that check in Pydantic after the response arrives; do not weaken local validation or invent an independent schema.

Each draft contains:

- `question_id`;
- proposed disposition: `answered` or `unresolved`;
- short `answer`;
- citations containing `passage_id` and a brief verbatim `excerpt`;
- unresolved reason and identified conflicts.

The application determines reviewer routing and final status; model labels do not grant approval. Only supplied product passages, or explicitly labelled rule-consistent working-source additions, count as evidence. Expected results, approval history, and outside product knowledge are not source passages.

Use one configured, accessible Flash-class model supporting structured output. Confirm its exact model identifier during implementation, record all settings, and use bounded output and request timeouts. Model calls follow explicit user actions, never ordinary widget reruns.

### Validation

Apply checks in this order:

1. **Source integrity:** parse seed/source inputs with Pydantic; then check unique document, passage, and question IDs, existing supersedes targets, valid owner mappings, and an acyclic supersession graph.
2. **Response structure:** validate raw draft and semantic-check JSON with their shared Pydantic models; then check matching question ID and required citations for answered output. Validate edits with the same draft model before evidence checks.
3. **References:** every passage resolves to the captured document revision.
4. **Excerpts:** nonempty verbatim substring of the cited passage; reject invented quotes.
5. **Authority:** use explicit supersedes edges only. Dates and `status` alone cannot resolve authority. Show replaced passages alongside current evidence.
6. **Semantic support:** make a separate Gemini checking call over the complete proposed answer and full corpus. Require claim-by-claim support, citation relevance, omitted/extra claims, and conflicting evidence assessment.
7. **Human review:** show complete findings and require confirmation that displayed evidence supports the final wording.

The semantic checker must examine the whole answer rather than trust the draft's own claim list. Its structured result identifies each claim, supporting passage, verdict, and explanation. Reject missing claim coverage or malformed checker output. Apply the same pipeline to reviewer-edited wording and citations before approval; validation is bound to the exact revision and source snapshot.

A valid reference does not prove entailment, and a second model can repeat the first model's mistake. Any unsupported, uncertain, contradictory, missing, or malformed checking result blocks approval and leaves the answer unresolved. The reviewer corrects wording/citations and reruns validation; there is no warning bypass.

A supersedes edge establishes authority, not whether two passages contradict each other. The semantic check identifies relevant contradictions; the graph resolves them only when an explicit replacement relationship applies. Multiple conflicting current sources without such a relationship remain unresolved. Q1 must display the replaced EXPORT passage even though its conflict is resolved.

Undocumented JSON export remains unknown. Do not turn absence of documentation into a negative capability claim. Explicitly documented negative answers, such as free-plan CSV export and live chat, can be supported.

### Real-run capture and replay

Persist raw draft **and semantic-check** responses before parsing. Capture exact requests, prompts, schemas, question IDs, source contents/versions/fingerprints, model/settings, SDK version, timestamps, and response metadata. Store sanitized failures without credentials or HTTP authorization headers.

Replay substitutes saved raw responses at the transport boundary, then runs the same parsing, citation, authority, and status logic. Require an exact request fingerprint match and label the UI **Replay of real run**, with the original run ID.

Replay needs no key or client initialization. An edited answer without a matching recorded check remains unresolved until live validation is available. Never silently fall back from replay to a live request. Replay source snapshots do not bypass current-source checks for approval or reuse. Synthetic responses are confined to labelled tests.

## E. Implementation steps

| Step | Concrete result and files | Depends on | Verification and expected observation |
| --- | --- | --- | --- |
| **1 - Setup** | Create dependency files, `.env.example`, module skeleton, and ignore local database output | None | Create `.venv` from verified interpreter; install during implementation; import dependencies and run Ruff. No LangChain dependency |
| **2 - Sources/store** | Implement Pydantic source contracts, SQLite schema, atomic import, source snapshots and supersession in `store.py` and `evidence.py`; add source tests | 1 | Five documents/eight questions import; original IDs/mapping persist; wrong types/extra fields, duplicate IDs, missing targets and cycles fail visibly without partial import |
| **3 - Gemini/validation** | Define Pydantic draft/check contracts; reuse them for SDK schemas and live/replay/edit validation; implement checks and capture in `gemini.py` and `evidence.py`; add validation tests | 2 | Missing fields, wrong types, unknown fields, invalid disposition/verdict and malformed JSON fail visibly; wrong references/excerpts, irrelevant citations, extra claims and conflicts produce unresolved reasons; failures preserve existing state |
| **4 - Review/reuse** | Implement immutable edits, approval transactions, unresolved notes and exact reuse in `service.py`; add lifecycle tests | 3 | Approved correction is returned exactly; pending edit is excluded; reopening the database preserves approval and evidence |
| **5 - Streamlit flow** | Build `app.py` and AppTest checks | 4 | Filters/counts work; question, draft and passages appear side by side; mapped reviewer/warnings visible; form submits save once; ordinary reruns make no API calls |
| **6 - Source updates** | Add update/remove controls backed by stored revisions; extend lifecycle/UI tests | 2, 4, 5 | Version change or removal immediately blocks reuse; old evidence remains visible; failed updates leave current sources intact |
| **7 - Final verification** | Add reference runner/additional expectations; capture real runs, replay bundles, report and UI screenshots | 1-6 | Automated checks pass; eight real drafts reviewed; correction/reuse/reload/update flows exercised; real responses replay without credentials; independent report records actual results |

Build focused tests alongside each step. Do not defer domain verification until the UI exists. Use temporary databases in tests so verification never corrupts the user's working state.

Planned commands after implementation, not currently verified application instructions:

- Install from the project environment: `.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt`.
- Run a focused test file: `.venv\Scripts\python.exe -m pytest tests/test_lifecycle.py -q`.
- Run all tests: `.venv\Scripts\python.exe -m pytest -q`.
- Lint: `.venv\Scripts\python.exe -m ruff check app.py workspace tests scripts`.
- Check compilation: `.venv\Scripts\python.exe -m compileall -q app.py workspace tests scripts`.
- Start the app: `.venv\Scripts\python.exe -m streamlit run app.py`.
- Produce the report: `.venv\Scripts\python.exe scripts/verify_reference_cases.py`; the script must select a separate verification database and write observed artifacts under `artifacts/verification/`.

## F. Acceptance coverage

| Acceptance case | Steps | Required verification |
| --- | --- | --- |
| Q1: no, `EXPORT-v2:p1`, old conflict visible | 2, 3, 5, 7 | Real draft, graph test, browser evidence view, supplied expectation comparison |
| Q2 unresolved; Product reviewer | 3, 5, 7 | Real draft and queue show undocumented JSON export and supplied routing |
| Q3 documented hours; `SUPPORT-v1:p1` | 3, 5, 7 | Real draft and independent assertion: Monday to Friday, 09:00-17:00 UTC, correct passage |
| All eight drafted and reviewed | 3-5, 7 | Real runs for Q1-Q8; explicit review disposition saved for every question |
| Approved correction reused | 4, 5, 7 | Edit, validate, approve, repeat exact question; wording and approval/source records match |
| Unapproved edit excluded | 4, 7 | Save different draft; repeat question returns only eligible approved wording or no approved result |
| Approval/evidence survive reload | 2, 4, 7 | New database connection, process restart and browser refresh retain records |
| Changed referenced version requires review | 6, 7 | Update approved source; reuse blocked; old text visible; fresh approval required |
| Missing references | 2, 3, 5 | Reject invalid import; show unresolved missing-citation/source warning |
| Malformed model output | 3, 5 | Pydantic rejects malformed JSON, missing/unknown fields, wrong types and invalid disposition/verdict in live and replay paths; raw response retained; warning shown; approval blocked |
| API failures | 3, 5 | Inject timeout/provider failure; visible error; existing approval remains intact |
| Irrelevant citations | 3, 7 | Correct passage ID/excerpt with unrelated answer fails semantic support |
| Unsupported extra claims | 3, 7 | Supported fact plus undocumented claim remains unresolved, including reviewer-edited answers |
| Unresolved source conflicts | 2, 3, 7 | Labelled conflicting sources without supersedes cannot yield approved answer |
| At least five independent reference cases | 7 | Report uses supplied expectations plus predeclared additions, separately from observed output |

## G. Final verification

1. Run focused tests during development, then the full pytest suite, Ruff, and Python compilation checks. Check that application modules do not read supplied expected results or branch on question IDs.
2. Run Streamlit AppTest for forms, counters, warnings, persistence, and API-call boundaries. AppTest checks application outputs; it does not replace browser layout verification. See [Streamlit AppTest documentation](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
3. Start the actual Streamlit server. Inspect screenshots before and after review actions, including evidence columns, replaced text, error states and filters.
4. Make real drafting calls for all eight questions. Inspect saved raw output and checker results; record each review disposition. Clearly distinguish live verification from synthetic tests.
5. Correct and approve Q1 through the UI. Repeat its exact text, verify approved wording/details, then save an unapproved edit and verify it is excluded. Also check an unapproved answer without a previous approval.
6. Restart the process and refresh the browser; verify approvals, citations, notes and source revisions persist.
7. Change a referenced source version, verify reuse is blocked, then exercise removal and fresh review. Verify original fixtures remain unchanged and replaced text remains accessible.
8. Start replay in a clean verification database with credential access disabled. Replay saved real draft/check responses through the same validators. Verify a missing replay match cannot initiate a live call.
9. Generate separate JSON and Markdown expected-versus-observed reports. Include the five supplied cases - Q1, Q2, Q3, approval-reuse and source-change - and independently checked additions such as Q4 (live chat not offered, `SUPPORT-v1:p1`) and unapproved-edit exclusion.

Define added expectations from direct inspection of the domain rules and passages before examining application output. Each report row records expected behavior and its origin, observed behavior, pass/fail/unverified, real/replay/synthetic provenance, and relevant run/revision IDs. Compare factual meaning and required references rather than incidental model phrasing; approved reuse must preserve wording exactly.

Only tests/reporting may read `expected-seed-results.json`. Application modules must not import it or use it as answer data.

## H. Blockers and assumptions

- **External blockers:** dependency download access, Gemini network access, usable model access/quota, and credentials supplied locally during implementation. Mocks and replay cannot establish that live integration works.
- **Credentials:** `.env.example` contains an empty `GEMINI_API_KEY` and nonsecret model configuration. Read the key from the local process environment only when live mode is invoked; never persist, print, or commit it. No credentials are needed for planning.
- **Scope assumptions:** one local reviewer at a time; reviewer name/role recorded without authentication; sequential drafting; explicit retry after failure; exact question-text reuse.
- **Replay limitation:** previously captured responses are reproducible; novel edits require live semantic checking before approval.
- **Conservative validation:** uncertain support and new unresolved conflicts remain unresolved. Source changes invalidate eligibility without deleting historical approval.
- **Completion reporting:** if access or setup blocks live verification, report those checks as unverified rather than substitute synthetic success. State what is implemented, what passed, and what remains blocked.

## Completion checklist

- [x] Original evidence fixtures and supplied expected results remain unchanged.
- [x] The application uses the requested stack and imports all five documents/eight questions with integrity checks.
- [x] Shared Pydantic models define source and model-output contracts; Gemini schemas, live/replay parsing, and edited-answer validation reuse them.
- [x] Real drafts and edited answers pass the same evidence-validation path before approval. Q1 real replay/lifecycle passed; Q2–Q8 real draft/check outcomes and exact replay passed. Q2 remains unresolved, and all approvals are isolated demonstrations.
- [x] The actual review UI exposes evidence, replaced text, warnings, routing, filters, counts, notes and approval details.
- [x] Immutable revisions, approvals and evidence survive a process restart and browser reload, verified in isolated synthetic demonstrations.
- [x] Identical-question reuse returns only eligible approved wording; unapproved edits are excluded, verified offline and in the demonstration browser.
- [x] Source changes or disappearance persistently block reuse until fresh review and approval, verified offline and in the demonstration browser.
- [x] Raw real responses and identifying request/source metadata are saved; replay runs without credentials or network fallback. Q1 archived real draft/check replay passed; all Q2–Q8 real draft/check pairs were captured and replayed with credential access and network fallback prohibited.
- [x] Required failure paths have visible outcomes and meaningful labelled synthetic tests.
- [x] Automated checks and actual browser flow checks have recorded results under `artifacts/verification/`.
- [x] A separate expected-versus-observed report covers the five supplied cases and ten independently declared additions, with synthetic/live/replay provenance separated.
- [x] Final completion claims distinguish passed, failed and externally blocked verification.

After the two targeted tests, the user explicitly authorized Q2–Q8 verification. Gemini 3.1 Flash-Lite supplied all seven draft/check pairs, their expected outcomes passed independent inspection, and credential-free exact replay reproduced the real outputs. Q2 remains unresolved and Q3–Q8 have supported wording. `q2-q8-results.json`, Q1 lifecycle artifacts and the reference report preserve actual results and earlier failures separately. Presentation materials, submission documentation, and AI workflow records were not added.
