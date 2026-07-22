# TASK-021 implementation notes

## Incidents / plan divergences

### Circular import: PromptIdentityCore ↔ cognition

`PromptIdentityCore.intent_identity()` needs `INTENT_CLASSIFICATION_PROMPT` from
`cognition.py`, while `CognitionProvider` imports `PromptIdentityCore` for
diagnostics. Eager imports caused a cycle.

**Workaround:** lazy imports inside `PromptIdentityCore` stage helpers
(`intent_identity` / `selection_identity` / `execution_identity` /
`delivery_identity`). ID string constants remain defined both beside production
prompts and re-exported from `prompt_identity_core` for stable values.

`tech-debt: revisit if Core should take control-plane strings only (Integrations
pass material) to restore Core→Data-only dependency without lazy imports.`

### Live isolation adapters duplicated under evaluation

`InMemoryStorageApi` / `RecordedToolProvider` exist under
`tests/routing_evaluation/fakes.py` (TASK-020) and again under
`yoda/mind/evaluation/live_fakes.py` so the live Integration never imports
`tests.*`.

`tech-debt: if a third consumer appears, extract a shared production-safe
recorded-tool + in-memory storage module under yoda/mind/evaluation/.`

### Live runner artifact path

`LiveRoutingEvaluation.run` returns `LiveEvalReport` per design and exposes
`last_artifact_path` for the CLI console summary (avoids double-write).

### Review fix: prompts_used accumulation

`LiveRoutingEvaluation` no longer hard-seeds intent/delivery identities.
`ObservingCognitionProvider` / `ObservingAgent` / `ObservingMind` append
prompt identities into a shared sink at each diagnostic emit so the report
retains every distinct ID/hash actually invoked (FR-2 / FR-6).

## ADR candidates

None. Privacy logging and artifact policy follow existing ADR-000.
