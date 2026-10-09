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

Report actionable findings with file/location, the trigger, and the observable consequence. For an implementation task, fix findings within the authorized scope and rerun affected checks. For a review-only request, report findings without modifying the implementation. State which checks passed, failed, or could not run; absence of findings does not prove untested behavior works.
