# Reviewer walkthrough

Questionnaire Evidence & Review Workspace — Alternative C.

This is the written presentation of the solution: the problem it addresses, a reproducible review flow, the implementation decisions and the evidence behind the results.

## What the application does

A sales team needs to answer buyer questionnaires using its product documents. The difficulty is deciding which statements are supported, which document has authority, what still needs clarification, and which reviewed wording is safe to reuse.

The workspace loads the supplied five fictional documents and eight questions. Gemini proposes answers with passage references; evidence checks run before a reviewer can approve the exact wording. A repeated question retrieves only an eligible approved answer, with its reviewer and source records. Changing the source corpus requires fresh review.

The original data and expected results remain unchanged in [tasks/evidence/](tasks/evidence/). A separate [five-scenario extension](exercises/evidence/README.md) adds supported, unknown and conflicting evidence examples plus reuse/source-change checks. Its results are explicitly synthetic. The main demonstration below uses saved **real Gemini responses**.

## Run without an API key

Open PowerShell at the repository root. Python 3.12 is required. If a prepared `.venv` already exists, skip creating/installing it; otherwise use an available Python 3.12 interpreter:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Start the demonstration with a fresh database filename. If the example filename already exists, choose a new one; startup intentionally preserves existing state.

```powershell
$env:WORKSPACE_DB='.tmp/reviewer-walkthrough.sqlite3'
$env:WORKSPACE_VERIFICATION='0'
$env:WORKSPACE_ALLOW_LIVE='0'
Remove-Item Env:GEMINI_MODEL, Env:WORKSPACE_REPLAY_DIR, Env:WORKSPACE_SEED -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Open the local URL printed by Streamlit. The header should say **Replay of real run · gemini-3.1-flash-lite**, and Q1 should be selected. Live calls are disabled. The repository contains 17 real captures: a draft/check pair for each Q1–Q8 and one check for the fixed Q1 correction. Replay matches the complete current request and uses the same validation path; it never falls back to a network call.

The sidebar contains questions, status counts and filters. **Review** contains the answer and evidence; **Reuse approved answer** retrieves reviewed wording; **Sources** edits working documents; **History & diagnostics** exposes revisions and checker/run details. **Awaiting approval** means a checked draft, not a human-approved answer.

## Guided review

### 1. Q1: use the authoritative policy and show the conflict

Select **Q1 · Can free-plan users export CSV?** and click **Create answer**.

The answer should say that free-plan users cannot export CSV. Inspect the evidence beside it:

- `EXPORT-v2:p1`, version 2, says CSV export is available on paid plans only.
- `EXPORT-v1:p1`, version 1, says exports are available on every plan and remains visible as replaced/conflicting evidence.

The newer document wins because it explicitly **supersedes** the older one. Its date or status label alone would not establish authority. Q1 is **Awaiting approval**; generating and checking it has not approved it.

### 2. Correct, approve and reuse the exact wording

Click **Edit answer**. Replace only **Answer wording** with:

```text
Free-plan users cannot export CSV; CSV export is available on paid plans only.
```

Keep the source/excerpt rows, answer status and unresolved reason unchanged. Click **Save and check**. A saved real checker exists for this precise proposal, preserved in [examples/q1-correction.json](examples/q1-correction.json). The check should pass, and the answer should still await human approval.

Click **Approve answer**, enter a clearly labelled name such as `Demonstration reviewer`, review the evidence, check the confirmation and click **Confirm approval**. The required role is **Product reviewer**, taken from the supplied topic mapping. This is your explicit local demonstration action; Gemini never grants approval.

Open **Reuse approved answer**, enter the exact original question below and click **Look up approved answer**:

```text
Can free-plan users export CSV?
```

Expect **Eligible approved answer**, the corrected sentence, the reviewer/role/timestamp and both source records. Reload the browser, return to this tab and repeat the lookup. The same approval and evidence should persist in SQLite. The app's history retains the original model wording and the reviewer correction.

### 3. An unapproved edit must not become reusable knowledge

Return to **Review**, open **Edit answer**, change only the wording to `Unapproved demonstration edit awaiting review.` and click **Save and check**.

The edit is saved, but **No exact replay match** is visible: this new proposal has no recorded checker. Approval is disabled and the pending text remains a draft. Repeat the original Q1 lookup. It should still return the previous approved correction, not the pending wording. This failure is intentional and demonstrates that replay and approval safeguards stay active.

### 4. Q2: an undocumented feature stays unknown

Select **Q2 · Is JSON export available?** and click **Create answer**.

Expect **Unresolved**, an explanation that JSON export is undocumented, no invented supported answer and the **Product reviewer** route. **Approve answer** should be disabled. Use **Leave unresolved** to save a note such as `Ask Product to document whether JSON export is available.`

The lack of documentation does not justify answering either “yes” or “no.” Q2's unresolved disposition is correct. Its current saved empty-answer checker passes separately; earlier checker failures remain historical records rather than being hidden by that disposition.

### 5. Q3: a straightforward supported answer

Select **Q3 · When is email support available?** and click **Create answer**.

Expect Monday to Friday, **09:00–17:00 UTC**, supported by `SUPPORT-v1:p1`. The status is **Awaiting approval**, and the visible passage lets you check the claim yourself. For comparison, Q4 can answer that live chat is not offered because the same passage explicitly documents that negative statement.

### 6. Change a source version and block reuse

Do this last, because it changes the demonstration's source snapshot. On **Sources**, expand **Edit or remove a working source**, choose **EXPORT-v2**, and change only its JSON `version` value from `2` to `3`. Keep the document ID, passage ID, text and `supersedes` value unchanged. Confirm **This working source follows the exercise rules**, then click **Save working source**.

Return to Q1. Its status should be **Needs fresh review**. Repeat the Q1 lookup: expect **No eligible approval for this exact question**. The previous version-2 evidence remains in the answer/history, but is no longer eligible for current reuse. The supplied fixture files have not changed; you edited a persisted working copy.

A source change invalidates the corpus snapshot, so this implementation conservatively requires fresh review of all existing approvals. Returning to eligible reuse needs a newly checked and explicitly approved revision. The original version-2 captures cannot validate a version-3 request. Start a new demonstration database to repeat the original flow.

## How the implementation supports the flow

The application is one local Python/Streamlit process with SQLite and the official Google Gen AI SDK. The small corpus fits in a request, so it needs no retrieval service or separate frontend/API.

| File | Responsibility |
| --- | --- |
| [app.py](app.py) | Question queue, side-by-side review, explicit edit/approval/unresolved actions and reuse/source/history tabs |
| [workspace/schemas.py](workspace/schemas.py) | Shared Pydantic contracts and captured-run/transport data |
| [workspace/prompts.py](workspace/prompts.py) | Separate draft/check instructions and source-use rules |
| [workspace/evidence.py](workspace/evidence.py) | Source/reference integrity, excerpt matching, supersession and semantic-check findings |
| [workspace/gemini.py](workspace/gemini.py) | Real native structured-output calls, raw capture and exact-request replay |
| [workspace/store.py](workspace/store.py) | Atomic SQLite initialization/import, immutable revisions/evidence/checks, persisted approvals and source history |
| [workspace/service.py](workspace/service.py) | Coordinate checks and reviewer actions; bind approval to exact wording/current source revisions and gate reuse |

Structured output controls the response shape. Deterministic checks establish that IDs/excerpts exist and validate authority; a separate model check examines the entire answer for unsupported claims and conflicts. None of those automatically establishes human approval. Malformed output, bad references, checker failures and provider errors have visible outcomes and cannot silently produce an approval.

## Expected results and verification

| Minimum demonstration requirement | What to observe |
| --- | --- |
| Supported answer with valid evidence | Q3 support hours and `SUPPORT-v1:p1`; Q1 also cites its authoritative passage |
| Unsupported/undocumented question routed for review | Q2 remains unresolved with Product reviewer |
| Outdated-policy conflict shown and resolved through explicit metadata | Q1 uses `EXPORT-v2:p1`, keeping `EXPORT-v1:p1` visible |
| Approved correction reused; unapproved edit excluded | Exact Q1 lookup returns only the approved corrected sentence |
| Approval/evidence survive reload; changed source requires review | Reload preserves Q1; the version change blocks reuse and retains old evidence |

Run these in another repository-root terminal, or stop the UI first:

```powershell
.venv/Scripts/python.exe scripts/verify_q1_demo.py --output .tmp/walkthrough-checks/q1
.venv/Scripts/python.exe scripts/verify_reference_cases.py --output .tmp/walkthrough-checks/reference
.venv/Scripts/python.exe -m pytest -q --basetemp=.tmp/walkthrough-tests
.venv/Scripts/python.exe -m ruff check app.py workspace tests scripts
```

The first two commands are offline and use isolated databases. The Q1 report covers the real draft/check and fixed correction plus demonstration approval/reuse, pending-edit exclusion, reload and source change/removal. The reference command writes `reference-results.md` and `.json` under the chosen output directory, comparing separate expected results with observed behavior. Inspect its **current**, **provenance** and **checker** fields: current real replay should pass Q1–Q8; new live verification is not claimed by an offline run. Synthetic cases and retained historical outcomes are labelled separately.

The last recorded full suite on 9 October passed **163 tests**, with Ruff, compilation and dependency checks also passing. Its coverage includes invalid model output, nonexistent/irrelevant evidence, unsupported added claims, provider/replay failures, persistence and source invalidation. These failure tests are explicitly synthetic. Automated test approvals are isolated demonstrations, not working-data approvals. AppTest/server execution requires localhost sockets; the Windows Codex sandbox needed elevated execution for those checks.

## AI workflow and limits

Codex helped plan, implement and review the solution. [LLM_USAGE_NOTE.md](LLM_USAGE_NOTE.md) records selected original instructions, generated work and the Q2 correction. [ai-workflow/README.md](ai-workflow/README.md) and [manifest.json](ai-workflow/manifest.json) record actual models, instructions/skills, scripts, tool/permission settings and recoverable earlier versions, with redactions and unavailable details stated explicitly.

This is a local prototype: reviewer names are entered rather than authenticated, reuse requires an identical question, and any source-corpus change invalidates approvals conservatively. Saved real responses demonstrate the exercised requests, not reliability on arbitrary questions. Other edits need matching recorded checks or authorized live validation; live API availability is not tested by offline replay. Model-based semantic checking can still be wrong, which is why source inspection and explicit human review remain part of the product flow.
