---
id: TASK-005
doc: requirements
updated: 2026-06-15
---

# TASK-005: summarizer provider and profile extraction — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) compresses long conversations by replacing an older message window with an inline `summary` block and durable profile deltas. The riskiest step is a single LLM call that must return a strict JSON envelope (`summary`, `topics`, `profile_updates`) plus mechanically derived metadata (`participants`, `skills`). That interaction is isolated here so it can be developed and tested against a fake LLM before the full apply pipeline lands in [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]].

[[TASK-000-compression-prerequisites/task|TASK-000]] added `Tools used: …` in agent `task_result` content and append-only delta keys on `UserProfile`. [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] added `Message.kind`, so participants and skill extraction can key off `kind == "user"` and `kind == "task_result"` without text heuristics. This task delivers `SummarizerProvider` — an IODA Provider that depends only on the language (LLM) API — and the pure parsing/validation/redaction logic around the summariser contract in [[design/prompts/summarizer|summarizer prompt]] and [[chat_context_management#Summarizer envelope]].

Stakeholders: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] (needs a stable `summarise` return type and profile deltas to pass to `MemoryProvider.update_user_profile`), and operators (profile PII must never be stored from redactable content).

## Functional requirements

### FR-1: `SummarizerProvider` as an IODA Provider

The summarisation unit is a self-contained Provider testable without Redis, Maintenance, or compression locks.

**Acceptance criteria:**
- [ ] A `SummarizerProvider` class exists under `yoda/mind/` (exact module path is a design choice).
- [ ] The Provider depends only on the LLM API façade (`LLMApi` or a thin wrapper) and summariser configuration (model name, prompt text) — **no** `MemoryProvider`, `StorageApi`, or Maintenance imports.
- [ ] The Provider performs **no** persistence: it does not call `MemoryProvider.update_user_profile`, does not write conversation stashes, and does not mutate the input `chunk` list.
- [ ] `SummarizerProvider` is constructible from the wiring file with the same language API used elsewhere (per [[chat_context_management#Maintenance integration]]); construction may land in this task or remain test-only until TASK-006 wires apply — but the class and its public contract must be importable and unit-tested without starting the bot.

### FR-2: `summarise` public contract

One async entry point runs the full summarisation unit on a pre-stripped message chunk.

**Acceptance criteria:**
- [ ] `SummarizerProvider` exposes `async def summarise(self, chunk: list[Message], participant_profiles: dict[int, UserProfile]) -> SummarizerResult` (exact result type name is a design choice).
- [ ] `chunk` is the compression window **after** apply-side stripping of `user_introduction` messages (stripping is owned by TASK-006; tests pass already-stripped chunks).
- [ ] `participant_profiles` maps `user_id` → current `UserProfile` for every user in the mechanical `participants` set (FR-5). The Integration (TASK-006) fetches profiles and passes them in — the Provider does not load profiles itself.
- [ ] `SummarizerResult` includes at minimum: `summary: str`, `topics: list[str]`, `participants: list[int]`, `skills: set[str]` (or sorted list — design choice, but stable for tests), and `profile_updates: dict[int, dict]` keyed by integer `user_id` with per-user delta dicts ready for `MemoryProvider.update_user_profile` (FR-8).
- [ ] Record-schema fields that depend on apply context (`id`, `chunk_start_message_id`, `chunk_end_message_id`, `chunk_visible_count`, `created_at`) are **not** produced by this Provider — TASK-006 merges them when building inline `summary` messages, outbox entries, and Chroma records.

### FR-3: LLM call and prompt assembly

The Provider performs exactly one LLM call per `summarise` invocation, following [[design/prompts/summarizer|summarizer prompt]].

**Acceptance criteria:**
- [ ] The call uses `response_format = {"type": "json_object"}` (via existing `LLMApi.parse_chat_async` or equivalent).
- [ ] The **system** message is the static summariser prompt text from [[design/prompts/summarizer#Static system prompt]] (loaded from the design doc file, a packaged prompt module, or settings — design choice).
- [ ] The **user** message is the dynamic context block with two sections in order: `== PROFILES ==` then `== CHUNK ==`, per [[design/prompts/summarizer#Dynamic context block]].
- [ ] `== PROFILES ==` contains one JSON object per line for each `user_id` in `participants`, shaped `{"user_id": <id>, "profile": <UserProfile.to_dict() or equivalent>}`; profiles for users not in `participants` are omitted.
- [ ] `== CHUNK ==` contains one JSON object per message with fields `kind`, `ts` (from `Message.timestamp`, ISO-8601 UTC), and `content` (from `Message.text`); `user_id` is included when `kind == "user"`.
- [ ] Chunk serialisation includes only message kinds present in the stripped chunk (`user`, `assistant`, `task_result` in typical runs); the Provider does not re-infer `kind` from `role` or text.
- [ ] Exactly one LLM request is made per `summarise` call (no retry loop inside the Provider).

### FR-4: JSON envelope parsing and validation

LLM output is parsed strictly; any deviation fails fast so the caller can skip the compression iteration.

**Acceptance criteria:**
- [ ] The raw response is parsed with `json.loads` then validated (Pydantic model or equivalent Core validator).
- [ ] The top-level object must contain all three keys: `summary` (non-empty string), `topics` (list of strings, may be empty `[]`), `profile_updates` (object, may be empty `{}`). Missing keys or wrong JSON types raise a dedicated validation error (not silently coerced).
- [ ] `summary` after validation is non-empty whitespace-stripped text.
- [ ] `topics` length is at most 5 after validation (per prompt); excess entries raise validation error.
- [ ] Each `profile_updates` key is a stringified user id parseable to `int`; non-numeric keys raise validation error.
- [ ] Per-user delta objects must not be empty (`{}`) — empty per-user dicts are dropped during normalisation; if a user entry becomes empty after redaction (FR-7), that user is omitted from the returned `profile_updates`.
- [ ] Scalar delta fields (`preferred_name`, `gender`, `location`, `timezone`, `occupation`) reject `null`, empty string, and whitespace-only values — such entries are dropped (not passed through as erasures).
- [ ] Only allowed per-user keys are accepted: the five scalar fields above, `interests_to_add`, `facts_to_add`, `skill_preferences_to_add`. Unknown keys raise validation error.
- [ ] `interests_to_add` and `facts_to_add` must be lists of non-empty strings; `skill_preferences_to_add` must be a dict mapping skill names to non-empty lists of non-empty strings.
- [ ] Validation failures and `json.JSONDecodeError` propagate to the caller (no fallback summary, no partial result).

### FR-5: Mechanical `participants` extraction

Participant ids are derived from the chunk without LLM involvement.

**Acceptance criteria:**
- [ ] `participants = sorted({m.user_id for m in chunk if m.kind == "user" and m.user_id is not None})`.
- [ ] Messages with `kind != "user"` or `user_id is None` do not contribute to `participants`.
- [ ] Order is ascending numeric sort; duplicates are deduplicated.

### FR-6: Mechanical `skills` extraction from `task_result` content

Skill names are parsed from agent `task_result` lines using the TASK-000 content contract.

**Acceptance criteria:**
- [ ] For each message with `kind == "task_result"`, if `text` contains the substring `Tools used: `, the value after that substring up to the next `.` (first sentence boundary after the clause) is parsed.
- [ ] When the parsed value is the literal `none` (case-sensitive per TASK-000), that message contributes no skill names.
- [ ] Otherwise the value is split on `, ` (comma + space) into individual skill names; leading/trailing whitespace on each name is stripped; empty tokens are ignored.
- [ ] `skills` is the set union of names from all qualifying `task_result` messages in the chunk (stable ordering in `SummarizerResult` is a design choice but must be deterministic in tests).
- [ ] `task_result` messages without a `Tools used: ` substring (scheduled reminders, failures, clarifications) contribute nothing — no error.
- [ ] Skill names are matched as-is (open vocabulary); no validation against a tool registry.

### FR-7: Redaction on `profile_updates`

Structured profile deltas must never store redactable PII; contrast with summary prose where `[REDACTED]` is used (summary redaction is the LLM's job per prompt — this FR covers **post-parse** sanitisation of structured fields only).

**Acceptance criteria:**
- [ ] Redactable classes match [[chat_context_management#Profile extraction details / Redaction]] and [[design/prompts/summarizer|summarizer prompt]]: e-mail addresses, phone numbers, street-level postal addresses, IBAN / bank-card / account numbers, passwords, API tokens, secret keys.
- [ ] When a scalar field's entire value matches a redactable pattern, that field is **dropped** from the per-user delta (not stored as `[REDACTED]`).
- [ ] When an `interests_to_add`, `facts_to_add`, or `skill_preferences_to_add` item matches a redactable pattern, that **item** is dropped; other items in the same list survive.
- [ ] City and country names in `location` are **not** treated as redactable solely for being geographic — only street-level address patterns are redacted.
- [ ] After redaction, users with no remaining delta keys are omitted from `profile_updates`.
- [ ] Redaction logic lives in a Core helper or validator callable from unit tests without an LLM (exact split Core vs Provider is a design choice; behaviour must be testable in isolation).

### FR-8: Returned profile deltas (shapes only — no apply)

The Provider returns normalised deltas for the Integration to apply; merge semantics inside `MemoryProvider` remain owned by TASK-000.

**Acceptance criteria:**
- [ ] Returned `profile_updates` uses integer `user_id` keys mapping to dicts whose keys are exactly the delta fields the summariser emitted (post-validation and post-redaction).
- [ ] Scalar fields in the returned dicts use overwrite semantics at apply time (`preferred_name`, `gender`, `location`, `timezone`, `occupation`).
- [ ] `interests_to_add`, `facts_to_add`, and `skill_preferences_to_add` are returned as-is for append-with-dedup merge in `MemoryProvider` (TASK-000 FR-3).
- [ ] An LLM response with `"profile_updates": {}` yields an empty dict in `SummarizerResult` — valid, no error.
- [ ] The Provider never calls `MemoryProvider.update_user_profile` (IODA: Provider-to-Provider forbidden; TASK-006 applies deltas in transformation step 5 before `user_introduction` refresh).

### FR-9: Logging

Observability without leaking user content at default log levels.

**Acceptance criteria:**
- [ ] On validation failure, log at **error** with exception type and a short reason; raw LLM JSON may be truncated in the log (existing `LLMApi` debug pattern) but must not appear at info level.
- [ ] Successful runs log at **debug** only; debug logs may include truncated summary length and participant/skill counts but must not log full chunk text, profile snapshots, or complete `profile_updates` payloads.

### FR-10: Unit tests against a fake LLM façade

The summariser is fully testable without network or Redis.

**Acceptance criteria:**
- [ ] Tests inject a fake `LLMApi` (or stub) that returns predetermined JSON strings.
- [ ] Coverage includes: happy-path envelope parse; empty `profile_updates`; scalar, list, and `skill_preferences_to_add` delta shapes in the return value; redaction dropping a PII item while keeping safe items; `participants` from mixed `user` / `assistant` / `task_result` chunks; `skills` from `Tools used: a, b`, `Tools used: none`, and absent `Tools used:` on reminder-style `task_result`; invalid JSON and schema violations raising the expected error; dynamic context block contains profile lines only for mechanical participants.
- [ ] `python -m pytest` from the project root passes with the new tests.

## Constraints & assumptions

- **Constraint:** Follow IODA — `SummarizerProvider` is a Provider (async LLM adapter); parsing, redaction, and mechanical field rules are Core/static helpers; `SummarizerResult` (and any envelope Pydantic models) are Data types. No Integration logic in this task.
- **Constraint:** Epic `internal_compat` is `none` — no acceptance criteria for partial deploy states between member tasks on the shared branch.
- **Constraint:** Epic `external_contract` is `migrate-on-merge` — this task does not change stash schema or migration; it consumes `Message.kind` and `UserProfile.skill_preferences` as already defined by TASK-001 and TASK-000.
- **Constraint:** Fail fast on config and validation — no silent fallbacks for malformed LLM output or missing summariser settings.
- **Constraint:** `SummarizerProvider` must not depend on another Provider or Integration.
- **Assumption:** [[TASK-000-compression-prerequisites/task|TASK-000]] and [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] are complete: `Tools used: …` agent lines, delta merge keys, and `Message.kind` behave as specified.
- **Assumption:** Chunk stripping (removing `user_introduction`, skipping leading `prompt` / existing `summary` blocks before the LLM payload) is performed by the apply Integration in TASK-006, not inside `summarise`.
- **Assumption:** `participant_profiles` passed into `summarise` are the current Redis-backed profiles for chunk authors; stale snapshots in the prompt are acceptable because deltas are evidence-only and append keys dedupe at apply time.
- **Assumption:** Summariser model name and API key come from the same configuration surface as other mind LLM calls unless a dedicated `mind.memory.chat_compression.summarizer` block is added — exact settings key is a design decision.
- **Assumption:** Summary prose redaction (`[REDACTED]` in narrative text) is enforced by the static prompt and spot-checked in tests only where structured post-processing is unnecessary; FR-7 covers structured `profile_updates` only.

## Out of scope

- Calling `MemoryProvider.update_user_profile` or persisting profile changes ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] transformation step 5).
- Delta-key merge implementation inside `MemoryProvider` ([[TASK-000-compression-prerequisites/task|TASK-000]] — already delivered).
- Compression snapshot / transform / apply / graft+merge, per-conversation lock, inline `summary` message creation, FIFO eviction, `pending_vectorization`, `Chat.history` audit entry ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]).
- `user_introduction` strip, refresh, and merge reconciliation ([[TASK-002-user-introduction-on-ingest/task|TASK-002]], TASK-006).
- Compression triggers, `Maintenance.compress_conversations` wiring beyond optional Provider construction ([[TASK-004-maintenance-integration-shell/task|TASK-004]], TASK-006).
- Chroma, embeddings, `flush_summary_outbox`, `recall_conversation` skill ([[TASK-008-summary-store-and-outbox-flush/task|TASK-008]], [[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Changes to the summariser prompt prose in [[design/prompts/summarizer|summarizer.md]] unless a minimal fix is required for implementability (prompt content is the design source of truth).
- Building deterministic `summary` record ids (`sha256(…)`) — owned by apply / vector store tasks.
