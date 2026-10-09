# AI workflow used during this exercise

Questionnaire Evidence & Review Workspace, variant C. Recorded on 9 October 2026 using starter-pack version `2026-10-02`. [manifest.json](manifest.json) completes all nine categories from the supplied template. It records what was used and what can be recovered; unavailable details are labelled explicitly.

## Tools and models

| Stage | Recorded configuration |
| --- | --- |
| Initial project/workflow setup, 7 October | Codex Desktop, embedded runtime `0.160.1`; `gpt-6-sol` then `gpt-6.1-sol`, reasoning `medium` |
| Planning, implementation, review and fixes, 8–9 October | Codex Desktop, embedded runtime `0.162.0-alpha.2`; `gpt-6.1-sol`, reasoning `high` |
| Application draft and semantic check | Google's `gemini-3.1-flash-lite`, `google-genai==2.29.0`, temperature `0`, max output tokens `8192`, timeout `30000 ms`, native JSON structured output and shared Pydantic v2 contracts |
| Earlier application attempts / synthetic fixture setting | `gemini-3.8-flash` appears in earlier attempted real requests and explicitly labelled synthetic requests. It is not the current successful replay model. Historical failure/configuration records are retained. |
| Verification | Python `3.12.14`, Streamlit `1.65.0`, Pydantic `2.13.5`, pytest `9.1.1`, Ruff `0.16.10`; dependency pins remain in the normal requirements files |

Model/effort/runtime history comes from selected project session metadata, not a guess based on the current default. The current applicable user settings are saved in [user-settings.json](snapshots/user-settings.json): model/effort, explicit context/compaction values, default service tier, browser feature flag, Windows sandbox and project trust. Those are a snapshot of configured values, not claims about a model's capabilities. Other coding-model decoding defaults were not exposed in the reviewed records and are `not-exportable`.

The app-managed tools used for this work include Codex chat/project/file tools and local browser automation. Installed versions are `codex-app-tools` `0.1.5` and browser/computer-use runtime components `26.1002.52244`. [tool-settings.json](snapshots/tool-settings.json) keeps only their relevant configuration. Other installed personal plugins and account connections are omitted; installation alone does not establish usage.

## Configuration files and history

| Configuration | Active location / saved record | Restore or inspect |
| --- | --- | --- |
| Standing project instructions | [../AGENTS.md](../AGENTS.md) | Keep at the repository root for coding-agent work |
| Implementation instructions and choices | [../IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md), [../README.md](../README.md) | Read the plan as a historical implementation specification, then current README/status |
| Active domain and feature review skills | [evidence-review](../.agents/skills/evidence-review/SKILL.md), [feature-review](../.agents/skills/feature-review/SKILL.md) | Keep at `.agents/skills/`; invoke the applicable checklist when needed |
| Earlier project instructions/skills | [project-history/index.json](snapshots/project-history/index.json) | Named full snapshots and intermediate patches have source events and hashes; initial committed state is `77957afab3e75630946872795d89a4f7ec864504` |
| Removed setup experiment skills | `feature-design` / `feature-implementation` snapshots in project history | Archive only: removed before implementation, not active or used to implement the app |
| Installed built-in guidance read during work | [builtin-guidance/index.json](snapshots/builtin-guidance/index.json) | Current installed-file snapshots and the skill validator are reference copies; use the complete installed tool bundle to restore them |
| Runtime collaboration assignments | [subagents.json](snapshots/subagents.json) | Records temporary review/configuration tasks and inherited settings; no reusable standalone agent package was configured |
| Application instructions, schemas and parameters | [../workspace/prompts.py](../workspace/prompts.py), [../workspace/schemas.py](../workspace/schemas.py), [../workspace/gemini.py](../workspace/gemini.py), [../workspace/evidence.py](../workspace/evidence.py) | Active prompts and contracts are separate from transport and evidence checks; document/question content travels as evidence data |
| Earlier application configuration | [application-history/index.json](snapshots/application-history/index.json) | Exact captured prompts, settings and schemas are preserved as named historical snapshots, including failing configurations |
| Real replay and fixed correction | [../examples/README.md](../examples/README.md), [capture provenance](../examples/capture-provenance.json), [Q1 proposal](../examples/q1-correction.json) | 17 original real captures are in `examples/real-replay/`; request matching remains exact |
| Local UI and environment | [../.streamlit/config.toml](../.streamlit/config.toml), [.env.example](.env.example) | Streamlit binds to `127.0.0.1`; usage-stat collection is off. Environment examples contain names and harmless defaults only. |

The two project skills were kept small. Ideas from reviewed `autopilot`/`report` material were not installed as extra active skills; the resulting checks are in the two existing project files. The starter's data-generation guidance was consulted as reference material. No new unused skill, agent or hook was created to fill the manifest.

Subagents were used for bounded backend/integration review, capture/reporting review, feature audit/startup diagnosis and this configuration-history audit. Their effective inherited model/effort is recorded. Two available assignments are preserved as text. Some earlier task payloads are encrypted in local session storage and have no available export key: they are `not-exportable`, not reconstructed or replaced with invented prompts. Whole chat logs and ciphertext are excluded. Earlier built-in guidance revisions and complete prior user-level config revisions are also unavailable; current snapshots are labelled as current rather than silently substituted for old versions.

