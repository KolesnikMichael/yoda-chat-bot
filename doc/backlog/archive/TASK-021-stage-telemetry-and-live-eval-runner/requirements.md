---
id: TASK-021
doc: requirements
updated: 2026-07-21
---

# TASK-021: stage telemetry and live eval runner — Requirements

← [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/task|Back to task]]

## Context

The deterministic corpus and scorer from
[[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/task|TASK-020]]
can identify structural regressions under recorded model responses, but they do
not show how the configured live model behaves or make production routing
failures consistently attributable to one pipeline stage. Developers currently
have to infer whether a bad result originated in intent routing, skill
selection, tool planning, execution, or delivery from logs with different
vocabularies and incomplete prompt/model identity.

This task adds privacy-safe stage diagnostics to the production routing path and
an explicitly invoked live-model evaluation runner over the TASK-020 corpus.
The runner is for developers evaluating prompt, skill, and model-configuration
changes: it calls only the configured LLM, keeps all state and tool outcomes
isolated, scores the observed structural behavior with the shared evaluator,
and writes a reproducible metadata-rich report. Live results remain
informational because provider cost, rate limits, model drift, and residual
nondeterminism make them unsuitable for the initial pull-request gate.

## Functional requirements

### FR-1: Emit stage-labelled routing diagnostics

The production routing path and live evaluation path must emit diagnostics using
the canonical stages `intent`, `selection`, `planning`, `execution`, and
`delivery`, without changing routing or user-visible behavior.

**Acceptance criteria:**
- [ ] Successful paths emit a diagnostic for every applicable stage reached by
  an ordinary agent-task request, and each record identifies the canonical
  stage and a non-sensitive outcome or transition category.
- [ ] Failure and recovery paths identify the stage that rejected, retried,
  exhausted, blocked, or failed the operation; a later delivery cannot hide an
  earlier-stage failure.
- [ ] Diagnostics distinguish skill selection from execution planning, and
  planning from the resulting tool/job execution outcome.
- [ ] Resume, scheduled-task, chat, and intentionally bypassed paths do not
  report stages that were never applicable as successful or failed work.
- [ ] INFO/WARNING diagnostics contain no user text, recent conversation,
  profile values, distilled task, model response, prompt body, tool arguments,
  tool result, or delivery source text. If any such content is emitted for
  troubleshooting, it is DEBUG-only.
- [ ] Automated tests capture successful, corrective-retry, exhausted,
  execution-failure, and delivery paths and assert their stage labels and
  privacy-safe metadata.

### FR-2: Identify the effective model and prompts

Every LLM-backed stage must expose stable prompt identity and model identity so
production diagnostics and live reports can be compared across code, prompt,
skill, and model-configuration changes.

**Acceptance criteria:**
- [ ] Prompt families use stable versioned identifiers for intent
  classification, skill selection, skill execution, grounded delivery, and
  each activated skill workflow, consistent with the EPIC-002 prompt-identity
  contract.
- [ ] Every LLM invocation records the configured model identifier, applicable
  prompt identifier or identifiers, and a canonical prompt hash in diagnostic
  metadata; no API key, credential, or provider response identifier is stored.
- [ ] The canonical hash covers the effective control-plane prompt material
  that can affect that stage, including the catalog, active workflow, or tool
  schemas when applicable.
- [ ] User-authored text, profile data, tool results, model output, timestamps,
  request IDs, and other per-run data do not affect the canonical prompt hash.
- [ ] Repeating the same canonical prompt material produces the same hash, while
  changing any covered instruction, catalog contract, workflow, or schema
  changes the relevant hash.
- [ ] Live-run metadata preserves every distinct prompt ID/hash combination
  actually invoked, rather than collapsing a multi-skill run to one ambiguous
  hash.

### FR-3: Run the versioned corpus against a live model on demand

The project must provide an explicit developer command that loads the TASK-020
corpus and replaces eligible recorded model decisions with calls to the
configured live LLM while retaining deterministic inputs, local state, tool
outcomes, and stage expectations.

**Acceptance criteria:**
- [ ] The runner loads the checked-in corpus through the reusable production
  evaluation contracts, validates its schema and discovered-skill coverage
  before the first live call, and reports its schema and corpus versions.
