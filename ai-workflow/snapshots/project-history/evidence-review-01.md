---
name: evidence-review
description: Design, implement, or review the variant C questionnaire answer flow when source evidence, approval, reuse, or source-version changes are involved.
---

# Evidence and review flow

Use this skill for work on the assignment's answer lifecycle. First read the actual starter-pack rules and current implementation; treat missing details as unknown.

- Sketch the smallest end-to-end state flow needed for the current change: source/version -> cited draft -> human review -> approved answer -> eligible reuse. Make any transition caused by a source-version change explicit.
- Keep evidence identifiable enough to verify a claim against the specific document and version. A link or citation that cannot be resolved to its source is not sufficient evidence.
- Ensure a real model call is distinguishable from a mock or manual entry in implementation and reporting. Never turn a generated draft into an approval implicitly.
- For reuse, check approval status and source version at the point of reuse, not only when the answer was first stored.

## Acceptance and failure cases

Use the starter pack to resolve exact policies. Apply the cases relevant to the change; cover the whole lifecycle at final acceptance.

| Case | Observable check |
| --- | --- |
| Cited draft | The reference resolves to the exact document/version and the cited content supports the answer's claim. |
| Human approval | Approval follows an explicit human action; generating or editing a draft does not approve it. |
| Approved answer reused | Eligibility checks approval and the applicable source version when reuse occurs. |
| Unapproved answer | A draft or answer requiring review is excluded from approved-answer reuse. |
| Source version changes | Affected answers require review and are excluded from approved-answer reuse until reviewed and approved again. |
| Missing or insufficient evidence | The gap is visible; the model does not invent facts or references, or silently approve the answer. |
| Source unavailable | The unavailable reference is reported; current source verification is not claimed. Distinguish previously captured evidence from a successful current lookup. |
| Model call fails | The failure is visible, existing review/approval state is preserved, and no successful generation or approval is fabricated. |

Verify with the smallest meaningful checks available in the chosen stack. Record the scenario, expected behavior, observed result, and whether it was exercised at runtime or inspected in code. Keep real model calls distinguishable from mocked checks. Report cases that remain unverified; do not create a test suite before there is implementation to check unless the current task needs one.
