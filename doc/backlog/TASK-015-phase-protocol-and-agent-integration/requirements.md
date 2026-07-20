---
id: TASK-015
doc: requirements
updated: 2026-07-20
---

# TASK-015: phase protocol and Agent Integration — Requirements

← [[backlog/TASK-015-phase-protocol-and-agent-integration/task|Back to task]]

## Context

The agent currently uses one all-nullable `Decision` model for both skill
selection and workflow execution. That model permits contradictory combinations,
including selecting a skill while also asking a workflow-specific question, and
validation errors are converted into free-form answers instead of being repaired
as protocol failures. The orchestration that selects skills, advances phases,
executes tools, and persists suspended sessions also lives in `AgentProvider`,
although that coordination is Integration responsibility under IODA.

This task makes every transition explicit and stage-local. Skill selection must
finish before the selected workflow can clarify or call tools; selection and
execution must parse into different strict response contracts; and one malformed
response may receive one bounded corrective attempt. A bare-noun `Agent`
Integration becomes the orchestration boundary for direct requests, resumed
clarifications, and scheduled skill execution.

## Functional requirements

### FR-1: Define strict phase-specific response contracts

Skill selection and skill execution must use separate typed model responses whose
valid states are determined by the current phase. Cross-field and catalog/tool
membership checks must remain pure Core policy.

**Acceptance criteria:**
- [ ] The selection LLM call parses into a selection-only response model; that
  model contains no tool-call, clarification, execution-completion, or
  user-facing answer fields.
- [ ] A valid selection response represents exactly one of: an available skill
  with a non-empty self-contained distilled task, or a no-skill outcome.
- [ ] The execution LLM call parses into a different execution-only response
  model; that model contains no skill-selection or distilled-task fields.
- [ ] A valid execution response represents exactly one actionable mode:
  non-empty tool calls or completion according to the existing execution-result
  contract.
- [ ] Unknown or extra fields are rejected in both response models.
- [ ] Selection rejects unknown skill names, and execution rejects unavailable
  tool names and empty or mutually contradictory modes, without converting the
  rejected decision into a successful or user-facing answer.
- [ ] Unit tests exercise every valid mode and representative invalid
  cross-field, extra-field, unknown-skill, unknown-tool, and empty-output cases
  independently for selection and execution.

### FR-2: Select the skill before workflow clarification

The selection phase must choose the capability from the compact catalog contract
established by TASK-014 before the system gathers inputs specific to that
capability. Clarification belongs to execution under the selected workflow.

**Acceptance criteria:**
- [ ] A new agent task invokes selection without exposing `ask_user`,
  `update_profile`, skill-specific tool schemas, or any other executable tool to
  the selection response contract.
- [ ] Selection cannot emit or execute a clarification question or tool call.
- [ ] After a skill is selected, execution receives the selected full workflow
  and only its allowed skill tools plus shared infrastructure tools.
- [ ] Missing workflow inputs may be requested through `ask_user` only after
  the selected skill is active.
- [ ] A no-skill selection terminates without entering execution or calling a
  tool.
- [ ] Scheduled execution with an already specified skill enters execution
  directly and does not invoke the selector again.
- [ ] Deterministic tests cover direct selection-to-execution, no-skill,
  post-selection clarification and resume, and forced scheduled-skill execution.
- [ ] No test or runtime path permits the former pre-selection
  `ask_user`/`update_profile` loop.

### FR-3: Apply one bounded corrective retry

Each phase must give malformed model output one corrective opportunity using
concise validation feedback, then stop with a structured protocol failure if the
corrected response is still invalid.

**Acceptance criteria:**
- [ ] Structured-output parse failures, response-schema failures, phase
  cross-field failures, unknown skill names, and unavailable tool names all
  enter the corrective path for their current phase.
- [ ] The correction request is a `system` control message that identifies the
  violated phase contract without containing user-authored text, raw task
  content, tool output, stack traces, or provider details.
- [ ] Selection and execution each have one corrective-retry budget across the
  lifetime of that phase; the budget does not reset after a valid tool
  iteration or a suspend/resume cycle.
- [ ] At most one additional LLM request is made from that phase's retry budget
  for an invalid decision; a valid corrected response continues from the same
  phase.
- [ ] A second invalid response returns a structured failure identifying the
  failed stage as selection or execution and does not trigger another model
  correction.
- [ ] No skill activation or tool execution occurs from a rejected selection or
  execution response.
- [ ] Rejected output and raw validation details are not persisted as accepted
  assistant decisions and do not become chat-history answers.
- [ ] Deterministic tests cover first-attempt recovery and retry exhaustion in
  both selection and execution, including a parser/validation exception from the
  structured LLM boundary.

### FR-4: Establish `Agent` as the IODA orchestration boundary

A bare-noun `Agent` Integration must own phase transitions, skill activation,
tool dispatch coordination, suspend/resume flow, and terminal result assembly.
Pure policy and infrastructure access must remain in their respective
Operations.

**Acceptance criteria:**
- [ ] `Mind` delegates direct agent tasks, pending-session resumes, and scheduled
  skill runs to the `Agent` Integration through explicit async entry points.
