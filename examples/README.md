# Real-response Q1 review demonstration

`real-replay/` contains 17 saved real Gemini responses on `gemini-3.1-flash-lite`: one draft/check pair for each Q1–Q8 plus a checker for the fixed Q1 correction. Q1 was captured fresh for the current prompts. Q2 is the verified empty-answer pair; Q3–Q8 are unchanged earlier captures. `capture-provenance.json` records original sessions, exact request fingerprints and SHA-256 file hashes. These files contain only fictional exercise data and provider response metadata, with no API keys or reviewer identities. Historical captures remain under ignored `artifacts/real-runs/`.

Run from the repository root with installed pinned dependencies. Choose a fresh database filename if the example below already exists:

```powershell
$env:WORKSPACE_DB='.tmp/q1-presentation.sqlite3'
$env:WORKSPACE_VERIFICATION='0'
$env:WORKSPACE_ALLOW_LIVE='0'
Remove-Item Env:WORKSPACE_REPLAY_DIR, Env:GEMINI_MODEL, Env:WORKSPACE_SEED -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m streamlit run app.py
```

1. Q1 opens first. Click **Create answer**. Inspect `EXPORT-v2:p1`, version 2, and the visible replaced conflict `EXPORT-v1:p1`, version 1.
2. Open **Edit answer**. Replace only the answer wording with the exact text below. Keep citations, disposition, reason and conflicts unchanged; `q1-correction.json` preserves the complete checker proposal.

   ```text
   Free-plan users cannot export CSV; CSV export is available on paid plans only.
   ```

3. Click **Save and check**. Its recorded real checker passes, but saving/checking does not approve the answer.
4. Click **Approve answer**, use a clearly labelled demonstration reviewer name, review the evidence and confirm explicitly. This is a local demonstration approval, not a working approval or a decision made by Gemini.
5. On **Reuse approved answer**, enter `Can free-plan users export CSV?` exactly. The corrected approved wording, reviewer and source versions appear.
6. Reload the browser and repeat the lookup. Approval and evidence persist.
7. Optionally save a different pending wording. Its missing exact checker is visible, approval is blocked, and reuse still returns the previous eligible approved correction.
8. On **Sources**, change the working version of `EXPORT-v2` from 2 to 3. Reuse becomes ineligible and Q1 requires fresh review; the old evidence remains. A new source snapshot needs its own recorded check or an explicit live check before another approval.

Select Q2 and create its draft to show the undocumented JSON-export gap and Product reviewer route. It remains unresolved and cannot be approved. Q3–Q8 are also available without credentials.

For automatic verification in separate databases, with environment/credential access and live fallback prohibited:

```powershell
.venv/Scripts/python.exe scripts/verify_q1_demo.py
.venv/Scripts/python.exe scripts/verify_reference_cases.py --output .tmp/q1-reference
```

The first command verifies Q1's real draft/check, the fixed correction check, explicit demonstration approval/reuse, unapproved-edit exclusion, reload, and changed/removed sources. All approvals are isolated demonstrations. Exact request matching and all evidence validators remain enabled; arbitrary new wording cannot use the fixed correction's checker response.
