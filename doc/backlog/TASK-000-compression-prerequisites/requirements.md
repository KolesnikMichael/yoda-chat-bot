---
id: TASK-000
doc: requirements
updated: 2026-06-09
---

# TASK-000: compression prerequisites — Requirements

← [[backlog/TASK-000-compression-prerequisites/task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) assumes two data-shape widenings before compression apply and profile extraction land in later tasks. Neither change depends on `Message.kind`, migration, or the compression pipeline itself — they are small, additive schema/content extensions that unblock [[TASK-002-user-introduction-on-ingest/task|TASK-002]] (which snapshots `UserProfile`, including skill preferences, into `user_introduction`) and [[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]] (which mechanically parses skill names from `task_result` content and applies profile deltas).

Today, `Mind._handle_agent_result` writes agent outcomes without naming which skills/tools ran, even though `AgentResult.tools_used` is already populated. `UserProfile` has no place for per-skill preference strings, and `MemoryProvider.update_user_profile` only supports replace-style updates — insufficient for compression-time append-only deltas described in [[chat_context_management#Profile extraction details]].

This task delivers the prerequisites only: widen content and profile storage contracts. It does **not** wire summarisation, mechanical extraction, or compression.

## Functional requirements

### FR-1: Skill names in agent `task_result` content

When the agent completes a delegated task with a final answer, the system message written by `Mind._handle_agent_result` must include a machine-parseable list of skill/tool names in its **content** string, so downstream code (TASK-005) can derive a `skills` set from the substring `Tools used: …`.

**Acceptance criteria:**
- [ ] When `_handle_agent_result` handles an `AgentResult` with a non-empty `answer`, the stored conversation line contains a substring of the form `Tools used: <name>` for a single tool, or `Tools used: <name>, <name>, …` for multiple tools, using the names from `result.tools_used` in order.
- [ ] When `result.tools_used` is empty, the line contains `Tools used: none` (literal word `none`, not an empty list after the colon).
- [ ] The existing result text (`Result: …`, instruction to communicate naturally, trailing current-time stamp) remains present; only the tools clause is added.
- [ ] The clarification branch (`result.clarification`) is unchanged — no `Tools used:` clause is added there.
- [ ] `Mind.deliver_scheduled_reminder` and `Mind.notify_scheduled_failure` keep their current content format (no `Tools used:` substring).

### FR-2: `UserProfile.skill_preferences` field

`UserProfile` gains a dict-of-list field for per-skill preference strings, defaulting empty for new and legacy profiles.

**Acceptance criteria:**
- [ ] `UserProfile` declares `skill_preferences: dict[str, list[str]]` with `field(default_factory=dict)`.
- [ ] A profile loaded from Redis that predates the field deserialises with `skill_preferences == {}` (no migration bump required beyond the dataclass default).
- [ ] `UserProfile.to_dict()` serialises `skill_preferences` so a round-trip through `MemoryProvider.get_user_profile` / `update_user_profile` preserves values.

### FR-3: Append-only delta keys in `MemoryProvider.update_user_profile`

`MemoryProvider.update_user_profile` must recognise compression-time delta keys and merge them into the live profile without replacing entire list or dict fields. Replace-style keys used by the agent tool continue to work unchanged.

**Acceptance criteria:**
- [ ] `interests_to_add: list[str]` — each item is appended to `current.interests` with **case-insensitive deduplication** against items already in the list; existing items are not removed or reordered except by append.
- [ ] `facts_to_add: list[str]` — same append-with-case-insensitive-dedup semantics on `current.facts`.
- [ ] `skill_preferences_to_add: dict[str, list[str]]` — for each `(skill_name, items)` pair, each item is appended to `current.skill_preferences.setdefault(skill_name, [])` with case-insensitive deduplication within that skill's list; unknown skill names create a new bucket; skill keys are never deleted by a delta update.
- [ ] Delta keys (`interests_to_add`, `facts_to_add`, `skill_preferences_to_add`) are **not** persisted as top-level profile fields — they are consumed by the merge logic only.
- [ ] Replace-style keys (`interests`, `facts`, `skill_preferences`, and existing scalar fields) still overwrite via `setattr` as today; a call may mix replace keys and delta keys in one update, with each key handled by its respective rule.
- [ ] `updated_on` is refreshed on every successful update, including delta-only updates.

### FR-4: `update_profile` agent tool allows `skill_preferences`

The agent-facing replace path must be able to write the new field when the user explicitly asks to change stored preferences (compression will use delta keys instead).

**Acceptance criteria:**
- [ ] `"skill_preferences"` is added to `ALLOWED_FIELDS` in `update_profile_tool.py`.
- [ ] A tool call with `fields: {"skill_preferences": {<skill>: [<items>]}}` succeeds and persists via `MemoryProvider.update_user_profile` (replace semantics on the whole dict).
- [ ] Unknown field names are still rejected with the existing error behaviour.

## Constraints & assumptions

- **Constraint:** Changes are additive — no existing call site or persisted document shape may break. `schema_version` on `UserProfile` stays at `2`; the new field relies on dataclass defaults for backward compatibility.
- **Constraint:** Follow IODA — data model change in `UserProfile` (Data), merge logic in `MemoryProvider` (Provider), content formatting in `Mind` (Integration), tool allow-list in `UpdateProfileTool` (Portal-side tool).
- **Constraint:** Exact wording of the agent-result line beyond the `Tools used:` contract is flexible; downstream parsing (TASK-005) keys off that substring.
- **Assumption:** `AgentResult.tools_used` is already populated correctly by the ReAct loop (`react_loop.py`); this task only surfaces it in chat content.
- **Assumption:** Case-insensitive deduplication compares normalised strings (e.g. lowercased) for equality; first-seen casing is retained in storage.
- **Assumption:** `Message.kind` is not set in this task (owned by [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]); FR-1 applies to the system-role line content regardless of kind metadata.

## Out of scope

- `Message.kind`, conversation state v3, migration v2→v3, ingest counters, compression settings ([[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]).
- Mechanical parsing of `Tools used:` into a `skills` set, participant extraction, or applying deltas from summariser output ([[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]).
- Building or refreshing `user_introduction` messages ([[TASK-002-user-introduction-on-ingest/task|TASK-002]]).
- Compression triggers, `Maintenance`, summariser provider, vector store, recall skill (TASK-003–TASK-009).
- Prompt or summariser schema changes; redaction rules for profile extraction.
