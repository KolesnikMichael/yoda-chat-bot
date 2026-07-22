# TASK-015 implementation notes

## Legacy selection-instruction matching

Changing `SELECTION_INSTRUCTION` for tool-free selection would break
`refresh_selection_messages` matching against suspended Redis transcripts that
still embed the pre-TASK-015 instruction text.

**What was done:** kept `_LEGACY_SELECTION_INSTRUCTION` with the exact old
wording and try both legacy and current suffixes when rewriting combined
catalog-in-user seeds.

**Design impact:** aligns with Decision 5 (lazy upgrade / opaque history) but
is an implementation detail not spelled out in design.md. Optional follow-up:
document the dual-suffix match under Persistence/rollout.

## Stage ordering

Stages 1–5 were implemented as a tightly coupled rewrite (Data → Core →
Providers → Agent → Mind) rather than leaving `AgentProvider` import-broken
between Stage 1 and Stage 4. Behavior matches the plan; intermediate per-step
commits were not created (user did not request commits during implementation).

## Review fixes

Review exposed that refreshing a legacy pre-selection catalog seed is not
sufficient: the persisted combined system contract must also be replaced with
the selection-specific contract. Both legacy phase upgrades now recognize the
generated combined prompt structurally and replace it with the appropriate
phase prompt. Future compatibility plans should name both seed and base-system
rewrites explicitly.

Structured parsing now uses Pydantic's `model_validate` at the API boundary so
valid JSON with a non-object top level becomes the same normalized validation
failure as other malformed response shapes, without catching unrelated
provider `TypeError`s.
