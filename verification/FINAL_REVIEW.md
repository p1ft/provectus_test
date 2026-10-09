# Final submission review

Questionnaire Evidence & Review Workspace, Alternative C. Reviewed on 9 October 2026 against the supplied brief and starter pack. Checks ran from an isolated Git checkout using a newly installed Python 3.12.14 environment. No new Gemini API requests were made during this review.

**Result: the eight requested submission components are present and the required behavior passes the checks below.** The only unverified model scope is the separate fictional extension; its outcomes are explicitly synthetic.

## Minimum demonstration: expected versus observed

| Case and input | Independent expectation | Observed result | Check |
| --- | --- | --- | --- |
| Supported Q3: “When is email support available?” | Monday–Friday, 09:00–17:00 UTC, citing `SUPPORT-v1:p1` | Saved real response gives those hours; exact replay and checker pass with zero findings | **Pass — real capture replay** |
| Undocumented Q2: “Is JSON export available?” | No invented yes/no answer; unresolved with Product reviewer | Empty proposed answer, `unresolved` status, mapped Product route; independent saved empty-answer checker passes with zero findings | **Pass — real capture replay** |
| Superseded CSV policy, Q1 | No free-plan CSV export, citing `EXPORT-v2:p1` and showing conflicting `EXPORT-v1:p1` | Saved real draft uses paid-plan policy and names both passages; citations, supersession and checker pass | **Pass — real capture replay and UI** |
| Q1 corrected wording and repeated exact question | Explicitly approved correction with reviewer/source records; an unapproved edit must be excluded | Fixed correction passes its saved real checker; isolated demonstration approval/reuse passes; pending unsupported wording cannot replace it | **Pass — real checker replay, isolated lifecycle and UI** |
| Reload and source-version change | Approval/evidence persist on reload; changing its referenced source version blocks reuse pending review | Approved Q1 and both source versions persisted after browser reload; version 2→3 sets `review_required`, blocks reuse and retains old evidence | **Pass — isolated lifecycle, AppTest and browser reload** |

Expected values are the supplied `tasks/evidence/expected-seed-results.json` plus independent declarations in `tests/reference-cases.json` and `exercises/evidence/expected-results.json`; none is read by the application as an answer key. The five supplied reference cases and ten additional declarations were checked against the source passages before comparison with outputs. [Machine-readable results](results.json) list case-level provenance and statuses.

## Complete submission coverage

| Requested component | Evidence in the repository | Result |
| --- | --- | --- |
| 1. Working code and dependencies | `app.py`, `workspace/`, pinned requirements, local SQLite, explicit review/reuse, real Gemini adapter | **Pass**; clean-checkout full suite passed |
| 2. Starter and additional data | Four byte-identical original files in `tasks/evidence/`; separate fixed extension with generation method, assumptions and expected results | **Pass**; fixture integrity and extension checks passed |
| 3. Five reference cases | Table above, supplied expectations and independent reference cases; synthetic failure paths separately labelled | **Pass**; 15 synthetic reference outcomes and eight real replay outcomes passed |
| 4. Real responses and replay without key | `examples/real-replay/` has 17 `origin=live` captures with exact requests/raw responses; provenance records each SHA-256 | **Pass**; Q1–Q8 and fixed Q1 correction replay with credential access and live fallback prohibited |
| 5. Root README | Setup, local run, architecture, model/settings, data, candidate-estimated 6–7 hours, limitations, tests and replay | **Pass** |
| 6. LLM usage note | `LLM_USAGE_NOTE.md` names tools/models, generated work, an original planning instruction and the Q2 checker correction | **Pass** |
| 7. AI workflow setup | Completed `ai-workflow/README.md`, nine manifest categories, historical snapshots, tool settings, permissions and blank key names in `.env.example` | **Pass**; paths, hashes and omissions checked |
| 8. Brief presentation | `WALKTHROUGH.md` gives a written reviewer route and expected screen states | **Pass** |

## Executed checks

- Fresh isolated Python 3.12.14 venv: pinned `requirements-dev.txt` installed successfully; `pip check` reported no broken requirements.
- Full suite in an isolated checkout: **163 passed in 166.68 seconds**. Tests prohibit real Gemini client initialization. Ruff, compilation and dependency checks passed.
- Independent reference script: 15 labelled synthetic scenarios passed, all eight current real-response replay rows passed, **zero current failures**. Its “new live verification” row remains *unverified*, as expected for an offline run; it is not counted as a pass.
- Q1 replay script: real saved draft/check, fixed correction check, unapproved-correction exclusion, demonstration approval/reuse, pending-edit exclusion, replay miss, reload, source change and removal all passed.
- Separate extension: five scenario checks passed with labelled synthetic responses; no real extension capture is claimed.
- Actual clean-checkout browser: Q1 showed current/replaced evidence, accepted the fixed correction through saved checking and retained a clearly labelled demonstration approval after reload. [Review screenshot](screenshots/q1-review.jpg).
- True Git checkout integrity: all four starter evidence files matched the ZIP byte-for-byte. All 17 curated capture SHA-256 hashes, archived built-in guidance hashes and 72 normalized AI manifest file hashes matched. `.gitattributes` preserves the byte-hashed files on Windows checkout.
- Submission scan: `.env`, local databases, virtual environments, bulk historical artifacts and ignored temporary outputs are excluded. Captures and AI setup snapshots were checked for credential signatures and personal machine paths.

These checks use the submitted source and files in a separate working copy. The active working database and original starter documents were not modified. Approvals created by tests and browser automation are **isolated demonstrations**, not customer approvals.

## Limits and interpretation

The additional exercise was verified with synthetic responses only. New provider availability was not measured in this final offline review; the repository includes previously captured real responses from successful Gemini calls. Reuse requires identical question text, and new answer wording or source snapshots need a matching saved check or an authorized live validation. Any corpus change conservatively invalidates approvals. Reviewer identity is recorded, not authenticated. Model-based semantic checks and this small fictional sample do not establish performance on arbitrary documents.

Earlier failed checker/provider attempts remain identified as historical in the usage/configuration records. They do not certify current checker success and do not override the fresh Q1–Q8 replay results.

## Code organization follow-up

The final working tree now defines Pydantic and transport data contracts in `workspace/schemas.py` and Gemini instructions in `workspace/prompts.py`. Evidence checks, persistence, orchestration and model transports remain in their behavior modules. Existing import paths remain available to older scripts and tests. The `Draft`/`SemanticCheck` JSON-schema hashes and exact draft/check prompt hashes match the pre-refactor baseline; offline Q1 lifecycle and current Q1–Q8 replay still pass. The post-refactor focused checks passed **52 tests**, and the complete working-tree suite passed **163 tests in 158.81 seconds**. Ruff, compilation and dependency checks passed. No new live provider call or Git commit was made for this follow-up.
