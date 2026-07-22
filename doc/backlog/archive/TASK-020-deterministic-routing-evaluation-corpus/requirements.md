---
id: TASK-020
doc: requirements
updated: 2026-07-21
---

# TASK-020: deterministic routing evaluation corpus — Requirements

← [[backlog/archive/TASK-020-deterministic-routing-evaluation-corpus/task|Back to task]]

## Context

The routing pipeline now has separate contracts for intent classification, skill
selection, execution planning, tool or job outcomes, and grounded delivery.
Existing unit tests exercise many of those contracts independently, but their
cases are distributed across test modules and do not provide one versioned
regression corpus or a stage-by-stage score. A final reply can therefore appear
acceptable while an earlier decision selected the wrong capability, dropped a
request constraint, created the wrong job kind, or authorized a claim the
completed operation cannot support.

This task establishes a stable multilingual corpus and deterministic harness for
developers and CI. It evaluates structural decisions and semantic claim
boundaries instead of exact model reasoning or Yoda wording. The suite must make
the failed stage visible, cover multi-turn and recovery behavior, and preserve
the motivating July 20 scheduled-weather scenario as a named regression case.
Normal CI must use recorded or mocked model decisions and local test doubles;
live-model accuracy and production telemetry remain separate concerns.

## Functional requirements

### FR-1: Define a versioned routing corpus contract

The project must maintain a machine-readable, versioned corpus whose cases
describe the input conversation or interface event, deterministic model and
tool fixtures, and expected decisions at each applicable routing stage.

**Acceptance criteria:**
- [ ] The corpus exposes an explicit corpus/schema version and every case has a
  stable unique identifier, language tag, short purpose, and expected stages.
- [ ] A case can represent a single turn or an ordered multi-turn scenario,
  including recent visible conversation, clarification answers, suspended
  state, profile inputs, and fixed current time when relevant.
- [ ] Stage expectations can express intent, selected skill or no-skill,
  distilled-task constraints, execution mode, tool or job kind, key arguments,
  outcome category, and allowed or prohibited delivery claims.
- [ ] A stage that is intentionally bypassed by a scenario is explicitly marked
  not applicable rather than counted as a pass or silently omitted.
- [ ] Invalid corpus data fails fast before case execution with an error that
  identifies the case and invalid field; unknown fields or expectation values
  are not silently ignored.
- [ ] The corpus version used for a run appears in the result, and changes to
  the corpus contract or expected behavior require an intentional version
  update.

### FR-2: Provide multilingual contrastive coverage

The corpus must cover the routing behaviors assigned to this task with
contrastive English and Russian cases, including inputs whose surface keywords
are similar but whose requested outcomes differ.

**Acceptance criteria:**
- [ ] Every evaluated prompt family—intent classification, skill selection,
  execution planning, and grounded delivery—has representative English and
  Russian cases.
- [ ] Intent cases contrast conversational discussion with requests requiring
  an external capability or side effect, including current-information
  questions and short refinements that depend on recent visible conversation.
- [ ] Skill cases cover every currently discovered skill and include no-skill
  behavior without relying on catalog order.
- [ ] Scheduling cases contrast recurring static text, recurring fresh
  information, and a delayed reminder to check dynamic information; recurrence
  alone does not determine the expected skill or job kind.
- [ ] Cases cover immediate and deferred web search, picture creation, job
  management, user-data management, static message scheduling, and dynamic task
  scheduling at least once across the corpus.
- [ ] Adding a language or case does not require duplicating the harness logic
  or embedding language-specific assertions in test code.

### FR-3: Run deterministically in normal CI

The evaluation harness must execute the corpus without live models, network
services, production storage, wall-clock dependence, or nondeterministic
scheduler behavior.

**Acceptance criteria:**
- [ ] Normal CI consumes recorded raw structured responses or explicit mocks in
  a deterministic order and never calls a live LLM, Telegram, search, image,
  Redis, ChromaDB, or scheduler service.
- [ ] Recorded model responses pass through the production parsing, validation,
  Core policy, and Integration orchestration paths under evaluation; the
  harness does not inject the expected final state as the observed result.
