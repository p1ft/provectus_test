---
name: feature-implementation
description: Implement an authorized feature or bug fix in this assignment from its request or design through runnable verification.
---

# Implement a feature

Read the request or existing design and inspect the affected code, dependency manifests, and available checks. If a material design choice remains unresolved, use `../feature-design/SKILL.md`; do not manufacture a separate design phase for a straightforward fix.

- Work through the smallest runnable slice of the requested flow. Follow the acceptance cases and the project's actual conventions; introduce a dependency only when it removes necessary work.
- For a bug, reproduce its observable failure before changing behavior when feasible. For a new feature, choose checks that would catch a broken acceptance case, rather than tests that duplicate the code.
- Keep mocked model responses explicit. When a real integration is required, verify it with available access; if credentials are missing, finish independent work and report the integration as unverified.
- When changing evidence, approval, reuse, or source versions, read `../evidence-review/SKILL.md` and carry the relevant cases into implementation checks.
- Record the actual setup/run/test commands once they work. Capture consequential implementation choices in README.md so another developer can reproduce the result.

Run the relevant checks, fix failures introduced by the change, and inspect the final diff. Use `../feature-review/SKILL.md` for the completion review. Report the implemented behavior, verification results, and remaining limitations; do not turn an incomplete integration into a completion claim.
