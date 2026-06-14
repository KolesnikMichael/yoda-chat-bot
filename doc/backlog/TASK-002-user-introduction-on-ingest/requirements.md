---
id: TASK-002
doc: requirements
updated: 2026-06-12
---

# TASK-002: user introduction on ingest — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) adds a non-visible `user_introduction` message kind that carries a snapshot of a participant's `UserProfile` so Yoda has profile context in the live tail without an extra retrieval round-trip. [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] introduced `Message.kind`, `Conversation.introduced_users`, and visibility rules; [[TASK-000-compression-prerequisites/task|TASK-000]] added `UserProfile.skill_preferences`. Neither task inserts introductions — that is this task's deliverable.

On ingest of a participant's first `user`-kind message, the system must lazily insert a `user_introduction` immediately before that message and record the participant in `introduced_users` for O(1) lookup on later messages. The same path serves private and group chats ([[chat_context_management#Private vs. group chats]]). A reusable Core helper, parameterised by message range, must be designed now so [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] can reuse it for compression refresh (transformation step 8) and graft/merge reconciliation on `new_arrivals` without refactoring.

Stakeholders: Yoda (profile context in LLM input), operators upgrading deployments where TASK-001 migration may have backfilled `introduced_users` from historical `user` authors without creating `user_introduction` messages, and TASK-006 (depends on the shared Core helper contract).

## Functional requirements

### FR-1: `user_introduction` message shape

Stored introductions must conform to the master-design kind and visibility rules.

