---
id: TASK-016
doc: requirements
updated: 2026-07-20
---

# TASK-016: execution preferences and domain constraints — Requirements

← [[backlog/archive/TASK-016-execution-preferences-and-domain-constraints/task|Back to task]]

## Context

Agent execution currently receives general profile fields but not stored
`skill_preferences`. Adding the whole preference map would expose unrelated
preferences to the active workflow, while omitting it prevents durable choices
such as preferred weather sources from influencing execution. At the same time,
source restrictions stated in the current request can be weakened or lost when
the selector distils the task or when a dynamic task is scheduled for later.

This task establishes a narrow execution-context contract for direct, resumed,
and scheduled skill runs. Only preferences for the active skill reach its
executor; one-off request constraints remain part of that task rather than
becoming profile data; and conflicting inputs resolve predictably from explicit
strict constraints down to skill defaults. For web search, existing persisted
preferences under the tool-name key `web_search` remain usable after deployment,
while all new writes converge on the canonical skill-name key `search_web`.
Strict source requests are enforced through the search provider's domain
restriction argument and are never silently relaxed.

## Functional requirements

### FR-1: Supply only active-skill preferences to execution

The execution phase must receive the stored preferences relevant to its active
skill without receiving preferences belonging to any other skill. Preferences
are execution data and must not alter the selected workflow or become
control-plane instructions.

**Acceptance criteria:**
- [ ] After a skill is activated, its execution context includes that skill's
  stored preference values together with the existing relevant profile context.
- [ ] Preferences stored for other skills are absent from the active execution
  prompt and are not available to that workflow through another injected field.
- [ ] Skill selection remains independent of stored skill preferences; the
  preferences are introduced only after the skill has been selected or when a
  known scheduled skill enters execution directly.
- [ ] Direct execution, resumed execution, and `run_with_skill` scheduled
  execution apply the same active-skill preference filtering.
- [ ] An empty or missing active-skill preference set is represented
  unambiguously and execution continues with request inputs and skill defaults.
- [ ] Preference text is delimited and identified as profile data so it cannot
  replace the active workflow, tool schemas, or executor rules.
- [ ] Deterministic tests use a profile containing preferences for at least two
  skills and assert that only the active skill's values enter execution.

### FR-2: Apply request and stored inputs with fixed precedence

Execution must distinguish current-request constraints from durable profile
preferences and resolve conflicts in this order: explicit strict request
constraint, explicit soft request preference, stored active-skill preference,
then skill default.

**Acceptance criteria:**
- [ ] An explicit strict request constraint overrides every conflicting soft
  request preference, stored preference, and skill default.
- [ ] When no strict constraint applies, an explicit soft request preference
  overrides a conflicting stored active-skill preference and skill default.
- [ ] A stored active-skill preference is used when the current request leaves
  that choice unspecified, and the skill default is used only when neither the
  request nor the stored active-skill preferences specify it.
- [ ] A current one-off source choice or restriction affects the current task
  but is not written to `skill_preferences` unless the user explicitly states
  that it is a lasting preference.
- [ ] A later profile change may supply a default omitted by an already
  scheduled task, but it cannot replace or weaken an explicit constraint stored
  in that task.
- [ ] Deterministic tests cover each precedence tier and conflicts between the
  current request and the stored profile.

### FR-3: Preserve explicit constraints through task distillation

Every self-contained execution brief must retain the current request's explicit
strict and soft constraints and enough context to apply them at execution time,
including when dynamic work is deferred or recurring.

**Acceptance criteria:**
- [ ] The selection phase preserves explicit source/domain constraints, whether
  strict or soft, in the distilled task passed to the selected workflow.
- [ ] When `search_web` schedules dynamic work, the `schedule_task`
  `distilled_task` preserves the requested topic, location or other relevant
  entities, response language, output requirements, notification condition, and
  explicit strict/soft source constraints that were agreed when the job was
  created.
- [ ] The persisted scheduled-job payload is self-contained and does not depend
  on references such as “that site,” “as above,” or an unavailable chat turn to
  recover an explicit constraint.
- [ ] At trigger time, `run_with_skill` receives the persisted distilled task
  unchanged and applies its explicit constraints ahead of then-current stored
  preferences.
- [ ] Tests cover an immediate constrained search and a scheduled recurring
  search whose explicit source constraint survives selection, job persistence,
  job loading, and forced skill execution.

### FR-4: Converge web-search preferences on the canonical skill key

