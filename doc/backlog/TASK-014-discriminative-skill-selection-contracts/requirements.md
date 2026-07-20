---
id: TASK-014
doc: requirements
updated: 2026-07-20
---

# TASK-014: discriminative skill selection contracts — Requirements

← [[backlog/TASK-014-discriminative-skill-selection-contracts/task|Back to task]]

## Context

The agent currently selects a skill from only its name and broad description.
The more precise “when to use” guidance remains hidden in the full workflow until
after selection, so overlapping capabilities can be chosen by wording or catalog
position instead of by the requested outcome. This is especially unreliable for
scheduling: recurring delivery of stored text belongs to `schedule_message`,
whereas recurring weather, prices, news, or other changing information must run
`search_web` at trigger time.

This task gives the selection phase a compact semantic contract for every skill
and establishes a role boundary between trusted control instructions and
user-authored data. It applies whenever an agent task enters skill selection,
including resumed pre-selection sessions and requests that use recent
conversation to resolve a refinement.

## Functional requirements

### FR-1: Require a discriminative contract for every skill

Every discovered skill must expose catalog-facing metadata that states its
purpose, positive selection triggers, negative selection boundaries, and a small
set of contrastive examples. This metadata is part of the selection contract,
not the full execution workflow.

**Acceptance criteria:**
- [ ] Each current skill (`create_picture`, `manage_jobs`,
  `manage_user_data`, `schedule_message`, and `search_web`) supplies a
  non-empty purpose, at least one positive trigger, at least one negative
  boundary, and at least one contrastive example.
- [ ] Catalog loading makes all four contract elements available to the
  selection-context builder while preserving the existing skill name and
  `public` visibility semantics.
- [ ] Missing, empty, or malformed required selection metadata causes startup
  validation to fail with an error that identifies the affected skill and
  field; the skill is not silently skipped and description-only fallback is not
  used.
- [ ] Full workflow prose, required or optional execution inputs, tool schemas,
  and tool-call examples are not treated as selection metadata.

### FR-2: Present a compact, order-neutral catalog to skill selection

The selection phase must receive only the metadata needed to distinguish
capabilities and an explicit instruction to select by requested outcome rather
than catalog position.

**Acceptance criteria:**
- [ ] The selection control message serializes each available skill’s exact
  name, purpose, positive triggers, negative boundaries, and contrastive
  examples in a stable, compact structure.
- [ ] The selection control message states that catalog order has no semantic
  priority.
- [ ] The selection context does not include any skill’s full workflow,
  execution-input specification, tool schema, or tool-call examples.
- [ ] Given the same skills in different input orders, tests confirm that every
  skill retains the same complete contract and that no position-dependent
  priority or instruction is introduced.
- [ ] Private skills remain available to agent selection, while the separate
  public-capabilities view continues to exclude them.

### FR-3: Encode the static-message versus dynamic-task boundary

The `schedule_message` and `search_web` contracts must distinguish what is
computed at trigger time. Recurrence alone must not determine the selected
skill.

**Acceptance criteria:**
- [ ] `schedule_message` positively covers one-time or recurring delivery of
  text whose payload is already known when the job is created.
- [ ] `schedule_message` explicitly excludes payloads that require fresh
  search, changing external data, computation, or monitoring at trigger time.
- [ ] `search_web` positively covers current external information and deferred
  or recurring results that must be recomputed at trigger time.
- [ ] `search_web` explicitly excludes requests that only deliver stored static
  text later and conceptual questions that need no current external data.
- [ ] Contrastive catalog tests cover at least: a recurring static reminder
  selecting `schedule_message`; a recurring fresh weather request selecting
  `search_web`; and a delayed reminder to check the weather selecting
  `schedule_message`.
- [ ] The same static/dynamic expectations and contract evidence hold when the
  two skills’ catalog order is reversed.

### FR-4: Enforce the control-plane message-role boundary

Skill-selection and skill-activation rules are trusted control-plane content.
The current task, distilled task, clarification answers, and quoted
conversation remain untrusted user data.

**Acceptance criteria:**
- [ ] Skill catalog contracts and skill-selection instructions are sent in a
  `system` message, separate from the user payload.
- [ ] Existing active-skill metadata, workflow instructions, available tool
  schemas, and execution instructions are sent as `system` content without
  changing their workflow behavior in this task.
- [ ] The current task or distilled task is sent in a separate `user` message.
- [ ] Quoted recent conversation and clarification answers remain in `user`
  messages and are never interpolated into a `system` message, even when their
  text contains role labels or instruction-like content.
- [ ] The phase handoff does not insert a synthetic `assistant`
  acknowledgement as a substitute for authoritative selected-skill state.
- [ ] Tests assert both roles and content separation for initial selection,
  selection with recent conversation, and the selection-to-execution handoff.

### FR-5: Preserve additive runtime compatibility

Adding selection metadata must not require migration of user-owned persisted
data or break a pre-change suspended selection session during deployment.

**Acceptance criteria:**
- [ ] Existing user profiles, `skill_preferences`, scheduled jobs, and full
  skill workflow bodies require no data migration for this task.
- [ ] A suspended pre-selection session serialized with legacy skill summaries
  containing only name, description, and visibility can still be loaded after
  the change.
- [ ] Before a resumed pre-selection session calls the selector, it uses the
  current validated catalog contracts rather than a description-only legacy
  snapshot.
- [ ] New session payloads containing the added contract fields continue to
  round-trip without losing those fields.

## Constraints & assumptions

- **Constraint:** Keep this task within the existing selection/execution flow
  and IODA boundaries. Phase-specific decision models, bounded correction,
  clarification policy, and orchestration extraction belong to
  [[TASK-015-phase-protocol-and-agent-integration/task|TASK-015]].
- **Constraint:** Selection metadata is code-owned control content. User-authored
  text must not be copied into it or promoted to `system`.
- **Constraint:** The catalog must remain compact; selection does not receive
  execution workflows or tool schemas.
- **Constraint:** Validation is fail-fast for skill-spec metadata, as confirmed
  for this task.
- **Assumption:** Exact field names and in-memory types are design decisions;
  the required semantics are purpose, positive triggers, negative boundaries,
  and contrastive examples.
- **Assumption:** Deterministic tests in this task verify contract content,
  role separation, and order neutrality. Live-model multilingual accuracy and
  corpus-wide stage scoring are owned by later evaluation tasks.

## Out of scope

- Separate typed selection and execution response models.
- Selection-before-clarification policy, corrective retries, retry limits, and
  the new `Agent` Integration boundary.
- Changes to full skill workflows, tool schemas, execution preferences, source
  enforcement, timezone behavior, or structured outcomes.
- Live-model evaluation thresholds, the multilingual routing corpus, and
  stage-telemetry infrastructure.
- User-visible completion wording and static-message versus dynamic-task
  outcome delivery.