**Acceptance criteria:**
- [ ] A `user_introduction` message is stored with `kind="user_introduction"`, `role="system"`, and `user_id` set to the participant being introduced.
- [ ] `user_introduction` is **non-visible** per [[chat_context_management#Visibility]]: ingest does not increment `visible_messages` or update `last_visible_at`.
- [ ] The message is persisted in `Conversation.messages` and round-trips through the conversation stash (schema v3) with `kind` and `user_id` intact.
- [ ] `Message.to_llm_dict()` includes the introduction's `text` in LLM-bound message lists (profile context must reach the model; `kind` itself is not added as an extra LLM field).

### FR-2: Profile snapshot content

Introduction text is a deterministic snapshot of the participant's current profile for `(user_id, chat_id)`.

**Acceptance criteria:**
- [ ] Content is built from the `UserProfile` returned by `MemoryProvider.get_user_profile(user_id, chat_id)` at introduction time (empty profile if none stored).
- [ ] Snapshot includes all substantive profile fields: `preferred_name`, `gender`, `location`, `timezone`, `occupation`, `interests`, `facts`, and `skill_preferences` (including non-empty `skill_preferences` buckets when present per [[TASK-000-compression-prerequisites/task|TASK-000]]).
- [ ] Internal bookkeeping fields (`schema_version`, `updated_on`) are not required in the snapshot text.
- [ ] When all substantive fields are empty, the message is still created with well-formed content (e.g. an explicit empty-profile marker) rather than being skipped.
- [ ] Two introductions built from identical `UserProfile` values produce identical `text` (stable formatting for tests and compression refresh).

### FR-3: Lazy insertion on `user`-kind ingest

When a new participant speaks, their first `user` message in the live tail is preceded by an introduction.

**Acceptance criteria:**
- [ ] On ingest of a message with `kind="user"` and non-null `user_id`, if `user_id ∉ conversation.introduced_users`, the system inserts a `user_introduction` for that user immediately **before** the new user message, then adds `user_id` to `introduced_users`.
- [ ] On ingest of a `user`-kind message when `user_id ∈ conversation.introduced_users`, no additional `user_introduction` is inserted for that user.
- [ ] Insertion runs in the same logical ingest transaction as the user message append (both appear in `Conversation.messages` before the conversation is saved and before the LLM reply path reads `to_llm_messages()`).
- [ ] The ingest hook applies to every code path that appends `kind="user"` messages (at minimum `Mind.process_message_batch`); assistant, task_result, and other kinds do not trigger introduction logic.
- [ ] A conversation with no prior user messages receives exactly one introduction before the first user message in a private chat.

### FR-4: Reusable Core helper (range-parameterised)

Core logic for ensuring introductions precede first user messages must be shared with TASK-006.

**Acceptance criteria:**
- [ ] `MemoryCore` exposes a synchronous helper (name chosen in design) that, given a `Conversation`, a half-open message index range `[start, end)`, and a way to obtain/build snapshot text per `user_id`, ensures: for every distinct `user_id` that has a `kind=="user"` message in that range, a `user_introduction` for that user immediately precedes that user's **first** such message in the range.
- [ ] The helper is idempotent: running it twice on the same range without intervening mutations does not duplicate introductions or corrupt `introduced_users`.
- [ ] The helper updates `conversation.introduced_users` to reflect introductions it inserts; it removes a user from `introduced_users` only when design explicitly requires (ingest path does not remove entries — drops on missing tail users are owned by TASK-006 compression step 8).
- [ ] The helper operates only on the specified range (not necessarily the full message list), so TASK-006 can invoke it on a compression copy tail and on a `new_arrivals` slice without refactoring.
- [ ] Unit tests cover the helper in isolation (multi-user range, user with no messages in range, idempotency, empty profile).

### FR-5: `introduced_users` bookkeeping and persistence

The set must stay consistent with introductions present in the live tail and support O(1) ingest checks.

**Acceptance criteria:**
- [ ] After ingest handling for a `user`-kind message, `user_id ∈ conversation.introduced_users` if and only if a `user_introduction` for that user exists in the tail before that user's first `user`-kind message (post-apply invariant from [[chat_context_management#Post-apply invariant]], applied here to the live tail).
- [ ] `introduced_users` continues to serialise as a sorted JSON integer array in the stash and deserialises to `set[int]` (behaviour established in TASK-001).
- [ ] Ingest of `user_introduction` messages themselves does not modify `introduced_users` (only the introduction logic on `user` ingest and the Core helper do).

### FR-6: Migration and pre-TASK-002 stash compatibility

TASK-001 v2→v3 migration backfills `introduced_users` from historical `user` authors without creating `user_introduction` messages. TASK-002 must not leave those conversations permanently without profile context.

**Acceptance criteria:**
- [ ] Given a conversation loaded from stash with one or more historical `user`-kind messages, non-empty `introduced_users`, and zero `user_introduction` messages, the next ingest or reconciliation pass leaves the tail satisfying FR-5's invariant (missing introductions inserted, set corrected).
- [ ] New conversations (empty `introduced_users`, no `user_introduction` messages) behave per FR-3 without special cases visible to callers.

### FR-7: Private and group chat parity

One code path covers both chat types.

**Acceptance criteria:**
- [ ] In a private chat, the sole participant's first `user` message is preceded by one introduction; subsequent messages from the same participant do not add another.
- [ ] In a group chat, two participants each sending their first `user` message receive separate introductions immediately before their respective first messages; order in `Conversation.messages` reflects speak order.
- [ ] No chat-type-conditional branches in Core helper logic (chat type may influence upstream profile storage but not introduction placement rules).

### FR-8: Integration tests

End-to-end coverage for the primary ingest scenarios named in the task scope.

**Acceptance criteria:**
- [ ] **Private chat:** first user message → exactly one `user_introduction` before it in `messages`; LLM message list includes the snapshot; second user message → no second introduction; `introduced_users == {user_id}`.
- [ ] **Group chat:** two users' first messages → two introductions in speak order, each before the corresponding user's first message; `introduced_users` contains both ids.
- [ ] **Repeated messages:** third and later messages from an already-introduced user do not change introduction count or `introduced_users` membership.
- [ ] Non-visible counter invariant: total `visible_messages` after introductions equals the count of `user` + `assistant` messages only (introductions excluded).

## Constraints & assumptions

- **Constraint:** Follow IODA — snapshot formatting and range helper in `MemoryCore` (Core); profile fetch in `MemoryProvider` (Provider); ingest orchestration at the boundary where user messages enter memory (`Mind` and/or `MemoryProvider`, per design); Data types unchanged except any small DTO helpers colocated with Core.
- **Constraint:** Depends on [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] (kinds, `introduced_users` field, stash v3) and [[TASK-000-compression-prerequisites/task|TASK-000]] (`skill_preferences` on `UserProfile`) being merged before implementation.
- **Constraint:** `introduced_users` ingest lookup remains O(1); tail scans are confined to the Core helper's explicit range parameter (used by compression/reconciliation in TASK-006), not on every ingest once a user is introduced.
- **Constraint:** User-visible Telegram behaviour is unchanged — introductions are internal context, not sent as chat replies.
- **Assumption:** `Perception` / `Mind` always set `user_id` on user-originated lines; introduction logic keys off `user_id`, not role alone.
- **Assumption:** Exact snapshot string format (labels, ordering, empty-field omission) is a design choice as long as FR-2 acceptance criteria hold; TASK-006 refresh reuses the same builder.
- **Assumption:** Profile changes after an introduction do not trigger re-insertion until compression refresh (TASK-006); the unfolding tail carries newer facts until then ([[chat_context_management#Insertion on message ingest]]).
- **Assumption:** `get_user_profile` is async; design chooses how to bridge async fetch with Core's synchronous helper (e.g. prefetch profiles in Provider before calling Core).

## Out of scope

- `user_introduction` strip (transformation step 2), refresh (step 8), or graft/merge reconciliation on `new_arrivals` ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] — consumes the FR-4 helper only).
- Compression triggers, `Maintenance`, summariser, or profile delta application ([[TASK-003-compression-window-algorithms-core/task|TASK-003]]–[[TASK-005-summarizer-provider-and-profile-extraction/task|TASK-005]]).
- Re-introducing users mid-tail because `UserProfile` changed without compression (no "profile changed" or "long silence" triggers).
- Emitting `summary` messages or modifying `visible_messages` / `last_compressed_at` on compression apply.
- Changing v2→v3 migration logic in `migration.py` unless required solely to satisfy FR-6 (prefer runtime reconciliation over re-migration).