All new web-search preference writes must use the skill-name key `search_web`.
Existing preferences persisted under the legacy tool-name key `web_search` must
remain readable and contribute additively to `search_web` execution.

**Acceptance criteria:**
- [ ] Conversation summarization emits newly learned durable web-search
  preferences under `skill_preferences_to_add.search_web`, never under
  `skill_preferences_to_add.web_search`.
- [ ] Agent-initiated profile updates for durable web-search preferences write
  `skill_preferences.search_web` or the corresponding canonical additive update,
  never a new `web_search` key.
- [ ] For an active `search_web` skill, preferences already stored under
  `search_web` and under legacy `web_search` are both included in the effective
  active-skill preference set.
- [ ] Reading legacy values does not copy, delete, rename, or otherwise mutate
  the persisted profile as a side effect.
- [ ] Duplicate preference strings present under both keys do not produce
  duplicate effective preference entries.
- [ ] Other skill keys are neither aliased nor changed by this compatibility
  behavior.
- [ ] Compatibility tests load representative pre-epic Redis profile data with
  only `web_search`, only `search_web`, and both keys and verify effective reads
  plus canonical-only subsequent writes.

### FR-5: Enforce strict web-source domains without widening

A request that limits web results to one or more domains must be enforced
end-to-end with `include_domains`. Prompt wording, a domain name embedded in the
query, or a `site:` query operator is not sufficient enforcement.

**Acceptance criteria:**
- [ ] The `web_search` tool schema accepts a non-empty list of normalized domain
  host names as `include_domains`, and the API adapter passes that list unchanged
  to the external search provider.
- [ ] URL-like user input used as a strict source is normalized to the provider's
  accepted host form without broadening it to a parent domain or unrelated
  domain.
- [ ] Before a strict-source search is dispatched, the validated tool call
  contains every allowed domain in `include_domains`; a missing or conflicting
  restriction is rejected or corrected without performing an unrestricted
  search.
- [ ] Every refinement or retry for the same strict-source task retains an equal
  or narrower `include_domains` restriction.
- [ ] If the restricted search returns no usable result, execution reports the
  source limitation or asks whether another source is allowed and does not retry
  with an empty, omitted, or widened domain list.
- [ ] Soft source preferences may fall back only when no strict request
  constraint prohibits widening.
- [ ] Deterministic tool and agent tests verify provider argument propagation,
  normalization, rejection before unrestricted dispatch, restriction retention
  across refinements, and the no-results path.

## Constraints & assumptions

- **Constraint:** IODA boundaries remain in force. Pure preference selection,
  key aliasing, domain normalization, and constraint-validation policy belong in
  Core; `Agent` orchestrates Data between Operations; Providers and API façades
  only adapt storage, LLM, and search infrastructure.
- **Constraint:** User-authored tasks and preference values remain untrusted
  data. They must not be interpolated as executable control instructions even
  when rendered in a `system` execution-context block.
- **Constraint:** EPIC-002 has `internal_compat: none`, so this task does not
  need to support intermediate combinations of sibling-task code on the shared
  branch.
- **Constraint:** The epic's `external_contract: additive` requires existing
  Redis `UserProfile.skill_preferences`, scheduled jobs, and agent sessions to
  work on first deployment without a bulk migration.
- **Constraint:** Existing legacy `web_search` keys remain persisted; this task
  adds read compatibility but does not remove or rewrite them.
- **Constraint:** Full message, profile, constraint, and search-result content
  is logged only at DEBUG under the project logging policy.
- **Assumption:** A strict source constraint explicitly limits acceptable
  results to named sources (for example, “only from example.com”); a soft source
  preference requests or prefers a source while permitting fallback.
- **Assumption:** The concrete Data types and method signatures used to carry
  effective preferences and request constraints are design decisions, provided
  the observable scoping, precedence, persistence, and enforcement criteria
  above hold.

## Out of scope

- Timezone inference, IANA timezone persistence, and DST behavior owned by
  TASK-017.
- Grounded outcome DTOs, final success claims, safe-failure wording, and general
  user-visible rendering owned by TASK-018.
- Removing, renaming in place, or bulk-migrating legacy persisted `web_search`
  preference keys.
- Changing skill selection metadata or the static-message versus dynamic-task
  routing boundary owned by TASK-014.
- Changing the phase protocol, corrective-retry budget, or `Agent` Integration
  boundary established by TASK-015.
- Adding new search providers, source-ranking algorithms, web-search skills, or
  profile-management user interfaces.
