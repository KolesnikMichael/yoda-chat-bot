---
id: TASK-014
doc: implementation-notes
updated: 2026-07-20
---

# TASK-014 implementation notes

- Review fix: plan step 3.3 specified marker-based seed recognition but did not
  require structural matching against message role, wrapper boundaries, and the
  exact persisted legacy catalog suffix. Raw substring matching could truncate
  user data or misclassify user-authored markers. The fix recognizes the
  adjacent generated `system`/`user` wrapper pair and reconstructs the legacy
  suffix from the persisted catalog before replacing it. Adversarial tests now
  cover marker and legacy-delimiter literals in user data.
- ADR candidate: none; this tightens design Decision 5 without changing the
  architecture or external contract.
