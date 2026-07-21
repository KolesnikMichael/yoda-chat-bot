# TASK-020 implementation notes

## Corpus maintenance

- `tests/fixtures/routing_evaluation/build_corpus.py` regenerates
  `corpus-v1.json`. Run after adding skills or stage families.
- Corpus version 1.1.1 has 26 cases, including `no_skill`, selection
  successful correction (`en-selection-protocol-corrected`), protocol
  exhaustion, refinement, strict-domain retry, delayed dynamic work,
  relative delay, and scheduled constrained execution.

## Harness

- Multi-turn cases share `InMemoryStorageApi`, production `MemoryProvider`, and
  a stable hash-derived `chat_id`; conversation and agent-session state persist
  within the case.
- Recorded structured-response adapters preserve JSON/Pydantic exception types
  so `LanguageProvider` reaches the production `StructuredOutputError` recovery
  path.
- Claim-token expectations are exact sets, not required subsets; the generator
  writes every allowed and prohibited token explicitly.

## Review fix (2026-07-21)

- Added `en-selection-protocol-corrected` so FR-6 / Decision 7 cover selection
  `recovery: corrected` as well as `exhausted` (paired with planning correction
  in `en-strict-constraint-overrides-preference`).

## Follow-up for TASK-021

- Live runner should import `yoda.mind/evaluation/` only; keep recorded adapters
  test-local.