- [ ] Time, identifiers, profile data, tool results, scheduler results, and
  error outcomes are fixed by fixtures whenever they affect an expectation.
- [ ] Running the same corpus version repeatedly against the same code produces
  the same case results and stage scores.
- [ ] The deterministic suite runs under the repository's standard
  `python -m pytest` command and returns a non-zero result when any required
  expectation fails.
- [ ] A failing case reports enough fixture and stage identity to reproduce it
  locally without exposing secrets or requiring external services.

### FR-4: Score and report each pipeline stage separately

The harness must compare observed structural behavior with the expectations for
each applicable stage and report failures at the stage where the contract first
diverges, while retaining later observations that were actually produced.

**Acceptance criteria:**
- [ ] Results distinguish at least intent routing, skill selection, execution
  planning, execution outcome, and delivery.
- [ ] Each case reports pass, fail, or not-applicable for every declared stage,
  with the expected and observed structural values for failures.
- [ ] Aggregate output includes per-stage passed, failed, and applicable case
  counts plus an overall case result; a correct final delivery cannot hide an
  earlier-stage failure.
- [ ] A skipped downstream stage caused by an upstream failure is identified as
  blocked by that stage and is not scored as an independent pass.
- [ ] Free-form reasoning and exact Yoda phrasing are excluded from scoring;
  only declared structural fields, retained constraints, outcome semantics, and
  claim boundaries are compared.
- [ ] The scorer and report model are deterministic pure logic over corpus
  expectations and captured observations, independently testable without
  invoking Providers, Portals, or APIs.

### FR-5: Verify planning, argument, and outcome contracts

The corpus must detect when the correct high-level route loses information or
produces the wrong operation during execution.

**Acceptance criteria:**
- [ ] Selection expectations can verify the selected skill, self-contained
  distilled-task meaning, and retention of explicit entities, language,
  timing, recurrence, addressee, output requirements, and strict or soft source
  constraints without requiring byte-for-byte task text.
- [ ] Planning expectations verify execution mode, ordered or batched tool
  names when order is semantically relevant, terminal behavior, and declared
  key arguments while allowing unrelated non-semantic formatting differences.
- [ ] Source-constrained search cases verify normalized
  `include_domains` propagation and fail if a strict domain is dropped or a
  no-results retry silently widens the search.
- [ ] Preference cases verify strict request constraints take precedence over
  soft request preferences, stored active-skill preferences, and defaults, and
  that one-off constraints are not treated as durable profile updates.
- [ ] Absolute or recurring schedule cases verify an explicit valid IANA
  timezone and the expected job kind; relative-delay cases do not require
  timezone clarification.
- [ ] Outcome expectations distinguish successful and failed execution,
  `message` and `task` jobs, immediate results, clarification, transient
  failure, and unsupported work from typed runtime evidence.

### FR-6: Cover multi-turn, suspension, and bounded recovery

The corpus and harness must represent stateful routing paths rather than testing
only isolated successful turns.

**Acceptance criteria:**
- [ ] Refinement cases verify that short follow-up turns remain agent tasks when
  recent visible conversation supplies the referenced operation or parameters.
- [ ] A clarification scenario verifies skill selection occurs before
  `ask_user`, execution suspends without a success claim, and the clarification
  answer resumes the same active workflow.
- [ ] Suspend/resume cases verify the distilled task, request constraints,
  accepted tool evidence, active skill, and retry budget needed by the expected
  continuation are preserved.
- [ ] Malformed or semantically invalid structured output cases cover intent,
  selection, and execution stages, including a successful bounded correction
  path and an exhausted path with the expected safe failure.
- [ ] Rejected output is not scored as an accepted decision, dispatched as a
  tool call, or treated as user-visible completion.
- [ ] Recovery failures are attributed to the stage that exhausted its budget;
  raw parser, schema, model, skill, tool, provider, or storage details are not
  accepted as delivery content.

### FR-7: Score grounded claims without exact prose

Delivery evaluation must determine whether the semantic claims authorized by a
structured outcome are truthful without grading stylistic wording.

**Acceptance criteria:**
- [ ] Success cases compare typed facts plus allowed and prohibited claim
  tokens before voice rendering rather than matching one final sentence.