## Hooks, scripts and permissions

There is no custom `.codex/hooks.json` or project hook script. Preparation, live verification and replay scripts are run manually; none is a startup, pre-tool or pre-push hook. Their normal files remain under `scripts/` and are listed in the manifest.

The host has a bundled `notify` command with the event `turn-ended`. It is an app-managed notification/automation integration, not a custom project hook. Its executable path is host-specific and omitted. No custom hook is required or enabled by this submission.

The observed session used `workspace-write`, restricted network access and approved elevated executions for localhost UI checks and the specifically authorized Gemini payload. Session logs record `on-request`; the current desktop approval reviewer is `auto_review`. Host config also records Windows `sandbox = elevated`. These describe different configuration layers, not a blanket permission to run arbitrary commands. Project trust and permission snapshots are documentation; restoring the application does not require changing a reviewer's security settings.

Keep user-level configuration at the tool's normal location. To reproduce coding assistance, open the repository in Codex, retain its `AGENTS.md` and two project skills, and select the recorded model/effort if available. Inspect relevant snapshot settings before applying any of them. Let the app provision its own MCP/browser runtime; machine executable paths, browser trust hashes and named-pipe instances cannot be restored from generic placeholders. Application replay has no dependency on Codex, MCP, custom hooks or account connections.

## One workflow example

The planning request in **Plan evidence review app** separated investigation from implementation:

> For now, I only need a plan. Read the repository and work out how to build and verify the application. Don’t write code, change files, install dependencies, or call model APIs. Implementation will be a separate task.

`AGENTS.md`, the two review skills and the supplied evidence rules directed the plan toward the source → cited draft → human review → approval → exact reuse → source-change flow. I then corrected one implementation choice:

> fix your plan a bit, we should use pydantic for schemas

That choice became shared Pydantic contracts for input, native model output and live/replay/edited-answer validation. A later review found that Q2's expected unresolved status had been reported too broadly as success even though its checker response was invalid. Empty-answer instructions and result reporting were corrected; strict validation and old failure records were preserved. The fresh Q2 pair passes exact replay while Q2 remains unresolved and unapproved. [LLM_USAGE_NOTE.md](../LLM_USAGE_NOTE.md) preserves the selected original prompts, generated components and correction/verification detail.

## Reproduce or replay

From the repository root, create a Python 3.12 environment and install the pinned dependencies:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe scripts/verify_q1_demo.py --output .tmp/ai-workflow-replay/q1
.venv/Scripts/python.exe scripts/verify_reference_cases.py --output .tmp/ai-workflow-replay/reference
```

The two verification commands never initialize a real Gemini client or read credentials. They create isolated databases, replay the saved responses through the same validators, and report observed outcomes. The Q1 command includes the fixed correction, explicitly labelled demonstration approvals, reuse, pending-edit exclusion, reload and source invalidation. The reference command checks all eight current real draft/check pairs plus independent synthetic lifecycle cases. Synthetic results remain labelled; test approvals are not human approvals in a working database.

For a browser demonstration, choose a fresh database filename:

```powershell
$env:WORKSPACE_DB='.tmp/ai-workflow-browser.sqlite3'
$env:WORKSPACE_VERIFICATION='0'
$env:WORKSPACE_ALLOW_LIVE='0'
Remove-Item Env:GEMINI_MODEL, Env:WORKSPACE_REPLAY_DIR, Env:WORKSPACE_SEED -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Then follow [the Q1 demonstration](../examples/README.md). `.env.example` is documentation and is not automatically loaded by the app. The app reads `GEMINI_API_KEY` from its process environment only on explicit live actions. Explicit live-verification scripts also accept `GOOGLE_API_KEY` as an alias and can read known values from an ignored local `.env`; keys are never saved in captures. `WORKSPACE_ALLOW_LIVE=0` is the documented default. No key or new model call is needed for the commands above.

## Redactions, decisions and limitations

Only exercise-specific records were exported. API keys, tokens, account authentication, full personal configuration, unrelated project settings, private URLs and whole chat logs are excluded. Local workspace/user paths use `${REPO_ROOT}`, `${CODEX_HOME}`, `${USER_HOME}` or artifact-scope placeholders. Machine executable paths, runtime pipe names and build-specific trust hashes are omitted with their purpose explained in the snapshots. `not-used`, `default`, `used`, `redacted` and `not-exportable` distinguish actual usage from available or planned tools.

One local process, two focused review skills and explicit verification suited the small fictional corpus. No embeddings, agent framework or background worker was needed. Model checking is not a guarantee of factual correctness; reference inspection, deterministic checks and explicit reviewer confirmation remain part of the flow. Replay requires the pinned SDK and exact prompts, source snapshot and proposed wording; a different edit needs its own saved check or authorized live validation. The additional exercise uses synthetic responses and has no real extension captures.

If I repeated the exercise, I would version configuration changes earlier, preserve plaintext bounded agent assignments as they are created, and package a small working replay set from the start. This export does not invent missing history or require a reviewer to enable unfamiliar hooks.