- [ ] By default the runner evaluates every live-eligible corpus case, and it
  supports a stable case-ID filter for focused reruns and cost control; an
  unknown case ID fails before any model call.
- [ ] Eligible intent, selection, and planning decisions are obtained through
  the production prompt construction, live `LanguageProvider` parsing, Core
  validation, corrective-retry, and Integration orchestration paths rather than
  by injecting an expected decision.
- [ ] Raw recorded model responses do not influence live decisions for eligible
  calls. Fixed corpus time, synthetic conversation/profile inputs, request
  constraints, expectations, and recorded tool outcomes remain in force.
- [ ] A model-produced wrong route, skill, plan, argument, outcome, or claim is
  retained as an observation and scored as a stage divergence; the runner does
  not rewrite it to the expected value.
- [ ] Cases whose expected behavior depends on forced malformed/rejected
  recorded responses are excluded from live scoring by default, listed by
  stable case ID with an explicit reason, and never counted as passes or
  applicable live cases. Their deterministic CI coverage remains unchanged.
- [ ] Multi-turn, resume, and scheduled-task cases preserve state only within
  their case and start the next case with a clean isolated state.

### FR-4: Isolate live evaluation from real side effects

Only the LLM call may use an external service during a live evaluation. Corpus
execution must not read or mutate production user state or invoke real
user-facing, storage, scheduler, search, or media services.

**Acceptance criteria:**
- [ ] A live run never calls Telegram, Tavily/search, image-generation, vision,
  Redis, ChromaDB, or a production scheduler, even when the model selects an
  unexpected skill or tool.
- [ ] Tool dispatch still passes through production schemas and policy, but
  execution uses corpus-owned recorded results or local no-side-effect adapters.
- [ ] Session, conversation, profile, job, and generated identifier state is
  synthetic, deterministic where required by the corpus, and isolated from the
  running bot.
- [ ] The runner consumes no production transcript or user/profile record and
  sends only the checked-in synthetic corpus content and generated
  control-plane prompts to the live LLM.
- [ ] Provider errors, authentication failures, rate limits, and interruptions
  are reported separately from scored model divergences and cannot produce a
  successful run result for unexecuted cases.
- [ ] Tests with fail-on-call fakes prove that every external boundary except
  the selected LLM API remains unused.

### FR-5: Produce stage-local live metrics

The runner must score live observations with the TASK-020 structural scoring
contract and make the first divergent stage visible without grading exact model
reasoning or Yoda wording.

**Acceptance criteria:**
- [ ] Every attempted case reports `pass`, `fail`, `not_applicable`, or
  `blocked` for each declared stage, and a blocked downstream stage identifies
  the first upstream divergence.
- [ ] Aggregate output includes, for each canonical stage, passed, failed,
  applicable, and blocked case counts plus a derived pass rate with an explicit
  denominator.
- [ ] The report includes attempted, passed, failed, excluded, and incomplete
  case counts; excluded or operationally incomplete cases do not inflate stage
  accuracy.
- [ ] Structural differences identify case ID, turn ID, stage, and field path.
  Normal output does not require or expose raw model reasoning or exact
  user-facing prose.
- [ ] Selection scoring includes the selected skill and retained task
  constraints; planning includes modes, tools, and key arguments; execution
  includes typed outcome/job semantics; delivery includes allowed and
  prohibited claim boundaries.
- [ ] The scorer and metric aggregation remain deterministic pure logic over
  the captured live observations; only model acquisition is nondeterministic.

### FR-6: Persist a reproducible, privacy-safe run record

Each invocation must write a versioned JSON report artifact and print a concise
human-readable summary suitable for comparing runs without persisting prompt or
user-content replicas.

**Acceptance criteria:**
- [ ] The JSON artifact contains a report-schema version, unique run identity,
  UTC start/end timestamps, run completion status, corpus schema/version,
  selected case filter, and the configured model identity.
- [ ] The artifact contains the prompt IDs and canonical hashes actually used,
  exclusion reasons, per-case first divergence and structural diff paths,
  per-stage metrics, and any privacy-safe operational error categories.
