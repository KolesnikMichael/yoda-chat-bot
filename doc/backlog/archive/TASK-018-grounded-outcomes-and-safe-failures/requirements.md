---
id: TASK-018
doc: requirements
updated: 2026-07-21
---

# TASK-018: grounded outcomes and safe failures — Requirements

← [[backlog/archive/TASK-018-grounded-outcomes-and-safe-failures/task|Back to task]]

## Context

Agent execution currently returns free-form answer text plus a list of tool names.
`Mind` then asks the companion model to describe that text as a completed task.
This loses the distinction between what was requested, what actually succeeded,
and whether scheduling created a static message job or a dynamic task job. A
plausible answer can therefore strengthen a tool result into a claim the created
job cannot satisfy, such as saying that a stored reminder will fetch fresh
weather when it fires.

Failures have a similar trust-boundary problem. Although phase failures are
typed inside the agent, delivery currently collapses them into one generic
instruction, while tool outputs and exceptions may contain schema, tool,
provider, storage, file-path, or other implementation details. Direct,
resumed, and scheduled execution all need one structured source of truth from
which user-visible success, clarification, and failure messages can be derived.

This task establishes that source of truth and a deterministic delivery policy.
Tone may still be rendered in Yoda's voice and in the user's language, but the
renderer may communicate only facts and next steps authorized by the structured
outcome. Static scheduled messages remain stored-text delivery; dynamic task
jobs are the only scheduled jobs that may promise to recompute content when
triggered.

## Functional requirements

### FR-1: Produce a structured execution outcome

Every completed direct, resumed, or scheduled agent run must return one
structured outcome that identifies the user-level operation, whether it
succeeded or failed, a grounded summary, and the kind of result that actually
occurred. Scheduling outcomes must distinguish a static `message` job from a
dynamic `task` job without inferring that distinction from display text.

**Acceptance criteria:**
- [ ] A completed run exposes exactly one success or failure outcome; it cannot
  simultaneously expose a successful answer and a failure.
- [ ] The outcome contains a capability-neutral operation, status, grounded
  summary, and an actual result kind; when a job is created, its job kind is
  exactly `message` or `task`, and otherwise the job kind is absent.
- [ ] A failure outcome contains a safe failure category and next-step
  disposition rather than user-facing phase, protocol, model, schema, skill,
  tool, provider, storage, or exception details.
- [ ] Clarification remains a distinct non-completion result carrying the
  question to ask; it does not report success, failure, or a created job.
- [ ] `run`, `resume`, and `run_with_skill` return the same outcome contract for
  equivalent terminal execution paths.
- [ ] The structured outcome is Data with only consistency-level validation;
  operation/result derivation and failure classification do not live in the
  Data object.

### FR-2: Derive success from completed execution

A success outcome must be grounded in successful tool results and the operation
that actually completed. Model-authored finish text may summarize evidence but
must not convert a failed, missing, or different operation into success.

**Acceptance criteria:**
- [ ] A successful terminal tool produces the final success outcome from its
  typed result, including the actual operation and result/job kind supplied by
  code rather than by parsing its human-readable output.
- [ ] `schedule_message` success identifies a created `message` job, while
  `schedule_task` success identifies a created `task` job.
- [ ] Other terminal side effects, including successful picture delivery, carry
  their actual user-level result kind and do not claim a scheduled job.
- [ ] A failed terminal tool, a tool exception, or a missing terminal success
  cannot produce a success outcome or a statement that its side effect occurred.
- [ ] A non-terminal finish after operations such as web search is grounded only
  in the task and successful tool results present in that execution; failed tool
  output is not presented as a successful fact.
- [ ] If execution reaches a terminal state without evidence for the claimed
  operation, it returns a safe failure rather than a generic “completed” answer.
- [ ] Deterministic tests contrast successful and failed terminal tools and
  assert the resulting operation, status, and job/result kind.

### FR-3: Constrain success delivery to allowed claims

