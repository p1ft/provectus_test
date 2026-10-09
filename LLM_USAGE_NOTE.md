# LLM usage note

Questionnaire Evidence & Review Workspace — variant C, 9 October 2026.

## Tools, models and generated work

I used Codex to plan, implement, test and review the application, then asked for targeted corrections. AI assistance covered most of the implementation, tests and documentation. The original fictional evidence and supplied expected results came from the starter pack and were preserved.

| Tool / model | Use |
| --- | --- |
| Codex desktop, embedded runtime `0.160.1`, `gpt-6-sol` then `gpt-6.1-sol`, reasoning `medium` | Initial repository and workflow setup on 7 October; verified from that chat's runtime/model records. |
| Codex desktop, embedded Codex runtime `0.162.0-alpha.2`, `gpt-6.1-sol`, reasoning `high` | Repository analysis, implementation planning, Python/Streamlit code, tests, debugging, separate review chats and documentation. Runtime version and model settings were checked against the relevant chat logs; the desktop shell build was not recorded there. |
| Gemini, `gemini-3.1-flash-lite`, official `google-genai` 2.29.0 | The application's real answer drafting and semantic evidence checking. Saved requests use temperature 0, an 8192-token output limit, a 30-second timeout and native structured output derived from shared Pydantic contracts. |
| pytest, Ruff and browser tools | Automated checks and inspection of the actual review, approval, reuse and reload flows. |

Earlier `gemini-3.8-flash` attempts encountered provider/checker failures. Their records were retained separately from successful calls. Synthetic fixtures are labelled test data; replay uses saved real responses and makes no new model call.

Codex generated the implementation plan, SQLite persistence and answer lifecycle, evidence validation, Gemini adapter and capture/replay support, Streamlit interface, tests, verification scripts and supporting documentation. It also helped create the separate fictional extension under `exercises/evidence/`. The main implementation is in [app.py](app.py) and [workspace/](workspace/); tests and verification scripts are in [tests/](tests/) and [scripts/](scripts/).

## Representative instructions

These are selected original instructions submitted in the project chats. The planning example is excerpted to keep this note brief. Assistant-generated handoff instructions are not presented as my own prompts.

### Planning the complete implementation

From **Plan evidence review app**:

> Plan the implementation of Questionnaire Evidence & Review.
>
> For now, I only need a plan. Read the repository and work out how to build and verify the application. Don’t write code, change files, install dependencies, or call model APIs. Implementation will be a separate task.
>
> Keep the scope realistic for one working day. Focus on the application and its tests; leave presentation materials, submission documentation, and AI workflow records out of this phase. Keep the plan concise and prioritize the required end-to-end flow.
>
> Start by reading AGENTS.md, README.md, the project skills, and everything in tasks/evidence/. Inspect the repository so the plan reflects what already exists. Use tasks/evidence/domain.md as the authority for domain behaviour, and leave the original evidence fixtures and expected results unchanged.

Two further excerpts from the same instruction:

> A citation can be valid without supporting the claim. Irrelevant citations and unsupported extra claims must be detected or clearly left unresolved.

> Don’t hardcode answers by question ID or use expected-seed-results.json as application logic.

The full request specified Python, Streamlit, SQLite and the official Gemini SDK, without LangChain or an agent framework. It required acceptance coverage for supersession, unknown capabilities, reviewer corrections, approved reuse, reload persistence, source invalidation and visible failures. The resulting [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) was used for staged implementation: backend steps 1–4, followed by UI and verification steps 5–7.

### Correcting the schema choice

Also from **Plan evidence review app**:

> fix your plan a bit, we should use pydantic for schemas

This made shared Pydantic v2 contracts an explicit requirement for source data, structured model output and validation of live responses, replay and reviewer edits. Native structured output was subsequently confirmed in the same chat. Local evidence and approval checks remained necessary beyond schema validation.

### Questioning a failed check

From **Fix Questionnaire Evidence & Review…**:

> what q2 still fails? does it have to fail as planned or we need to fix smth?

This exposed an important distinction: Q2 should remain unresolved because JSON export is undocumented, but its checker should still return a valid response. The subsequent correction is described below.

### Challenging the interface

From **Оценить сложность UI задания**:

> посмотри UI этого задания. не кажется ли тебе что он сейчас слишком сложный, AI слопный и имеет слишком много всего как для такого задания? или это скорее вынужденная мера для задания

The review found that the main screen mixed reviewer tasks with replay settings, raw JSON and diagnostics. After I asked Codex to apply the suggested changes, the UI kept the question queue and answer/evidence together, opened forms only after an explicit action, and moved technical details into separate sections. Human approval stayed explicit.

## Correction and verification

Q2's earlier checker substituted invented answer text for an empty proposal and returned invalid evidence references. A correct unresolved disposition had also been reported too broadly as a passing result. Review separated question disposition, checker parsing and semantic acceptance instead of treating them as one outcome.

The correction explicitly instructed the empty-answer checker to copy the exact empty answer, never the unresolved reason, and to use only relevant passage references. Validators were kept strict and failed captures were retained. A fresh real Q2 draft/check pair passed with zero findings and matched credential-free replay. Q2 remained unresolved, routed to Product and unapproved. This is a correction to model instructions and reporting, not a change to the expected product answer.

For this note, I reran both offline verification commands in isolated databases:

```powershell
.venv/Scripts/python.exe scripts/verify_q1_demo.py --output .tmp/llm-usage-note-audit/q1
.venv/Scripts/python.exe scripts/verify_reference_cases.py --output .tmp/llm-usage-note-audit/reference
```

Both passed. The Q1 demonstration checked the corrected wording, explicit demonstration approval, exact-question reuse, exclusion of unapproved edits, reload persistence and invalidation after a source change or removal. The reference report checked independent expectations and current Q1–Q8 real-response replay. No credentials or new model calls were used for these runs.

The current repository includes 17 real captures: Q1–Q8 draft/check pairs plus the fixed Q1 correction check. [examples/README.md](examples/README.md) explains reproduction; [capture-provenance.json](examples/capture-provenance.json) records request fingerprints and file hashes. Arbitrary new edits require their own matching capture or live validation. The extension is verified with labelled synthetic responses, not real Gemini captures.

Standing instructions and the domain/review checklists are saved in [AGENTS.md](AGENTS.md) and [.agents/skills/](.agents/skills/). Credentials are excluded from the repository. The LLM usage note is separate from the assignment's AI configuration manifest.
