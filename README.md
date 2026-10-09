# Questionnaire Evidence & Review Workspace

Alternative C of the Junior AI Engineer assignment. A local workspace that drafts questionnaire answers from fictional product documents, shows supporting and conflicting evidence, and lets a reviewer correct, approve and reuse eligible answers.

**No API key is needed to review the submitted solution.** The default mode replays 17 saved real Gemini responses for Q1–Q8 and the fixed Q1 reviewer correction through the same validation path used for live calls.

| Review material | Purpose |
| --- | --- |
| [Written walkthrough](WALKTHROUGH.md) | Guided product demonstration with expected outcomes |
| [Final review and results](verification/FINAL_REVIEW.md) | Requirements coverage, executed checks, observed results and limitations |
| [LLM usage note](LLM_USAGE_NOTE.md) | Actual tools/models, selected original prompts and a correction example |
| [AI workflow setup](ai-workflow/README.md) / [manifest](ai-workflow/manifest.json) | Applied configuration, versions, history, restoration and explained omissions |

## Quick start

Python **3.12** is required; `3.12.14` was used for verification. Commands below use Windows PowerShell from the repository root. Use an available Python 3.12 interpreter for `python`; the Windows `py` launcher was not configured on the development host. On POSIX, the environment's interpreter is `.venv/bin/python`.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
$env:WORKSPACE_DB='.tmp/reviewer-demo.sqlite3'
$env:WORKSPACE_VERIFICATION='0'
$env:WORKSPACE_ALLOW_LIVE='0'
Remove-Item Env:GEMINI_MODEL, Env:WORKSPACE_REPLAY_DIR, Env:WORKSPACE_SEED -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. The app binds to `127.0.0.1`, with usage-stat collection disabled. Q1 opens first in **Replay of real run · gemini-3.1-flash-lite**. Choose a new database filename if the example already exists: startup preserves existing questions, documents and review state. Stop the server with Ctrl+C.

## What to try

1. **Q1 / CSV export:** click **Create answer**. The answer uses `EXPORT-v2:p1`, paid plans only, and keeps the replaced `EXPORT-v1:p1` every-plan policy visible. Authority follows explicit `supersedes`, not dates.
2. **Correction and approval:** choose **Edit answer** and replace only the wording with `Free-plan users cannot export CSV; CSV export is available on paid plans only.` Keep other fields unchanged and click **Save and check**. Then explicitly approve with a demonstration reviewer name and evidence confirmation.
3. **Reuse and reload:** on **Reuse approved answer**, enter `Can free-plan users export CSV?` exactly. The approved correction, reviewer and sources appear and survive reload. An unapproved edit cannot replace that reusable wording.
4. **Q2 / JSON export:** create its draft. It remains **Unresolved** with the **Product reviewer** route because JSON export is undocumented. It cannot be approved. Q3 provides documented support hours; Q4 can give a supported negative answer about live chat.
5. **Source change, last:** update the working `EXPORT-v2` version from 2 to 3 on **Sources**. Q1 needs fresh review, reuse is blocked and old evidence remains. Original fixture files are untouched.

The complete button-by-button route is in [WALKTHROUGH.md](WALKTHROUGH.md). The exact replay proposal is [examples/q1-correction.json](examples/q1-correction.json). New wording or changed sources without a matching recorded check produce a visible replay miss; replay never calls the API. A new database restarts the original demonstration.

## Architecture and model configuration

One synchronous Streamlit process, SQLite persistence, shared Pydantic v2 contracts and the official Google Gen AI SDK. The small corpus fits in a request, so no retrieval service, agent framework or separate frontend/API is needed.

| File | Responsibility |
| --- | --- |
| [app.py](app.py) | Queue, counts/filters, answer/evidence review and explicit reviewer forms |
| [workspace/schemas.py](workspace/schemas.py) | Shared Pydantic contracts, captured-run/transport data and stable request fingerprints |
| [workspace/prompts.py](workspace/prompts.py) | Exact draft and checker instructions, separate from document content |
| [workspace/evidence.py](workspace/evidence.py) | References/excerpts, supersession and semantic-check findings |
| [workspace/store.py](workspace/store.py) | Atomic initialization/import, immutable revisions, approvals and source history |
| [workspace/gemini.py](workspace/gemini.py) | Gemini transport, native structured output, raw capture and exact-request replay |
| [workspace/service.py](workspace/service.py) | Answer lifecycle, exact-wording approval, current-source eligibility and reuse |

The successful application model is **`gemini-3.1-flash-lite`**, through `google-genai==2.29.0`, with temperature `0`, max output tokens `8192`, a `30000 ms` timeout and one SDK attempt per explicit action. Dependency versions are in [requirements.txt](requirements.txt) and [requirements-dev.txt](requirements-dev.txt).

Document/question content is supplied separately from system instructions. Structured output controls shape; local checks validate references, exact excerpts and authority. Supported drafts also receive a separate whole-answer semantic check. Unresolved or reference-invalid proposals stop the approval pipeline locally; independent verification separately exercises Q2's recorded empty-answer checker. Neither generation nor checking grants approval. Reviewer edits require validation of their exact wording and an explicit approval action bound to stored source revisions.

