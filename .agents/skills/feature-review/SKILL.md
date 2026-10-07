---
name: feature-review
description: Test and review a feature, bug fix, or implementation diff in this assignment against its acceptance cases before reporting completion.
---

# Test and review a feature

Read the original request, any recorded design, and the changed code with its immediate callers. Compare the implementation with the acceptance cases; do not treat the implementation itself as the specification.

- Select checks for the changed behavior and its realistic failure path. Run the relevant existing tests and required project checks; extend verification only when a failure or unresolved risk justifies it.
- For UI changes, inspect the affected flow and visible error/empty/loading states where applicable. For model integrations, distinguish a real call from a mock and inspect failure handling without exposing credentials.
- For evidence lifecycle changes, use `../evidence-review/SKILL.md` for domain cases. Approval by a coding agent never substitutes for the application's human approval step.
- Inspect the diff for regressions, unrequested scope, and differences between documented commands and actual behavior. Add or amend tests only when they catch a meaningful failure.

## Requirements coverage

For a feature, check the relevant requirements; for final submission, check the original assignment and starter-pack requirements in full, including later user changes. In the review report, map each requirement to implementation evidence and a check/result: implemented, partial, missing, or unverified. Do not silently drop a requirement or label it complete solely because a plan or test says so. Save a short coverage table only when it helps reproduce the review; no separate backlog is required.

This requirements coverage is distinct from `ai-workflow/manifest.json`, which records the AI configuration actually used. At submission review, check that the manifest and README describe actual usage rather than planned tools or fictional runs.

## Final acceptance

Return to the original task and user amendments before judging completion. Run the documented commands and exercise the main user flow against those requirements, even if the implementation matches its design. Passing tests against a design can still miss an original requirement.

For variant C, exercise the evidence-to-draft-to-human-approval-to-reuse flow and a source-version change, using `../evidence-review/SKILL.md`. Include the relevant failure cases. If credentials or a service prevent a real run, report the specific blocked checks as unverified; code inspection and mocks do not establish that the real integration works.

Record commands and observed outcomes. Recheck only affected cases after fixes unless a broader regression risk remains. No separate reviewer agent or dashboard is required.

Report actionable findings with file/location, the trigger, and the observable consequence. For an implementation task, fix findings within the authorized scope and rerun affected checks. For a review-only request, report findings without modifying the implementation. State which checks passed, failed, or could not run; absence of findings does not prove untested behavior works.
