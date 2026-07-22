---
id: TASK-017
doc: requirements
updated: 2026-07-20
---

# TASK-017: IANA timezone execution guidance — Requirements

← [[backlog/TASK-017-iana-timezone-execution-guidance/task|Back to task]]

## Context

Absolute and recurring schedules are defined in a user's local civil time, but a
current clock reading or UTC offset does not identify the timezone rules that
must apply when daylight-saving transitions occur. The execution workflows
currently ask for a timezone whenever one is absent and the scheduling Core can
fall back to UTC, even when profile location data could resolve an IANA timezone
without another user turn.

This task makes IANA timezone identity the execution contract for both static
scheduled messages and deferred or recurring `search_web` tasks. Execution
reuses a valid profile timezone, infers and persists one when a named location
is unambiguous, and asks one direct question only when the available location
remains ambiguous. Existing `ZoneInfo` and `CronTrigger` scheduling mechanics
remain the implementation foundation and gain deterministic coverage across
DST transitions.

## Functional requirements

### FR-1: Resolve timezone identity during skill execution

The active `schedule_message` and `search_web` workflows must resolve an IANA
timezone before dispatching an absolute or recurring local-time schedule.
Timezone resolution is execution behavior after skill selection; relative-delay
schedules do not require it.

**Acceptance criteria:**
- [ ] An absolute or recurring schedule reuses a non-empty profile timezone only
  when that name is accepted by `ZoneInfo`.
- [ ] A valid IANA timezone explicitly supplied in the current request is used
  without asking for the user's current clock or an additional location.
- [ ] When no valid timezone is available and the task or profile contains an
  unambiguous named location, execution infers an IANA name and supplies that
  explicit name to `schedule_message` or `schedule_task` without clarification.
- [ ] An invalid profile timezone is treated as unresolved rather than reused or
  silently treated as UTC for an absolute or recurring local-time schedule.
- [ ] Relative-delay scheduling continues without requiring timezone or
  location clarification.
- [ ] The timezone-resolution rules appear in the full execution workflows for
  both `schedule_message` and deferred/recurring `search_web`; they are not
  added to the compact skill-selection contract.
- [ ] Deterministic workflow/agent tests cover a valid profile timezone, an
  explicit valid IANA name, an unambiguous named location, and a relative delay
  for both applicable scheduling paths.

### FR-2: Clarify only unresolved timezone ambiguity

Execution must ask directly for a city/region or IANA timezone only when the
available request and profile data cannot identify one timezone. A clock reading
or numeric UTC offset alone must never be accepted as timezone identity.

**Acceptance criteria:**
- [ ] An ambiguous location causes one concise clarification asking for the
  disambiguating city/region information or an IANA timezone name before an
  absolute or recurring schedule is dispatched.
- [ ] Missing location and timezone data causes the same direct clarification;
  the system does not ask the user to report their current local clock.
- [ ] A bare offset such as `+03:00` or `UTC+03:00` is rejected as timezone
  identity and does not result in a schedule being created under that value or
  under a silent UTC fallback.
- [ ] The system does not ask a timezone question when a valid profile IANA
  timezone, an explicit valid IANA timezone, or an unambiguous named location
  already resolves the schedule.
- [ ] Clarification uses the post-selection `ask_user` execution path and resumes
  the same active workflow rather than invoking skill selection again.
- [ ] Deterministic tests contrast an unambiguous location with an ambiguous
  location and an offset-only answer, asserting whether scheduling or
  clarification occurs and that no schedule is dispatched while identity
  remains unresolved.

### FR-3: Persist an inferred timezone and location

When execution infers timezone identity from a named location, it must save the
resolved IANA timezone and the location used to resolve it so later schedules
can reuse that identity.

**Acceptance criteria:**
- [ ] Inference from an unambiguous named location invokes `update_profile` with
  both the resolved IANA timezone and the corresponding location.