The 17 real captures in `examples/real-replay/` contain exact requests, prompt/schema/model settings and raw responses. [Capture provenance](examples/capture-provenance.json) records original sessions and byte hashes. Synthetic fixtures live separately under `tests/fixtures/synthetic/`. Earlier attempted model configurations and failed-check history are described in the usage/workflow records; they are not current successful outcomes or startup defaults.

## Data, preparation and assumptions

- [tasks/evidence/](tasks/evidence/) contains the four original files from starter-pack version `2026-10-02`, copied byte-for-byte: five documents, eight questions, fixed passage IDs, explicit supersession and topic/reviewer mapping. Their supplied expected results remain unchanged.
- [tests/reference-cases.json](tests/reference-cases.json) adds independently declared expectations for existing questions and failure/lifecycle checks. Expected values come from the passages/domain rules, never from application output or hardcoded application answers.
- [exercises/evidence/](exercises/evidence/README.md) is a separate fixed JSON extension prepared with Codex assistance: five additional questions and three short documents. It preserves the original records, has separate expected results and explicitly synthetic verification. No randomized dataset generation was used, so no random seed applies.
- An undocumented capability is unknown. Dates alone establish no authority; unresolved conflicts need review. Only approved wording can be reused, by identical question text. Replaced text and referenced source versions stay available.

## Verification

From the repository root, run:

```powershell
.venv/Scripts/python.exe scripts/verify_q1_demo.py --output .tmp/reviewer-checks/q1
.venv/Scripts/python.exe scripts/verify_reference_cases.py --output .tmp/reviewer-checks/reference
.venv/Scripts/python.exe scripts/verify_extension.py --output .tmp/reviewer-checks/extension
.venv/Scripts/python.exe -m pytest -q --basetemp=.tmp/reviewer-tests
.venv/Scripts/python.exe -m ruff check app.py workspace tests scripts
.venv/Scripts/python.exe -m compileall -q app.py workspace tests scripts
.venv/Scripts/python.exe -m pip check
```

The verifiers create isolated databases and never initialize a live Gemini client. Q1 exercises the saved real draft/correction plus explicitly labelled demonstration approval/reuse, pending-edit exclusion, reload and source invalidation. Reference verification compares five supplied cases plus ten independent additions and separately replays Q1–Q8. Extension verification is synthetic. The full test fixture prohibits real Gemini client initialization.

Reports distinguish question disposition, checker parsing/semantic acceptance, current replay and retained historical results. An offline run does not certify new live calls. [The submitted final-review report](verification/FINAL_REVIEW.md) and machine-readable results under `verification/` record the checks actually executed, including the five minimum demonstration cases. Windows Codex AppTest/server checks needed elevated execution for localhost sockets; ordinary tests do not need API credentials.

## Environment and optional live mode

| Variable | Purpose / default |
| --- | --- |
| `GEMINI_API_KEY` | Optional live credential; blank in examples |
| `GOOGLE_API_KEY` | Optional alias accepted by explicit live-verification helpers |
| `GEMINI_MODEL` | Defaults to `gemini-3.1-flash-lite` for real replay |
| `WORKSPACE_DB` | Defaults to ignored `data/workspace.sqlite3`; use a fresh `.tmp/` filename for review |
| `WORKSPACE_SEED` | Defaults to `tasks/evidence/seed.json` |
| `WORKSPACE_REPLAY_DIR` | Defaults to `examples/real-replay`; JSON captures must be directly in the directory |
| `WORKSPACE_VERIFICATION` | `0`; `1` enables labelled synthetic mode in isolated verification databases |
| `WORKSPACE_ALLOW_LIVE` | `0`; live actions require explicit opt-in |

[.env.example](.env.example) documents names and harmless defaults; the app does **not** load it or `.env` automatically. For optional new live actions, configure the process key and `WORKSPACE_ALLOW_LIVE=1`, then choose **Live Gemini** after agreeing model access/payload. That mode sends the selected question/current source snapshot, instructions/schema/settings and proposed answer for checking. Explicit live helpers can read known key/model values from an ignored local `.env`. No key is stored in captures or required for review.

## Limits and time spent

- Local prototype: reviewer names/roles are recorded, not authenticated.
- Exact question matching only. Changed wording/sources require matching captures or live validation; pinned SDK/request schemas matter for replay.
- Any source-corpus change conservatively invalidates all existing approvals, including same-version edits; restored text still needs fresh review.
- Model-based semantic checking can be wrong. Source inspection, deterministic checks and explicit human confirmation remain necessary; the small demonstration set is not an accuracy benchmark.
- Real calls were captured for the original questions. Added exercise cases are synthetic; final offline checks do not establish current provider availability.
- Local databases, credentials, full chat logs, dependency environments and bulk historical artifacts are excluded. The selected real samples, configuration snapshots and final results are included.

**Approximate total effort: 6–7 hours**, including data preparation, implementation, verification and documentation (candidate estimate; no detailed per-stage timesheet).

The [LLM usage note](LLM_USAGE_NOTE.md) explains AI-generated work and corrections. The [AI workflow manifest](ai-workflow/manifest.json) records actual configuration and explicitly marks unused, redacted and non-exportable parts. No deployment, external CRM or automated customer delivery is part of the required local scope.