- [ ] `Agent` coordinates `ReactLoop` Core policy with language, session, skill,
  and tool Operations; it contains no validation, routing, scheduling, or
  source-selection business rules.
- [ ] `ReactLoop` remains synchronous and static, depends only on Data, and owns
  phase transition and validation decisions without performing I/O.
- [ ] Providers remain narrow infrastructure adapters and do not call other
  Operations or Integrations; the orchestration-heavy `AgentProvider` no longer
  remains the architectural boundary.
- [ ] The Integration passes Data explicitly between Operations and uses
  `asyncio.gather()` when it dispatches two or more independent tool calls.
- [ ] The existing caller-visible behaviors for starting a task, running a
  known scheduled skill, checking a pending session, and resuming a
  clarification remain available after wiring changes.
- [ ] Architecture tests or focused unit tests demonstrate that phase and tool
  orchestration is exercised through `Agent`, while Core and Provider tests can
  run independently.

### FR-5: Preserve suspend/resume and deployed session compatibility

Phase changes and orchestration extraction must preserve valid suspended
execution workflows and remain additive for agent sessions already stored in
Redis when the epic is deployed.

**Acceptance criteria:**
- [ ] When execution successfully calls a suspending `ask_user`, the persisted
  session retains the selected skill, execution transcript, iteration/tool
  state, and all data required to resume the same workflow.
- [ ] A clarification answer is appended as untrusted `user` content and resumes
  execution without re-running skill selection.
- [ ] A legacy pre-selection session created before this task can still be
  loaded; after its existing clarification answer is supplied, the current
  selector chooses a skill before any further workflow-specific clarification
  or tool execution.
- [ ] A legacy suspended session with an already active skill can still be
  loaded and resumed in execution without requiring the historical combined
  `Decision` model to validate stored assistant messages.
- [ ] New session payloads round-trip all phase state needed by the split
  response protocol and bounded-retry policy.
- [ ] Existing user profiles, `skill_preferences`, scheduled jobs, and
  conversation history require no migration for this task.
- [ ] Compatibility tests load representative legacy pre-selection and active
  execution payloads from serialized data and complete their expected paths.

### FR-6: Return stage-safe protocol failures and diagnostics

Protocol exhaustion must terminate predictably and expose only structured,
capability-agnostic information to callers while retaining enough stage
information for diagnosis.

**Acceptance criteria:**
- [ ] Retry exhaustion returns a typed agent failure rather than strings such as
  “Invalid Phase 1”, an unknown skill/tool name, schema text, or an iteration
  limit message as a successful answer.
- [ ] The failure structure distinguishes selection from execution and can be
  mapped by the existing caller to a safe unsuccessful result without claiming
  that a tool or job completed.
- [ ] A terminal protocol failure removes or finalizes any affected pending
  session so the same invalid state is not resumed indefinitely.
- [ ] INFO/WARNING diagnostics contain the failed stage and a non-user-data
  failure category; model output, user content, profile data, and tool results
  remain DEBUG-only under project logging policy.
- [ ] Tests assert that raw parse, schema, model, provider, storage, file-path,
  and stack-trace details do not enter `AgentResult` user-facing text or
  conversation history.

## Constraints & assumptions

- **Constraint:** TASK-014 owns skill catalog metadata and control/user
  message-role separation. This task consumes that contract and must not
  duplicate full workflows or tool schemas into selection.
- **Constraint:** IODA rules apply: Integrations orchestrate; Cores are pure and
  synchronous; Providers adapt infrastructure; Operations do not depend on
  other Operations or Integrations.
- **Constraint:** The retry limit is deterministic and code-enforced. Prompt
  wording must not be the only mechanism preventing additional retries or
  phase-invalid actions.
- **Constraint:** The epic has `internal_compat: none`, so this task need not
  support intermediate deployment combinations with sibling-task code.
  `external_contract: additive` still requires upgrade safety for agent sessions
  already persisted before the merged epic is first deployed.
- **Constraint:** User-authored task and clarification text remains `user` data;
  phase instructions and generated validation feedback remain `system`
  control-plane content.
- **Assumption:** The exact response class names, Integration method signatures,
  Provider extraction, and serialized phase discriminator are design decisions.
- **Assumption:** This task may define a minimal typed protocol-failure result
  needed for safe termination. TASK-018 owns grounded success/failure outcomes,
  final delivery claims, and user-visible failure wording.
- **Assumption:** Deterministic tests are sufficient for this task. Multilingual
  live-model accuracy, corpus-wide stage scoring, and telemetry aggregation are
  owned by TASK-020 and TASK-021.

## Out of scope

- Adding or changing skill-selection metadata, catalog contrastive examples, or
  the static-message versus dynamic-task catalog boundary owned by TASK-014.
- Propagating skill preferences, enforcing request domains/sources, or changing
  profile-preference precedence owned by TASK-016.
- Timezone inference, IANA timezone guidance, and DST behavior owned by
  TASK-017.
- Grounded tool/job outcome models, final success claims, and user-visible safe
  failure rendering owned by TASK-018.
- Deterministic Telegram command routing owned by TASK-019.
- The multilingual evaluation corpus, live-model thresholds, stage telemetry,
  and live evaluation runner owned by TASK-020 and TASK-021.
- New skills, tools, scheduling capabilities, or storage backends.