- [ ] The scheduling call receives the resolved timezone explicitly and does not
  depend on rereading the profile update.
- [ ] `update_profile` and the scheduling call may be batched only when every
  scheduling argument is already resolved and the scheduling call has no
  dependency on completion of the profile write.
- [ ] A subsequent execution using the updated profile reuses the persisted
  timezone without asking the user again.
- [ ] Profile persistence uses the existing `timezone` and `location` fields and
  introduces no new profile schema or location-to-timezone storage model.
- [ ] Deterministic tests verify the profile-update arguments, explicit
  scheduling timezone, and subsequent reuse for at least one static message and
  one deferred `search_web` task.

### FR-4: Preserve IANA and DST scheduling semantics

Scheduling must continue to use `ZoneInfo` for absolute conversion and
`CronTrigger` for recurring schedules, preserving local wall-clock intent when
a regional timezone changes UTC offset.

**Acceptance criteria:**
- [ ] Valid regional IANA names are accepted by absolute and recurring
  scheduling, passed unchanged to the scheduler, and retained in persisted job
  metadata.
- [ ] Invalid and offset-only timezone strings for absolute or recurring local
  schedules fail before a job is registered or its metadata is persisted; they
  are not coerced to UTC.
- [ ] Deterministic absolute-time tests use well-defined local times on both
  sides of a DST transition and assert the expected UTC instants and offsets.
- [ ] Deterministic recurring tests assert that a fixed local cron time remains
  at the requested local wall-clock time across both spring and autumn
  transitions while its UTC offset changes according to the named zone.
- [ ] DST tests avoid nonexistent or duplicated transition-hour wall times; this
  task does not define a new policy for those edge cases.
- [ ] Existing valid persisted profiles and scheduled-job payloads remain
  readable without migration, and existing valid jobs retain their stored IANA
  timezone behavior after deployment.

## Constraints & assumptions

- **Constraint:** This is a prompt-first change. It may tighten deterministic
  timezone validation and add tests, but it must not add a geocoding service,
  location-to-timezone resolver, or mapping Provider.
- **Constraint:** IODA boundaries remain in force. Execution workflow guidance
  belongs to skill specifications; pure timezone validation/conversion belongs
  in Core; scheduler and profile side effects remain in their existing API and
  Provider/tool adapters; `Agent` only orchestrates Operations.
- **Constraint:** User location and timezone values remain untrusted execution
  data and are logged only at DEBUG under project logging policy.
- **Constraint:** EPIC-002 has `internal_compat: none`, so this task does not
  need to support intermediate combinations of sibling-task implementations on
  the shared branch.
- **Constraint:** The epic's `external_contract: additive` requires existing
  valid Redis profile and scheduled-job data to work on first deployment
  without a bulk migration.
- **Assumption:** `UTC` is a valid named timezone for users who explicitly use
  UTC; textual or numeric offsets that do not resolve through `ZoneInfo` are not
  timezone identities.
- **Assumption:** Prompt/model accuracy over a broad multilingual location
  corpus is evaluated by TASK-020. This task uses deterministic workflow,
  mocked-decision, Core, and scheduler tests for the specified cases.
- **Assumption:** Handling nonexistent or duplicated local times inside the DST
  transition hour is a separate policy decision; transition coverage here uses
  unambiguous wall times and protects established library behavior.

## Out of scope

- A new geocoding API, timezone lookup database, location resolver, or Provider.
- A general profile-preference precedence model or web-source enforcement,
  which belongs to TASK-016.
- Changes to skill selection, phase response contracts, or suspend/resume
  orchestration established by TASK-014 and TASK-015.
- Grounded outcome DTOs, success claims, and user-visible safe-failure rendering
  owned by TASK-018.
- A policy for nonexistent or duplicated local wall times during the DST
  transition hour.
- Bulk migration or cancellation of existing profiles or scheduled jobs.
- Corpus-wide multilingual and live-model timezone evaluation owned by
  TASK-020 and TASK-021.
