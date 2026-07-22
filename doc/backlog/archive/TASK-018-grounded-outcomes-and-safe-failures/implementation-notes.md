# TASK-018 implementation notes

## Workplace

- Pre-flight dirty tree waived by user: TASK-018 requirements/design/plan/task
  docs left unstaged while implementing on `feat/EPIC-002-agent-routing-reliability`.

## Plan lessons

- Evidence-free `finish` is a `transient` failure (design Decision 2). Several
  agent tests previously expected success after clarify/correct without a
  successful tool; they were updated to either dispatch a successful tool before
  finish or assert the transient outcome.
- Failed tool results are labeled `(FAILED, not outcome evidence)` in the loop
  transcript so models and tests can distinguish display context from typed
  evidence.

## Compatibility

- New delivery lines use prefix `GROUNDED DELIVERY:` (added to
  `KNOWN_TASK_RESULT_PREFIXES`); all legacy prefixes retained.
- Protocol 4 persists `outcome_evidence`; missing legacy field loads as `[]`.
- No job/conversation/profile migration.

## Manual AC (7.2)

- Skipped: no live Redis/Telegram in this run. Covered by deterministic tests in
  Stage 7.1.

## Review fixes

- JSON string encoding alone does not protect an XML-like trust delimiter:
  source text can contain a literal `</delivery_data>`. Delivery serialization
  now escapes delimiter-significant characters as JSON Unicode escapes, with an
  adversarial round-trip test.
- Successful evidence alone cannot represent an unresolved terminal failure:
  an earlier image-generation or data-read result could otherwise authorize a
  later `finish` after send/delete failed. Protocol-4 sessions now persist a
  boolean terminal-failure guard; a later successful terminal retry still wins.