- [ ] A static `message` job authorizes only scheduled stored-text delivery and
  prohibits live search, fetching, monitoring, calculation, future-result, or
  other recomputation claims.
- [ ] A dynamic `task` job may authorize a claim that the user-level operation
  will run later but prohibits claiming its future result or success before it
  runs.
- [ ] Immediate operations do not authorize an uncreated job, and failed
  operations do not authorize any unproved side effect.
- [ ] Ambiguous, transient, and unsupported outcomes carry only their permitted
  next-step semantics and prohibit internal implementation details or success
  claims.
- [ ] The harness includes negative tests proving that a prohibited claim or
  internal-detail marker fails delivery scoring even if other stages pass.

### FR-8: Preserve the July 20 regression scenario

The corpus must contain one stable, named, multi-stage fixture for the
motivating July 20 request to schedule a fresh recurring Saint Petersburg
weather result constrained to AccuWeather.

**Acceptance criteria:**
- [ ] The scenario expects intent `agent_task`.
- [ ] It expects selection of `search_web`, not `schedule_message`, and retains
  the recurring fresh-weather task, Saint Petersburg, response language, and
  strict AccuWeather constraint across the phase handoff.
- [ ] Clarification is permitted only after skill selection and only for
  genuinely missing execution data; data already supplied by the scenario or a
  valid profile is not requested again.
- [ ] The terminal scheduling call creates `kind=task` for the `search_web`
  operation and carries the scenario's schedule and valid IANA timezone.
- [ ] The persisted task constraints and eventual constrained search require
  `include_domains=["accuweather.com"]`; the fixture fails if execution widens
  the source silently.
- [ ] Creation delivery states only that the dynamic weather operation is
  scheduled and does not claim a forecast result already exists or that a
  static message job will perform a live search.
- [ ] The scenario is addressable by its stable case identifier and is included
  in the default deterministic CI run.

## Constraints & assumptions

- **Constraint:** EPIC-002 has `internal_compat: none`; the corpus does not need
  to model intermediate mixtures of sibling-task implementations on the shared
  branch.
- **Constraint:** The epic's `external_contract: additive` remains in force.
  Evaluation support must not change persisted agent-session, profile, or
  scheduled-job contracts or require migration of deployed data.
- **Constraint:** IODA boundaries apply to evaluation code: schema/result DTOs
  are Data, deterministic validation and scoring are Core logic, orchestration
  belongs in an Integration, and infrastructure adapters remain Providers,
  Portals, or APIs.
- **Constraint:** Recorded responses are regression fixtures for code and prompt
  contracts, not evidence of current live-model accuracy.
- **Constraint:** User messages, profile values, recorded model content, tool
  output, and outcome summaries are user data. Any logs or reports containing
  their full content remain DEBUG-only; normal results use case IDs, stages,
  categories, and non-sensitive structural diffs.
- **Constraint:** The deterministic corpus and harness must not introduce a
  network-capable test dependency into normal CI.
- **Assumption:** English and Russian are the required initial language set,
  based on the epic evaluation contract; the corpus contract must permit later
  languages without a harness rewrite.
- **Assumption:** Exact serialization format, file layout, version syntax,
  scorer class names, and human-readable report formatting are design choices
  provided the observable requirements above hold.
- **Assumption:** Existing focused unit tests remain useful. Corpus cases may
  reuse shared test builders, but the corpus is the canonical cross-stage case
  inventory rather than a copy of every low-level unit test.

## Out of scope

- Calling live models in normal CI or setting a live-model accuracy, release, or
  pull-request threshold.
- The on-demand live-model runner, prompt/model identity capture, production
  stage telemetry, dashboards, and alerting owned by
  [[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/task|TASK-021]].
- Grading exact model reasoning, chain-of-thought, final Yoda phrasing, or
  byte-for-byte distilled-task prose.
- Fixing unrelated routing behavior discovered by the corpus; defects outside
  this task's harness and fixture infrastructure are reported for the owning
  task rather than silently changing capability contracts.
- Adding new user-facing skills, tools, providers, schedulers, or storage
  systems.
- Migrating, cancelling, recreating, or repairing production jobs or sessions,
  including artifacts from the motivating July 20 test session.
