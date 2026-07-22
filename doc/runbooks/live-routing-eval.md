# Live routing evaluation

On-demand live-model runs over the routing evaluation corpus. **Not** PR/CI
gating — cost, rate limits, and model drift make scores informational only.
Pytest never invokes this CLI and does not require live credentials.

## Prerequisites

- Project `settings.json` with `agent.model_name` and `llm.api_key`
- Corpus: `tests/fixtures/routing_evaluation/corpus-v1.json` (default)

## Run

```bash
.venv/bin/python -m yoda.mind.evaluation.live_runner \
  [--case CASE_ID] \
  [--corpus PATH] \
  [--report-dir PATH] \
  [--settings PATH]
```

- **Full corpus:** omit `--case`
- **Single case:** `--case <stable-id>` (unknown IDs fail before any model call)
- **Defaults:** corpus `tests/fixtures/routing_evaluation/corpus-v1.json`, report
  dir `artifacts/live_routing_eval/`, settings `settings.json`

## Side-effect boundary

Only the configured `LLMApi` may network. Telegram, Tavily, media, Redis,
scheduler, and Chroma are fail-on-call. Tool outcomes come from
corpus-recorded fixtures.

## Reports

Unique JSON under `artifacts/live_routing_eval/` (gitignored) with model id,
prompt id/hash pairs, corpus version, exclusions, stage metrics, and scored
eligible cases. Console summary prints the artifact path.

Incomplete, excluded, or unattempted cases do not inflate stage pass rates.
Forced-malformed/recovery fixtures are excluded with stable reasons;
deterministic CI still scores them.

## Deterministic CI (contrast)

Structural routing quality in CI uses recorded adapters — not live models:

```bash
.venv/bin/python -m pytest tests/test_routing_evaluation.py -q
ROUTING_EVAL_CASE=<stable-id> .venv/bin/python -m pytest tests/test_routing_evaluation.py -q
```

Module layout and contracts: `yoda/mind/evaluation/AGENTS.md`.

## Production telemetry

`Mind`, `Agent`, and `CognitionProvider` emit privacy-safe INFO/WARNING stage
diagnostics via `RoutingTelemetryCore` (no user content at those levels).
