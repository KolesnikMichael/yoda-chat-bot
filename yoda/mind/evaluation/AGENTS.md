# Evaluation Module

Routing quality contracts and harnesses for intent → selection → execution →
delivery stages. All corpus text is synthetic (ADR-000).

Code conventions: [../../../AGENTS.md](../../../AGENTS.md)  
Live eval runbook: [doc/runbooks/live-routing-eval.md](../../../doc/runbooks/live-routing-eval.md)

## Layout

```
yoda/mind/evaluation/
  data.py                   # Data — corpus schema, stage results, live report types
  core.py                   # Core — deterministic scorer (RoutingEvaluationCore)
  live_core.py              # Core — live run aggregation
  corpus_provider.py        # Provider — load corpus JSON
  live_report_provider.py   # Provider — write live eval artifacts
  telemetry_core.py         # Core — privacy-safe stage diagnostics
  prompt_identity_core.py   # Core — prompt id/hash for reports
  observation.py            # Integration — ObservingMind / ObservingAgent / ObservingCognitionProvider
  live_evaluation.py        # Integration — live corpus runner
  live_runner.py            # CLI entry point
  live_fakes.py             # fail-on-call fakes for live runs

tests/routing_evaluation/   # recorded LLM/tool adapters (test-only)
tests/fixtures/routing_evaluation/corpus-v1.json
```

## IODA map

| Component | Category | Responsibility |
| RoutingEvaluationCore | Core | Score stage observations against corpus expectations |
| LiveRoutingEvaluationCore | Core | Aggregate live run metrics and exclusions |
| RoutingTelemetryCore | Core | Privacy-safe production stage diagnostics |
| PromptIdentityCore | Core | Stable prompt id/hash pairs for reports |
| RoutingCorpusProvider | Provider | Load and validate corpus JSON |
| LiveEvalReportProvider | Provider | Persist live eval artifacts |
| ObservingMind / ObservingAgent / ObservingCognitionProvider | Integration | Record stage observations without changing production logic |
| LiveRoutingEvaluation | Integration | Orchestrate live corpus runs |
| data.py types | Data | Corpus fixtures, expectations, reports |

## Where to look

| Question | Go to |
| Corpus schema, stable case IDs | `data.py`, `tests/fixtures/routing_evaluation/corpus-v1.json` |
| CI scoring contract | `core.py`, `tests/test_routing_evaluation.py` |
| Live CLI, credentials, artifacts | [doc/runbooks/live-routing-eval.md](../../../doc/runbooks/live-routing-eval.md) |
| Production telemetry | `telemetry_core.py` |
| Epic-level eval strategy (historical) | [archived EPIC-002 design](../../../doc/backlog/archive/EPIC-002-agent-routing-reliability/design.md) — link only; not SoT |

Live eval resolves `agent.model` through `inference`. Only the resolved chat façade (`MistralApi` or `OpenRouterApi`) may network.

## Tests

Deterministic (CI):

```bash
.venv/bin/python -m pytest tests/test_routing_evaluation.py -q
ROUTING_EVAL_CASE=<stable-id> .venv/bin/python -m pytest tests/test_routing_evaluation.py -q
```

Live runs are on-demand — not CI-gated. See the runbook.

## Do not

- Copy production transcripts into the corpus (ADR-000).
- Use live eval as a PR gate (cost, drift).
- Emit user content in telemetry INFO/WARNING logs.