- [ ] The default artifact and console summary contain no prompt bodies,
  synthetic user-message bodies, profile values, raw model responses,
  reasoning, tool inputs/results, credentials, or full decisions.
- [ ] Reports from separate invocations do not silently overwrite one another,
  and the console summary states the artifact location.
- [ ] Score failures still produce a completed report. If a provider or runner
  failure prevents completion, a partial report is written when possible and
  clearly distinguishes attempted, incomplete, and unattempted cases.
- [ ] JSON serialization is stable and covered by a round-trip test so a report
  can be consumed without importing live-run implementation classes.

### FR-7: Keep live evaluation opt-in and non-blocking

Live evaluation must remain an explicit diagnostic workflow, separate from the
deterministic test gate.

**Acceptance criteria:**
- [ ] The repository's standard `python -m pytest` run and normal CI do not call
  the live runner, require live-model credentials, or depend on a live report.
- [ ] No pull-request, merge, or release threshold is introduced for live stage
  metrics, and no mandatory or scheduled remote run is added.
- [ ] A live regression is visibly reported but does not alter corpus
  expectations, routing behavior, or user-visible outcomes to make the score
  pass.
- [ ] Developer documentation gives the exact invocation, required model
  credential/configuration, full-corpus and case-filter examples, report
  location, side-effect boundary, expected provider cost/rate-limit caveat, and
  metric interpretation.
- [ ] The existing deterministic corpus gate continues to run and score all
  cases, including malformed-output and recovery fixtures excluded from live
  scoring.

## Constraints & assumptions

- **Constraint:** EPIC-002 has `internal_compat: none`; this task does not need
  to support mixed intermediate implementations of sibling tasks on the shared
  branch.
- **Constraint:** The epic's `external_contract: additive` remains in force.
  Telemetry and evaluation must not change or migrate deployed conversation,
  profile, agent-session, scheduled-job, Redis, or ChromaDB data.
- **Constraint:** IODA boundaries apply: telemetry/evaluation DTOs are Data,
  hashing/formatting/scoring policy is Core logic, live-model and report I/O are
  Providers/APIs, and multi-stage live execution belongs in an Integration.
- **Constraint:** Runtime code may import TASK-020 contracts from
  `yoda.mind.evaluation`, but it must not import the test-only
  `tests.routing_evaluation` harness or recorded adapters.
- **Constraint:** ADR-000 applies to logs and artifacts. No real user-message
  replica may be added; user data stays DEBUG-only when logging is necessary.
- **Constraint:** The canonical stage vocabulary and scoring semantics remain
  aligned with TASK-020 so deterministic and live reports are comparable.
- **Assumption:** The live runner calls only the LLM; all other integrations use
  isolated state and corpus fixtures.
- **Assumption:** Live reports are retained as versioned JSON artifacts plus a
  concise console summary. Automated retention or upload is not required.
- **Assumption:** Recorded malformed-output/recovery cases are deterministic
  fault-injection tests and are excluded, with reasons, from default live
  scoring rather than weakening their expectations.
- **Assumption:** Exact command name, module/file layout, JSON field names,
  report directory, hash algorithm, and diagnostic serialization are design
  choices provided the observable contracts above hold.

## Out of scope

- Making live-model results pull-request blocking or defining accuracy,
  regression, release, or alert thresholds.
- Scheduling periodic live runs, uploading reports, building a dashboard, or
  adding alerting and long-term telemetry analytics.
- Calling real tools or production services other than the configured LLM
  during corpus evaluation.
- Persisting production user traces, prompt bodies, raw model responses, tool
  payloads, or user-visible replies in live-report artifacts.
- Changing TASK-020 corpus expectations, weakening deterministic recovery
  fixtures, or replacing recorded CI evaluation with live calls.
- Changing routing, skill, planning, execution, or delivery behavior to
  accommodate model variance; defects found by the runner belong to their
  owning task.
- Grading chain-of-thought, exact reasoning, exact Yoda wording, or using
  another model as a judge.
- Adding new user-facing skills, tools, model providers, schedulers, storage
  systems, or production-data migrations.