User-visible success delivery must be built from the structured outcome through
a deterministic claim policy. A language model may vary tone and phrasing but
may not add facts, strengthen certainty, change the result kind, or claim an
operation not authorized by that policy.

**Acceptance criteria:**
- [ ] Delivery receives a structured, authoritative success payload containing
  the operation, grounded summary, job kind, user-relevant schedule when
  applicable, and mechanically derived allowed claims.
- [ ] For `job_kind=message`, allowed claims state only that stored text will be
  delivered on the schedule; they prohibit claims that the job will search,
  fetch, monitor, calculate, or otherwise recompute live content.
- [ ] For `job_kind=task`, allowed claims may state that the named user-level
  action will run at trigger time, but may not claim its future result or success
  before that execution occurs.
- [ ] When no job was created, delivery does not describe the result as
  scheduled or assign it a message/task job kind.
- [ ] Success delivery does not expose internal skill or tool names merely
  because they were used to derive the outcome.
- [ ] Rendering preserves the supplied user-relevant language and summary
  meaning while allowing normal voice variation.

### FR-4: Preserve the static-message boundary at trigger time

Scheduled delivery must continue to distinguish stored reminders from dynamic
task execution after the job fires, not only when the job is created.

**Acceptance criteria:**
- [ ] Triggering an existing `kind=message` job delivers its stored reminder
  text under an instruction that forbids adding current facts, search results,
  or claims that an external lookup occurred.
- [ ] Triggering a `kind=task` job executes its persisted skill task and renders
  the outcome of that new execution; job creation text is not reused as evidence
  that the dynamic operation later succeeded.
- [ ] A failed scheduled task is delivered through the same safe failure policy
  as a failed direct run and does not expose scheduler, skill, model, tool, or
  provider details.
- [ ] Tests cover both one-shot and recurring message/task jobs and assert that
  recurrence does not change the static-versus-dynamic claim boundary.

### FR-5: Map failures to safe, useful next steps

Every user-visible failure must be reduced to the narrowest applicable
capability-agnostic category: ambiguous input, transient failure, or unsupported
work. The category determines the useful next step without exposing why the
implementation failed internally.

**Acceptance criteria:**
- [ ] Ambiguous or insufficient user input yields a supplied clarification when
  the workflow can suspend, or otherwise asks the user to clarify or rephrase;
  it does not imply that work completed.
- [ ] External/runtime failures and exhausted internal format or protocol
  recovery yield a transient failure that suggests trying again later, unless
  the evidence instead establishes ambiguity or an unsupported capability.
- [ ] A no-skill result or an active workflow's capability-boundary rejection
  yields an unsupported failure that states only the user-level boundary and
  does not suggest that an unavailable internal component merely crashed.
- [ ] Failure delivery never includes skill names, tool names, model or prompt
  details, phase or schema terminology, validation text, provider or storage
  details, file paths, exceptions, or stack traces.
- [ ] Failure delivery never implies success, a created job, a sent artifact, a
  completed lookup, or any other side effect not established by a successful
  outcome.
- [ ] The safe summary and next step remain brief and in the user's language;
  voice rendering may rephrase them but cannot change their category or meaning.
- [ ] Deterministic tests cover all three categories, including no-skill,
  terminal tool exception, protocol exhaustion, and an ambiguous-input path.

### FR-6: Make claim policy independently testable

Correctness of completion and failure claims must be testable without scoring
Yoda voice or requiring exact free-form response wording.

**Acceptance criteria:**
- [ ] Pure Core policy transforms a structured outcome or clarification into a
  delivery payload with explicit facts, allowed claims, prohibited boundaries,
  and the permitted next step before any voice rendering occurs.
- [ ] Unit tests assert semantic payload fields and claim boundaries rather than
  matching one exact final sentence.
- [ ] Integration tests inspect the authoritative conversation instruction
  given to the renderer and verify that raw `AgentFailure`, `ProtocolIssue`,
  `ToolResult`, and exception content does not enter user-visible history.
