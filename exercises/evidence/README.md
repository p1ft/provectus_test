This separate starter extension contains the original documents, questions and reviewer mapping unchanged, plus five questions and three short fictional documents. XLSX export is documented; YAML export remains unknown. Two independent invoice-dispatch sources conflict and neither explicitly supersedes the other. No date-based authority or seeded policy change is introduced.

Run the five scenarios with synthetic exact replay and a new isolated database:

```powershell
.venv/Scripts/python.exe scripts/verify_extension.py --output .tmp/extension-demo
$env:WORKSPACE_SEED='exercises/evidence/seed.json'
$env:WORKSPACE_DB='.tmp/extension-demo/browser-new.sqlite3'
$env:WORKSPACE_VERIFICATION='1'
$env:WORKSPACE_ALLOW_LIVE='0'
$env:WORKSPACE_REPLAY_DIR='.tmp/extension-demo/synthetic-captures'
Remove-Item Env:GEMINI_MODEL -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

Use a fresh database filename: startup never replaces existing questions or sources. `expected-results.json` declares the exercise separately from synthetic responses; the app never reads it.

Draft EXT-SUPPORTED and EXT-UNKNOWN, then EXT-CONFLICT to see both conflicting passages and blocked approval. Explicitly demonstration-approve EXT-SUPPORTED; repeat EXT-REUSE's identical question to get that approved wording. An unvalidated edit must not replace the reusable approval. Approve EXT-CHANGE, change EXPORT-EXT to version 2 by adding “Export files include a header row.”, then confirm review-required status and blocked reuse with version 1 evidence retained. Save a fresh edit, validate and explicitly approve before reuse. These exact source updates have synthetic checking captures.

The additional inputs and expectations were prepared with Codex assistance as fixed JSON snapshots, without randomized dataset generation. Expected results are separate from synthetic model fixtures and were checked against the passages and exercise rules; original records remain unchanged.

This exercise verifies application behavior with explicitly synthetic responses. Real Gemini behavior for these additions is unverified because no saved real extension captures exist. The original-question Q1/Q2 issues are historical: current `examples/real-replay/` covers Q1–Q8 and the fixed Q1 correction, with Q2 correctly unresolved and its independent checker passing.