- [ ] Representative static-message, dynamic-task, immediate-tool,
  clarification, transient, and unsupported cases are covered deterministically.
- [ ] Tests explicitly fail when a static message payload authorizes a live-task
  claim or when any failure payload contains an implementation-detail marker.

### FR-7: Preserve deployed sessions and scheduled jobs

The new outcome and delivery contracts must remain additive for agent sessions
and scheduled jobs already persisted when EPIC-002 is deployed.

**Acceptance criteria:**
- [ ] Suspended sessions written by the previously deployed phase protocol can
  be loaded and resumed after this change without a bulk migration.
- [ ] Any lazy session upgrade refreshes generated outcome/control schema
  messages while preserving the active skill, task, clarification answers,
  accepted tool history, request constraints, retry state, and user-authored
  content needed to finish safely.
- [ ] New suspended sessions round-trip every field needed to construct the
  structured outcome after resume.
- [ ] Existing scheduled-job records with `kind=message` or `kind=task` remain
  readable and execute through the correct static or dynamic delivery path
  without rewriting stored records.
- [ ] Existing conversation history and already delivered task-result messages
  require no migration or retrospective rerendering.
- [ ] Compatibility tests load representative pre-change active sessions and
  message/task job metadata, then complete or deliver them under the new claim
  policy.

## Constraints & assumptions

- **Constraint:** IODA boundaries remain in force. Outcome and delivery DTOs are
  Data; deterministic classification and claim derivation belong in Core;
  `Agent` and `Mind` Integrations pass Data between Operations; Providers,
  Portals, and API façades retain their infrastructure or interface roles.
- **Constraint:** User-authored text, tool output, and outcome summaries remain
  untrusted data. Delivery policy and rendering constraints use authoritative
  control-plane messages and never promote user text into instructions.
- **Constraint:** EPIC-002 has `internal_compat: none`, so this task does not
  need to support intermediate combinations of sibling-task implementations on
  the shared branch.
- **Constraint:** The epic's `external_contract: additive` requires existing
  Redis agent sessions, active job metadata, user profiles, and conversation
  history to work on first deployment without a bulk migration.
- **Constraint:** INFO/WARNING logs may contain stage and safe failure category
  but no user text, profile values, tool output, or outcome summary; content with
  user data remains DEBUG-only.
- **Constraint:** Factual claim boundaries are enforced in code and typed
  contracts. Prompt wording alone is not sufficient to distinguish message
  versus task jobs or to establish that an operation succeeded.
- **Assumption:** Exact class names, field names, operation vocabulary, and
  serialized protocol-version increment are design decisions provided the
  observable outcome, compatibility, and delivery criteria above hold.
- **Assumption:** A clarification is a suspended, non-terminal interaction, not
  a fourth failure category. If suspension is no longer possible, unclear input
  is represented by the `ambiguous` safe-failure category.
- **Assumption:** Tool/result kinds are internal structured evidence. Delivery
  exposes only the corresponding user-level operation and job semantics, not
  implementation names.

## Out of scope

- Skill-selection metadata and static-versus-dynamic routing decisions owned by
  TASK-014.
- Phase orchestration, retry budgets, and the `Agent` Integration boundary owned
  by TASK-015, except for consuming their terminal results safely.
- Preference propagation, source-domain enforcement, task distillation, and
  legacy preference-key handling owned by TASK-016.
- Timezone inference, IANA persistence, and DST scheduling semantics owned by
  TASK-017.
- Corpus-wide multilingual evaluation, live-model scoring, stage telemetry, and
  live evaluation runners owned by TASK-020 and TASK-021.
- Defining exact free-form Yoda wording or requiring byte-for-byte renderer
  output.
- Adding new user capabilities, tools, schedulers, search providers, or storage
  systems.
- Bulk migration, cancellation, recreation, or operational repair of existing
  scheduled jobs, including jobs from the motivating July 20 test session.
