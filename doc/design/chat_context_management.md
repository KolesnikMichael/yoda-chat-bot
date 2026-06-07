# Chat Context Management

Plan for managing the long-term contents of a `Conversation`: when and how to
compress old messages, how to extract durable knowledge from them, and how to
restore enough context for Yoda to behave coherently after compression.

This document evolves in stages. Sections appear here only after the
corresponding design decision is settled. Anything still open is parked in
[Open questions](#open-questions).

---

## Foundational concepts

### Message kinds

Every `Message` carries a `kind` field (schema migration required —
see [Persistence and migration](#persistence-and-migration)).
The field is statically typed as a `Literal` over six values:

```python
Kind = Literal[
    "prompt",
    "user",
    "assistant",
    "task_result",
    "user_introduction",
    "summary",
]
```

| kind | meaning | producer |
|---|---|---|
| `prompt` | system prompt at the start of a conversation | `Conversation.ensure_system_prompt` |
| `user` | a user-originated message (perception output) | `Perception.perceive_message` |
| `assistant` | Yoda's reply | `Mind._reply_and_send` |
| `task_result` | non-visible system message carrying the outcome of either a delegated agent task or a fired scheduled reminder. Both are bot-initiated payloads with the same downstream treatment by triggers and summarisation; merging them keeps the enum minimal. | `Mind._handle_agent_result`, `Mind.deliver_scheduled_reminder` |
| `user_introduction` | non-visible system message carrying a snapshot of a participant's `UserProfile`, lazily inserted before that user's first appearance in the live tail and refreshed at compression. Does not exist in the codebase yet — see [`user_introduction` lifecycle](#user_introduction-lifecycle). | `MemoryProvider` ingest hook + `user_introduction` lifecycle refresh |
| `summary` | compression block produced by this design | `Maintenance.compress_conversations` (via `MemoryProvider.apply_compression`) |

`kind` is set by the producer at message creation time, not inferred
downstream. Inference is used only during the v2 → v3 migration of
existing stashed messages — see [Persistence and
migration](#persistence-and-migration).

### Visibility

A message is **visible** if its kind is `user` or `assistant`. All
other kinds (`prompt`, `summary`, `task_result`, `user_introduction`)
are **non-visible**.

Visibility matters because:
- it defines what counts towards the minimum live tail — Yoda must always
  have roughly the same recent message screen that the user sees;
- it defines which intervals count as "gaps" for the timeout-trigger.

### Activity

"Activity" for trigger logic means **user messages only**.

- Assistant replies and skill/agent results that follow a user message
  immediately enough belong to the same chunk and are compressed together
  with their triggering user message.
- Bot-initiated system messages (scheduled reminders, recurrent task
  results) **do not count as activity**. Otherwise Yoda's own 3am reminder
  could indefinitely block the timeout-trigger.

This is reflected in `Conversation.last_visible_at` (see [Conversation
state fields](#conversation-state-fields)), which is bumped on
visible-message ingest only — never on non-visible system traffic such
as scheduled reminders. The timeout-trigger therefore stays
activity-aware by construction. `Chat.last_active` continues to track
user-message timestamps as chat-level metadata, separate from trigger
logic.

### Boundary alignment by kind (universal rule)

Wherever a candidate compression boundary is produced — middle of
conversation for the size-trigger, gap location for the timeout-trigger,
or any future trigger — the boundary is then **shifted so that the live
tail starts at a `user` (private chat) or `user_introduction` (group chat)
message**.

The rule is partially redundant for the timeout-trigger: gap detection by
visibility already lands the boundary on `user`/`assistant`, so the rule is
satisfied by construction. It is recorded as universal so that any future
trigger inherits it without re-derivation, and it is the only source of
correctness for the size-trigger.

### Conversation state fields

`Conversation` carries five fields beyond the message list, used by
the compression triggers, the `user_introduction` lifecycle, and the
externalised summary store. All five are persisted as part of the
conversation stash.

- **`last_visible_at: float`** — Unix epoch timestamp (seconds, subsecond
  precision) of the most recent *visible* message. Bumped on every
  visible-message ingest. Used both for the quiet-for-N-runs check and
  the "anything changed since last compression" check of the
  timeout-trigger. Replaces `Chat.last_active` for trigger evaluation;
  `Chat.last_active` itself stays as chat-level metadata for unrelated
  bookkeeping. Default `0.0`.
- **`last_compressed_at: float`** — Unix epoch timestamp of the snapshot
  moment of the **most recent successful** compression run. Updated on
  successful commit only; failed or aborted runs do not touch it.
  Replaces the previously considered `Chat.updated_on`-based semantic.
  Default `0.0`.
- **`visible_messages: int`** — running count of messages in
  `Conversation.messages` whose kind is `user` or `assistant`.
  Incremented on every visible-message ingest in the same code path
  that bumps `last_visible_at`. Decremented exactly once per
  successful compression apply, by the number of visible messages
  inside the compressed chunk. Used as the entry guard for both
  triggers (`visible_messages > 2 * MIN_CHUNK_LENGTH` for the
  timeout-trigger; `visible_messages > SIZE_TRIGGER_THRESHOLD` for
  the size-trigger), so the firing decision is one integer comparison
  rather than a list walk over `prompt`, accumulated `summary`s and
  `user_introduction` markers. Default `0`.
- **`introduced_users: set[int]`** — set of `user_id`s for which a
  `user_introduction` system message currently exists in the live tail.
  Maintained as an O(1) lookup so message ingest does not have to scan
  the tail to decide whether to insert a `user_introduction`. See
  [`user_introduction` lifecycle](#user_introduction-lifecycle). Default empty.
- **`pending_vectorization: list[Summary]`** — outbox of `summary`
  blocks that have just been evicted from the inline tail and are
  waiting to be embedded and written to the vector store. Appended to
  by [Compression apply](#compression-apply) when
  `MAX_SUMMARY_COUNT` eviction fires; drained by
  [`Maintenance.flush_summary_outbox`](#single-ticking-loop) once
  embedding and Chroma write succeed. Lives on `Conversation` (rather
  than as a separate Redis key) so that the apply commit and the
  outbox push are persisted atomically by the same stash write. See
  [Persistence flow](#persistence-flow). Default empty.

The `0.0` default on both timestamps makes
`last_visible_at > last_compressed_at` trivially true on a conversation
that has any visible message and was never compressed — which is the
correct firing decision for that case out of the box.

#### Persistence and migration

The five fields are serialised together with `Conversation.messages`
into the conversation stash. `CONVERSATION_STASH_SCHEMA_VERSION` bumps
from 2 to 3 in the same release that introduces `Message.kind`. The
v2 → v3 migration step runs in the following order, on each stashed
conversation:

1. For each `Message` in the conversation, infer `kind` from existing
   fields. Pre-existing stashes contain only `prompt` / `user` /
   `assistant` / `task_result` worth of content (no `summary`, no
   `user_introduction` — both are new in this design), so inference
   reduces to:

   ```python
   def infer_kind(msg: Message, is_first: bool) -> str:
       if msg.role == "assistant":
           return "assistant"
       # Pre-migration role is "system" for everything except
       # assistant replies; perception wraps user-originated messages
       # as system role with user_id preserved.
       if is_first:
           return "prompt"
       if msg.user_id is not None:
           return "user"
       # role == "system", user_id is None, not first → bot-initiated
       # task delivery (agent result or scheduled reminder).
       known_prefixes = (
           "SCHEDULED REMINDER:",
           "Agent completed a task",
           "Ask the user (rephrase naturally",
       )
       if msg.text.startswith(known_prefixes):
           return "task_result"
       raise MigrationError(
           f"Unknown system-message prefix at chat_id=..., "
           f"message_id=...: {msg.text[:80]!r}"
       )
   ```

   Migration is **fail-fast**: an unknown system-message prefix
   aborts the run so the operator can examine the offending message
   before the stash is rewritten. If a new producer of system
   messages is ever added without updating `infer_kind`, that miss
   shows up loudly on the next upgrade rather than silently
   defaulting to `task_result`.

2. Walk the migrated `messages` once and, in the same pass:
   - collect distinct `user_id`s among `kind == "user"` messages into
     `introduced_users`;
   - count visible messages into `visible_messages`;
   - track the latest visible timestamp into `last_visible_at`
     (`0.0` if none).
3. Set `last_compressed_at` to `0.0` — pre-existing conversations have
   never been compressed under this design.
4. Set `pending_vectorization` to `[]` — pre-existing conversations
   have never had a summary evicted under this design (no `summary`
   blocks exist yet at all).

After this one-time migration on the first restart following the
upgrade, the fields stay consistent through normal operation; no
recurring full-message recomputation is needed.

### `Chat.history` schema

`Chat.history` is the chat-level **audit log**: a list of structured
records describing notable events that happen to the conversation
over its lifetime. It is **not** a copy of the discussion flow — that
is what `Conversation.messages` (plus, eventually, the externalised
summary store) is for. `Chat.history` is for events about events.

All entries share one envelope:

```json
{
  "ts":    "<iso8601 UTC>",
  "event": "<event_name>",
  ... event-specific fields ...
}
```

Compression entries (the only event type defined by this design)
look like this:

```json
{
  "ts":    "<snapshot_ts of the run>",
  "event": "compression",
  "added": {
    "summary_id":    "<sha256 — same id as the Chroma record and the outbox entry>",
    "visible_count": 42,
    "from_ts":       "<iso8601 of the first visible message in the chunk>",
    "to_ts":         "<iso8601 of the last visible message in the chunk>"
  },
  "evicted": [
    {"summary_id": "<sha256>", "added_at": "<iso8601 — when this summary was originally added inline>"}
  ]
}
```

Notes:

- `summary_id` is the deterministic identifier described in
  [Persistence flow / Deterministic record id](#deterministic-record-id).
  Sharing it across `Chat.history`, `pending_vectorization`, and the
  Chroma record gives an end-to-end trace of one summary block by a
  single id.
- `evicted` is always present, possibly empty (`[]`) when the
  `MAX_SUMMARY_COUNT` cap was not reached on this run — an absent
  field would force readers to distinguish "no eviction happened"
  from "field missing because of an old writer".
- Typically `evicted` has length 1 (FIFO one-in-one-out), but the
  list shape handles multi-eviction without schema change.

The same envelope will host **other event types** as the project
grows. The next likely addition is `skill_invocation`, for agent
tasks; its concrete fields are out of scope of this design but will
follow the same `{ts, event, ...}` shape so consumers do not need a
per-event parser dispatch.

The compression audit entry is written by [Compression apply step
10](#transformation-on-the-copy) and persisted atomically with the
rest of the apply.

---

## Prerequisites

Two codebase changes have to land **before** the compression
implementation can use the data shapes assumed by this design. They
are small, self-contained, and independent of compression itself —
they only widen the existing schemas.

### Prerequisite: skill name in `task_result` content

The summarizer and the mechanical `skills` extractor both expect the
skill (tool) name to be present in the **content** of every
`task_result` message stored in `Conversation.messages`. Today it is
not: `Mind._handle_agent_result` writes a line of the form

```
Agent completed a task. Result: {result.answer}. Communicate this to
the user naturally
```

`result.tools_used: list[str]` is already available on
`AgentResult`; it just needs to flow into the chat line, for example:

```python
tools = ", ".join(result.tools_used) if result.tools_used else "none"
line = (
    f"Agent completed a task. Tools used: {tools}. "
    f"Result: {result.answer}. ..."
)
```

The exact wording is flexible. The contract for downstream code is:
the substring `Tools used: <name>[, <name>]*` (or any equivalent
machine-parseable form) appears in every `task_result` content
produced by `_handle_agent_result`. Reminder-style `task_result`
records that did not go through the agent (e.g. plain scheduled
reminders) keep their current content; the mechanical extractor
treats their `skills` set as empty.

### Prerequisite: `UserProfile.skill_preferences`

`UserProfile` gains a new field:

```python
skill_preferences: dict[str, list[str]] = field(default_factory=dict)
```

Storage layer changes:

- `MemoryProvider` migration: existing stashed profiles get
  `skill_preferences = {}` on first read (default value handles this
  for free if the dataclass field has `default_factory=dict`).
- `MemoryProvider.update_user_profile` is extended per
  [Profile extraction details](#profile-extraction-details).
- The agent-side `update_profile` tool's `ALLOWED_FIELDS` set gains
  `"skill_preferences"` so the agent can write the field through the
  replace path when it has a strong reason to (e.g. user explicitly
  asks to forget a stored preference). Compression always uses
  `skill_preferences_to_add`.

The field is then included in the `UserProfile` snapshot that
`user_introduction` carries, so Yoda sees skill-specific preferences
in the live tail without any extra retrieval round-trip.

---

## Compression triggers

There are **two distinct compression algorithms**, not one algorithm with
two firing conditions. They serve different goals and select the
compression window by different rules.

### Size-trigger — emergency cutoff

**Goal:** prevent runaway token cost and persona drift on long-running
chats where users themselves have stopped paging back.

**Rationale:** in real conversations almost no one scrolls back ~300
messages, let alone uses search. Past that horizon humans operate from
gist, not detail. Yoda can do the same and stop paying tokens for
fine-grained history that will not be referenced.

**Firing condition:** `conversation.visible_messages >
SIZE_TRIGGER_THRESHOLD` (default `300`, configured at
`mind.memory.chat_compression.size_trigger_threshold`). Visible-only
counting matches the timeout-trigger and ignores `prompt`,
accumulated `summary` blocks, and `user_introduction` markers, none of which
should drive an emergency cutoff.

**Window selection:** simple, **non-semantic**. The point of this trigger
is that we cannot afford to wait for a clean chunk boundary — we are
already over budget. Halve the conversation by visible-message count
(older half compressed, newer half kept raw), then apply the universal
boundary alignment rule.

**Expected frequency:** rare. This is a safety net, not the primary
compression path.

### Timeout-trigger — clean-chunk compression

**Goal:** compress along **complete semantic chunks** of conversation,
taking advantage of natural quiet periods.

**Rationale:** when humans go quiet for several hours (especially
overnight) their own working context resets. On returning to the chat they
may recall or scroll back ~30–40 messages, but rarely more. Compressing
during these quiet periods means:
1. compression boundaries align with natural topic boundaries — a chunk
   is "what was discussed before they went silent";
2. the user is unlikely to be mid-thought when their detailed history is
   replaced by a summary.

This is the **primary** compression path.

**Firing condition:** a distributed scheduled run, executed once per
hour, visits conversations for which **both** of the following hold:
- the conversation has been quiet for **N consecutive runs** — i.e.
  `now - conversation.last_visible_at >= N * 1h`;
- `conversation.last_visible_at > conversation.last_compressed_at` —
  i.e. visible activity has occurred since the last successful
  compression run. This guards against re-running compression on a
  conversation that has been quiet *and* unchanged since the previous
  run.

N is a setting with **two separate values** — one for private chats,
one for group chats, both default to `8`, configured at
`mind.memory.chat_compression.quiet_runs_before_compression.{private,group}`.

The two-knob split exists because in groups with users across time zones a
shared "night" may not exist, so groups may need a different (typically
larger) N. We accept that in extreme cases the timeout-trigger fires
rarely or late for groups — that is preferable to firing mid-conversation.

#### Window selection algorithm

```
1. Walk backwards from the newest message, counting only VISIBLE messages.
2. Once at least MIN_CHUNK_LENGTH visible messages have been counted,
   keep walking back looking for the first GAP.
3. A gap is an interval between two consecutive visible messages
   strictly greater than GAP_THRESHOLD.
4. If no such gap exists in the remaining range, abort the run as a
   no-op — leave the conversation untouched and wait for the next
   tick. Do NOT fall back to halving; that is the size-trigger's job.
5. Once the gap is found, the boundary is placed inside it.
6. Non-visible messages (`task_result`, `user_introduction`, ...) that fall inside
   the gap are attached to the NEXT burst — they go into the live tail,
   not into the compressed chunk.
7. Everything before the boundary, after skipping the leading `prompt`
   and any already-existing `summary` blocks, is compressed into a
   single new summary block.
```

Consequences:

- The MIN_CHUNK_LENGTH count is a **minimum**, not an exact length. If
  the MIN_CHUNK_LENGTH-from-end visible message is `assistant`, the
  algorithm continues walking back through `assistant`/`user` until it
  finds the gap; the live tail will then hold MIN_CHUNK_LENGTH or more
  visible messages, never fewer.
- Because gaps are measured between visible messages only, a stray
  `task_result` inside an otherwise quiet stretch does
  not split the chunk — it is silently absorbed into the next burst.
  *Example:* a user accidentally schedules a daily 3am news digest. The
  digest itself, the early-morning fallout, and the full morning
  conversation all land in one chunk — the desired behaviour.
- The boundary lands automatically on a `user` (or `user_introduction`) message
  through gap-by-visibility, so the universal alignment rule is satisfied
  by construction here.
- A continuously active chat with no internal pause longer than
  GAP_THRESHOLD never produces a chunk via this trigger, even once
  it eventually goes quiet. That is intentional: there is no natural
  semantic break to align with. Such a chat will be compressed by the
  size-trigger if it ever crosses the message-count threshold.

#### Single summary per run (default)

Per timeout-trigger run a **single** summary block is produced, regardless
of how many bursts the compressed window contained. This keeps the
algorithm simple and decouples gap detection from summary granularity.

A possible future refinement is finer-grained summaries — e.g. one summary
per detected sub-gap, or topic-keyed records. That refinement is
orthogonal to gap detection and is not pursued here unless the broader
memory design (see open questions on summary representation) demands it.
This document does not aim to build a "diary of the chat".

**Agent-result fidelity.** Non-visible system messages that fall *inside*
the compressed window (i.e. between visible messages, not inside a gap)
are included in the summarisation payload as-is — the algorithm does not
strip them, since they carry content rather than projected metadata. In
particular, `task_result` messages routinely carry information that
narrative-style compression loses first — URLs, IDs, exact tool
configurations, parameter values, error contexts. The summariser prompt
([`doc/design/prompts/summarizer.md`](design/prompts/summarizer.md)) explicitly
instructs the model to preserve such values **verbatim** in the summary,
separately from the narrative compression of the surrounding dialogue.

#### Constants and entry threshold

All of the empirical knobs below live in
`settings.json → mind.memory.chat_compression`; the
defaults listed are the values shipped with the repo and the values
referenced throughout this document. Names in code (loaded into a
`ChatCompressionSettings` dataclass at startup) match the JSON keys
1:1. The same dataclass also exposes the size-trigger threshold and
the per-chat-type silence knobs documented earlier in
[Size-trigger](#size-trigger--emergency-cutoff) and
[Timeout-trigger](#timeout-trigger--clean-chunk-compression).

- **`min_chunk_length = 30`** — the same value serves two roles by
  design: minimum visible length of the live tail (so Yoda always
  retains roughly the screen of recent messages a returning user
  sees), and minimum visible length of a compressed chunk (so we never
  spend an LLM call on a chunk smaller than what humans themselves
  would still recall in detail).
- **`gap_to_trigger_ratio = 0.5`** — single tunable that ties gap
  detection to the silence threshold. `GAP_THRESHOLD` is derived
  per-chat-type as
  `quiet_runs_before_compression[chat_type] * gap_to_trigger_ratio`,
  i.e. 4h for the default `N = 8`. Tying the two together guarantees
  by construction that an internal gap can never be longer than the
  silence required to fire the trigger, and that groups with larger
  `N` (time-zone-spread) automatically get proportionally larger gap
  thresholds, matching their slower natural rhythm. The ratio is a
  single setting rather than two independent thresholds to keep the
  invariant `GAP_THRESHOLD < N` non-optional.
- **`max_summary_count = 30`** — hard cap on the number of `summary`
  blocks coexisting inline in a single `Conversation`. When a
  compression run would push the count above the cap, the same atomic
  apply that inserts the new summary also evicts as many oldest
  `summary` blocks from the head of `Conversation.messages` — typically
  one in, one out. Eviction is FIFO by position, which equals FIFO by
  creation order since variant C never reorders summaries. Without this
  cap, variant C would let the prompt grow unboundedly on long-lived
  chats; with it, the inline conversation lives in a known envelope.
  Evicted summary blocks remain available through the externalised
  summary store — eviction here is purely about inline footprint, not
  data loss.

The full block, with the size-trigger and timeout-trigger settings
gathered alongside, looks like this in `settings.json`:

```json
"mind": {
  "memory": {
    "chat_compression": {
      "size_trigger_threshold":        300,
      "min_chunk_length":              30,
      "max_summary_count":             30,
      "gap_to_trigger_ratio":          0.5,
      "quiet_runs_before_compression": {
        "private": 8,
        "group":   8
      },
      "outbox_health_threshold":       10
    }
  }
}
```

`outbox_health_threshold` controls operator warnings from
`flush_summary_outbox`; see
[Outbox health threshold](#outbox-health-threshold).

The Maintenance loop tick itself is unrelated to compression in
isolation — it also drives `flush_summary_outbox` and
`reconcile_active_jobs` — and lives at `mind.maintenance.tick_minutes`
(default `60`).

Throughout the rest of the document, the names `MIN_CHUNK_LENGTH`,
`GAP_THRESHOLD`, `MAX_SUMMARY_COUNT`, `SIZE_TRIGGER_THRESHOLD` and
the per-chat-type `N` refer to the values resolved from these
settings at startup.

The deliberate side effect of choosing `0.5` is that several short
sub-bursts separated by 1–3 hour pauses will be slept through and
collapsed into one chunk and one summary. That matches the design's
"single summary per run" stance — we are not building a per-topic
diary.

A timeout-trigger run only attempts compression when
`conversation.visible_messages > 2 * MIN_CHUNK_LENGTH`. This is a
*necessary* but not *sufficient* condition: the algorithm may still
abort as a no-op if no qualifying gap is found (step 4 of window
selection).

---

## Interaction between triggers

Size-trigger may fire on a busy chat, leaving the conversation shaped as:

```
[prompt, summary_v1, recent_tail_of_raw_messages]
```

If that same chat then goes quiet long enough for the timeout-trigger to
fire, the timeout-trigger does **not** rewrite `summary_v1`. It produces a
new summary block alongside the existing one:

```
[prompt, summary_v1, summary_v2, recent_tail_of_raw_messages]
```

This is variant **C** (parallel summaries) and is the **permanent
choice** for this design. Variant **B** — re-summarising
`summary_v1 + new growth` into a fresh combined `summary_v2` — is
explicitly excluded: the design relies on summaries never being
re-summarised, to keep cost predictable and avoid information loss
compounding across generations.

Implication: the conversation can carry several summary blocks in
chronological order. Algorithms downstream of compression (system-prompt
rebuild, profile extraction, retrieval) must treat summary blocks as a
list, not a singleton.

The list is bounded by `MAX_SUMMARY_COUNT` (see
[Constants and entry threshold](#constants-and-entry-threshold)). Once
the cap is reached, every new compression run evicts the oldest
inline `summary` block at apply time. The full history of summaries is
preserved out-of-band in the externalised summary store; only the
inline tail is bounded.

---

## `user_introduction` lifecycle

`user_introduction` is a non-visible system message that carries a snapshot of
a participant's `UserProfile`. It is lazily inserted before that user's
first appearance in the live tail and refreshed during compression, so
Yoda always has fresh profile context for any user actively present in
the tail without paying for that context for inactive registered
participants.

`Conversation.introduced_users` (see [Conversation state
fields](#conversation-state-fields)) is the bookkeeping set used to
make the ingest path O(1) instead of scanning the tail.

### Insertion on message ingest

When a new message of `kind == "user"` arrives:

1. If `user_id ∈ introduced_users` → no-op.
2. Else: build a `user_introduction` from the current `UserProfile` snapshot
   for `(user_id, chat_id)`, insert it immediately before the new user
   message, and add `user_id` to `introduced_users`.

There is no second insertion trigger ("after long silence", "profile
changed", etc.). `UserProfile` may evolve between compressions — for
example, an agent tool can update it after a user states a new fact —
but that information arrives to Yoda through the unfolding tail itself.
The next refresh of `user_introduction` happens at the next compression.

### Refresh during compression

The compression pipeline interacts with `user_introduction` markers
at two points; the full step-by-step pipeline lives in
[Compression apply / Transformation on the copy](#transformation-on-the-copy)
and is the single source of truth. This subsection only states the
`user_introduction`-specific contract:

- **Strip before summarisation** (transformation step 2).
  Every `user_introduction` message in the selected chunk is removed
  before the LLM call; the set of removed `user_id`s is held as
  `removed_users` for use in step 8. The markers do **not**
  participate in summarisation — they are projected metadata, not
  content, and the source of truth is `UserProfile` itself.

- **Refresh after summarisation** (transformation step 8).
  For each `user_id ∈ removed_users`, the tail of `copy.messages`
  after the just-inserted summary is scanned for that user's first
  `user`-kind message: if found, a fresh `user_introduction` is
  built from the just-updated `UserProfile` and inserted before it;
  if not found, the user is dropped from `copy.introduced_users` and
  will be re-introduced lazily on their next message via
  [Insertion on message ingest](#insertion-on-message-ingest).

  *Invariant:* `removed_users` equals the set of `user`-kind authors
  whose messages got compressed, by construction of insertion (every
  `user_introduction` is inserted directly before that user's first
  reply, so it shares chunk membership with that reply). The
  implementation should assert this invariant.

  This scan only sees the snapshot tail. Messages that arrived on
  the live conversation during the LLM call are reconciled
  separately at apply time — see
  [Apply: graft + merge](#apply-graft--merge).

### Private vs. group chats

The same logic runs for private chats. With a single user:
- `introduced_users` holds at most one entry.
- Every compression has `removed_users = {single_user}` and runs the
  identical pipeline with one element instead of many.

The added cost over a chat-type-conditional shortcut is negligible (a
single-element set, one extra `user_introduction` per compression). The
upside is a single code path with one test surface and no
chat-type-conditional branches in core logic, so the design uses the
same lifecycle for both.

---

## Compression apply

The mechanic by which a compression run, having computed its summary,
commits the result back to the live `Conversation`. This section
defines the snapshot/transform/apply algorithm. Locking, ordering with
vector-store persistence, and failure handling are still
[open](#open-questions); this section assumes only that snapshot and
apply each happen indivisibly with respect to ingest.

### Snapshot

At the start of the run, with the live conversation briefly held in a
consistent state:

- `N_old = len(live.messages)` — the size of the messages list at the
  moment of snapshot.
- `copy = deep_copy(live)` — a self-contained `Conversation` that the
  compression run will transform without any further reference to the
  live object until apply.

Both are captured in one indivisible step. After this point, ingest
of new messages on `live` continues unaffected; `copy` is the
compression run's private working state.

The append-only nature of `live.messages` is the load-bearing
assumption: indices `0..N_old-1` are never mutated after snapshot,
only extended. This makes `live.messages[N_old:]` an unambiguous
identifier of "everything that arrived during compression" at apply
time.

### Transformation on the copy

Compression operates **entirely on the copy**, producing what would
have been a complete, self-consistent post-compression conversation
**if no new messages had arrived during the LLM call**. The
transformation runs in this order:

1. [Window selection](#window-selection-algorithm) on `copy.messages`
   produces the chunk.
2. Strip `user_introduction` markers from the chunk into
   `removed_users`. See
   [`user_introduction` lifecycle / Refresh during compression](#refresh-during-compression)
   for the contract.
3. Run a single LLM call on the stripped chunk per
   [Summarizer envelope](#summarizer-envelope), producing
   `summary`, `topics`, and `profile_updates` in one JSON object.
   The summarizer prompt is in
   [`doc/design/prompts/summarizer.md`](design/prompts/summarizer.md).
4. Compute the mechanical record fields from the chunk:
   `participants = sorted({m.user_id for m in chunk if m.kind == "user"})`,
   `skills` = the set of skill names parsed out of `task_result`
   contents (relies on [Prerequisite: skill name in `task_result`
   content](#prerequisite-skill-name-in-task_result-content)). These
   plus the LLM output form the complete summary record for the
   [Record schema](#record-schema).
5. Apply each per-user delta in `profile_updates` to `UserProfile`
   via `MemoryProvider.update_user_profile`. Updates are persisted
   to the user-profile store directly — they do not live on `copy` —
   and must commit **before** step 8 so the `user_introduction`
   refresh sees fresh profiles. Delta semantics in
   [Profile extraction details](#profile-extraction-details).
6. Replace the chunk in `copy.messages` with the new `summary`
   block.
7. If the resulting `summary`-block count exceeds
   `MAX_SUMMARY_COUNT`, FIFO-evict the oldest summary block(s) from
   the head of `copy.messages` — same number as added in this run,
   typically one — and append each evicted block to
   `copy.pending_vectorization` so that the externalised summary
   store eventually picks it up via [Persistence
   flow](#persistence-flow).
8. `user_introduction` refresh on `copy`'s tail. For each
   `user_id ∈ removed_users`, scan the portion of `copy.messages`
   after the just-inserted summary for that user's first
   `user`-kind message:
   - **Found** → build a fresh `user_introduction` from the
     just-updated `UserProfile` and insert it immediately before
     that message; keep `user_id` in `copy.introduced_users`.
   - **Not found** → drop `user_id` from `copy.introduced_users`.
     The user will be re-introduced lazily on their next message
     via the ingest rule
     ([Insertion on message ingest](#insertion-on-message-ingest)).

   The scan only sees the snapshot tail; messages that arrived on
   the live conversation during the LLM call are reconciled
   separately at apply time — see [Apply: graft + merge](#apply-graft--merge).

   *Invariant:* the set of compressed `user`-kind authors equals
   `removed_users` exactly, by construction of insertion (every
   `user_introduction` is inserted directly before that user's first
   reply, so it shares chunk membership with that reply). The
   implementation should assert this.
9. Update derived fields on `copy`:
   - `copy.visible_messages -= chunk_visible_count`;
   - `copy.last_compressed_at = snapshot_ts`;
   - `copy.introduced_users` was already mutated by step 8.
10. Append a structured `compression` audit entry to
    `copy.chat.history` per
    [`Chat.history` schema](#chathistory-schema). Fields:
    `ts = snapshot_ts`,
    `added.summary_id` = the deterministic id of the just-inserted
    summary, `added.visible_count = chunk_visible_count`,
    `added.from_ts` / `added.to_ts` from the first/last visible
    messages in the chunk, and `evicted` from the blocks moved into
    `copy.pending_vectorization` in step 7 (each carrying its own
    `summary_id` and original `added_at`). The same shape is written
    by the size-trigger.

After step 10, `copy` is a valid `Conversation` representing the
state the live conversation **would** have ended up in had no
concurrent ingest happened.

### Apply: graft + merge

The apply step has two parts. Both run together as one indivisible
write to `live`.

**Graft.** Identify what arrived during the LLM call and stitch the
transformed copy in front of it:

```
new_arrivals = live.messages[N_old:]
live.messages = copy.messages + new_arrivals
```

**Merge new arrivals.** Bring the rest of the conversation state in
line with the new tail:

```
live.last_compressed_at = copy.last_compressed_at
live.chat.history       = copy.chat.history    # audit line included
live.visible_messages   = copy.visible_messages
                        + visible_count(new_arrivals)
live.introduced_users   = copy.introduced_users
```

Then reconcile `user_introduction` correctness on `new_arrivals` —
the same refresh contract from
[Refresh during compression](#refresh-during-compression) applied to
the post-snapshot range. For each distinct `user_id` whose
`user`-kind message appears in `new_arrivals`:

- **`user_id ∈ live.introduced_users` already, with a `user_introduction`
  for them in `new_arrivals` before that message** — no-op
  (brand-new user introduced by ingest during compression;
  `user_introduction` already in place).
- **`user_id ∈ live.introduced_users`, no `user_introduction` in
  `new_arrivals`** — no-op (user was already introduced before
  snapshot; ingest correctly skipped insertion).
- **`user_id ∉ live.introduced_users`, `user_introduction` exists in
  `new_arrivals`** — add `user_id` to `live.introduced_users`.
  Brand-new user introduced during compression; the marker is
  already in place.
- **`user_id ∉ live.introduced_users`, no `user_introduction` in
  `new_arrivals`** — *the edge case.* This is a user who was in
  `removed_users` (so dropped from `copy.introduced_users` by
  transformation step 8) but whose new message arrived during
  compression while ingest still saw them as introduced (because
  `live.introduced_users` had not yet been overwritten and so ingest
  correctly skipped insertion). Build a fresh `user_introduction`
  from the just-updated `UserProfile`, insert it in `new_arrivals`
  immediately before this user's first `user`-kind message there,
  and add `user_id` to `live.introduced_users`.

The same code that implements the refresh in transformation step 8
should be reused for this scan; the only difference is the range it
operates on (`new_arrivals` here, copy's tail there).

### Post-apply invariant

For every distinct `user_id` whose `kind == "user"` message appears
in the tail of `live.messages` (anything after the last `summary`
block):

- `user_id ∈ live.introduced_users`, **and**
- a `user_introduction` for `user_id` precedes that user's first such
  message.

This is the acceptance criterion for the apply step. Any
implementation that satisfies it is correct, regardless of how the
work is divided between transformation-on-copy and merge-on-arrivals.

### Profile extraction details

Profile extraction is the part of the compression run that updates
`UserProfile` from what was said in the chunk. It is folded into the
same LLM call as summarisation (transformation step 3), and the
resulting deltas are applied in step 5.

#### Delta shape

The summariser's JSON envelope carries a `profile_updates` object
keyed by `user_id`:

```json
{
  "summary": "...",
  "topics": ["погода"],
  "profile_updates": {
    "<user_id_a>": {
      "preferred_name":           "...",                  // scalar, overwrite
      "location":                 "...",                  // scalar, overwrite
      "interests_to_add":         ["...", "..."],         // list, append
      "facts_to_add":             ["..."],                // list, append
      "skill_preferences_to_add": {                       // dict-of-list, append per skill
        "<skill_name>": ["...", "..."]
      }
    },
    "<user_id_b>": { ... }
  }
}
```

An empty `profile_updates: {}` is the expected output when the chunk
contained no clear profile-relevant signal. The summariser prompt
instructs the model to emit a field **only** when the chunk
contains explicit evidence — no inference, no guessing.

#### Scalar vs list vs dict-of-list semantics

`UserProfile` has three classes of field, each with its own update
rule:

- **Scalar fields** (`preferred_name`, `gender`, `location`,
  `timezone`, `occupation`) — overwrite. The LLM emits a scalar
  **only** when the chunk provides explicit, durable evidence of a
  new value; in that case the new value replaces the old. If the
  chunk indicates that the old value is no longer true ("I quit
  Yandex") without naming a replacement, the field is skipped
  entirely. Empty strings and `null` are forbidden as scalar
  values — erasure is never a compressor operation, only the
  explicit `update_profile` agent tool can clear a field.
- **List fields** (`interests`, `facts`) — **append only**. At
  compression time the LLM sees a single chunk and has no knowledge
  of what was previously known about the user, so a full
  replacement would silently wipe everything accumulated from past
  compressions. The delta uses distinct keys `interests_to_add` and
  `facts_to_add`, and `MemoryProvider` appends with case-insensitive
  deduplication against the existing list.
- **Dict-of-list field** (`skill_preferences`) — **append per
  skill**. Shape:

  ```python
  skill_preferences: dict[str, list[str]] = {}
  # e.g. {"web_search":   ["weather forecast: accuweather.com",
  #                        "currency rates: ligovka.ru"],
  #       "text_to_image": ["prefers anime style"]}
  ```

  The delta key is `skill_preferences_to_add` and has the same
  shape. For every `(skill_name, items)` entry, `MemoryProvider`
  appends `items` to `current.skill_preferences[skill_name]` with
  case-insensitive deduplication. Skill names are matched as-is
  against the open vocabulary used by `task_result` content; an
  unknown name simply creates a new bucket. Skill names are never
  removed.

The distinct key names (`interests_to_add` vs `interests`, etc.)
make the three semantics statically disjoint: no compression-time
delta can accidentally trigger a replace on a list/dict field.

#### `MemoryProvider.update_user_profile` extension

The current `MemoryProvider.update_user_profile(user_id, chat_id,
fields)` does `setattr` for any field present in `fields`. This is
correct for the existing `update_profile` agent tool, which acts
with full conversational context. It needs to be extended to also
recognise these compression-time keys:

- `interests_to_add: list[str]` → append-with-dedup to
  `current.interests`.
- `facts_to_add: list[str]` → append-with-dedup to `current.facts`.
- `skill_preferences_to_add: dict[str, list[str]]` → for each
  `(skill, items)`: append-with-dedup to
  `current.skill_preferences.setdefault(skill, [])`.

The replace-style keys (`interests`, `facts`, `skill_preferences`)
stay available for the agent tool, so the extension is purely
additive — no existing call site breaks.

#### Ordering

Profile updates commit during transformation step 5, before the
`user_introduction` refresh in transformation step 8. The refreshed
`user_introduction` is therefore built from the just-updated
`UserProfile` and carries the new values (including
`skill_preferences`) immediately into the live tail. Any reordering
of these steps breaks the design.

#### Redaction

The redaction list from
[`doc/design/prompts/summarizer.md`](design/prompts/summarizer.md) (e-mails,
phone numbers, street-level postal addresses, IBAN / card / account
numbers, passwords, API tokens, secret keys) applies to every field
of `profile_updates`.

Crucially, redaction in `profile_updates` means **dropping the item
entirely**, never storing the literal token `[REDACTED]`. The
contrast with summary text is intentional: in prose, `[REDACTED]`
keeps the narrative intact ("she sent me her [REDACTED]
yesterday") — in a structured profile field, the same token is
useless noise, so the only acceptable behaviour is to skip the
item. This rule covers `facts_to_add` items, `skill_preferences_to_add`
items, and any scalar whose content would consist of redactable PII.
City and country are not redacted — they are profile-relevant and
expected in `location`.

### Lock model

A single per-`Conversation` `asyncio.Lock` serialises ingest and
compression. It is acquired in two short critical sections, both
holding for hundreds of microseconds:

- **Snapshot:** record `N_old`, `deep_copy(live)`, `snapshot_ts`.
  Three cheap operations.
- **Apply:** `live.messages = copy.messages + new_arrivals`, the
  merge of derived fields, the merge of `user_introduction` on
  `new_arrivals`, the post-apply Redis stash (which also persists
  `pending_vectorization` — see [Persistence
  flow](#persistence-flow)). Bounded sequential writes.

Everything between — the LLM call and the rest of the transformation
on `copy` — runs without the lock and never blocks ingest.

The same lock is shared with `Mind`'s ingest path: the ingest hook
that appends a message and updates `last_visible_at`,
`visible_messages`, and `introduced_users` runs under it as well, so
a snapshot can never observe a partially-applied ingest and an apply
can never race a concurrent ingest.

Sanity assertion under the apply lock: `len(live.messages) >= N_old`.
The append-only invariant of `live.messages` makes this trivially
true; the assertion is a tripwire for any future change that
introduces in-place message mutation or deletion.

### Persistence — separate concern

Vector-store externalisation of evicted `summary` blocks is decoupled
from the apply via the per-`Conversation` outbox
(`pending_vectorization`). The apply commits the outbox push together
with the inline state in one Redis stash; a separate background
sub-routine drains the outbox into Chroma. See [Persistence
flow](#persistence-flow) for the full design.

---

## Summary store

Per [variant C](#interaction-between-triggers), inline summary blocks
accumulate up to `MAX_SUMMARY_COUNT` and the rest are evicted from
`Conversation.messages`. Evicted blocks are persisted to an external
**summary store** so that history that no longer fits inline remains
recallable on demand. Summaries that are still inline are **not**
mirrored to the store: by construction the store and the inline tail
are disjoint, and recall therefore returns only what Yoda has
forgotten — see [Persistence flow](#persistence-flow).

### Stack

- **Vector DB:** [ChromaDB](https://www.trychroma.com/) in persistent
  mode (single directory under `data/`, SQLite + HNSW under the hood).
  Embedded in-process, no separate network service.
- **Embeddings:** `openai/text-embedding-3-small` via OpenRouter
  (1536d, multilingual in practice). Routed through OpenRouter to keep
  the secret-store surface minimal — the same API key as for chat
  completions. Direct OpenAI access can be swapped in later without
  changing call sites.
- **Operations:**
  - `EmbeddingProvider` — async wrapper around the embedding HTTP API.
  - `VectorProvider` — async wrapper around Chroma; owns collection
    lifecycle, the persistence directory, and the encryption hooks
    described below.

Both are Providers per the IODA convention.

### Collection model

**One collection per chat,** named `chat_{chat_id}`. Created lazily on
the first `persist_summary` for that chat. Cross-chat retrieval is
impossible by API construction, not by runtime filter — there is no
`chat_id` parameter on the search call, only a collection handle. A
buggy caller cannot accidentally query the wrong chat: the wrong
collection name simply does not exist or returns nothing.

Chroma scales to thousands of collections fine (each is a separate
SQLite table plus its own HNSW index). Per-collection volume is small
(see [Cost envelope](#cost-envelope) below).

### Record schema

Each summary block produced by compression becomes one Chroma record:

| field | type | source | role |
|---|---|---|---|
| `id` | str (sha256 hex) | `sha256(chat_id, snapshot_ts, chunk_start_message_id, chunk_end_message_id)` — see [Persistence flow](#persistence-flow) | primary key; deterministic so retries overwrite rather than duplicate |
| `document` | str | summary text | embedded; returned on retrieval |
| `embedding` | float[1536] | `EmbeddingProvider` | ANN search |
| `metadata.created_at` | float | snapshot timestamp = post-apply `last_compressed_at` | recency filters, time decay |
| `metadata.chunk_start_message_id` | int | first `message_id` in the compressed chunk | back-reference for debugging / future "expand" tools |
| `metadata.chunk_end_message_id` | int | last `message_id` in the compressed chunk | same |
| `metadata.chunk_visible_count` | int | mirrors the audit line in `Chat.history` | analytics |
| `metadata.participants` | str | comma-separated `user_id`s of `user`-kind authors in the chunk | filter for "what did Alice say about X" |
| `metadata.skills` | str | comma-separated names of skills invoked in the chunk | retrieval of past runs of the same skill |
| `metadata.topics` | str | comma-separated topic tags from the summarizer | semantic prefilter before ANN |

Lists are flattened to comma-separated strings because Chroma metadata
does not natively support arrays; filtering uses substring/`$contains`
predicates. This is a documented Chroma limitation, not a workaround
for buggy code.

### Summarizer envelope

One LLM call per compression run produces the summary text, topic
tags, and per-user profile-update deltas as a single JSON envelope.
`participants` and `skills` are **not** emitted by the LLM — the
compressor fills them in mechanically from the chunk after the call
returns. This both lightens the cognitive load on the summarizer and
removes a class of drift / out-of-sync failures (a closed skill
vocabulary in the prompt would inevitably diverge from the real tool
registry).

LLM-emitted envelope:

```json
{
  "summary":         "...",
  "topics":          ["погода", "выезд за город"],
  "profile_updates": { "<user_id>": { ... } }
}
```

Mechanically computed by the compressor after the call:

- `participants`: `sorted({m.user_id for m in chunk if m.kind == "user"})`.
- `skills`: the set of skill names parsed out of `task_result`
  records' `content` (see
  [Prerequisite: skill name in `task_result` content](#prerequisite-skill-name-in-task_result-content)).
  The vocabulary is open and always in sync with the live tool
  registry.

The merged record (LLM output + mechanical fields) is what the
[Record schema](#record-schema) consumes for the Chroma write.

The full prompt text — input format description, output rules,
redaction list, profile-update semantics, and a worked example —
lives in [`doc/design/prompts/summarizer.md`](design/prompts/summarizer.md).

Topic-tag extraction is part of the MVP, not deferred. Cost is one
extra JSON field in the summarizer's output — practically free — and
adding tags later would force a re-embed of every existing summary to
backfill metadata.

### Persistence flow

Summaries are written to the vector store **only when they are
evicted from the inline tail under `MAX_SUMMARY_COUNT` pressure** —
never at creation. By construction, the vector store and the inline
tail are disjoint: anything Yoda already sees in context is not
duplicated in retrieval results, and the agent does not need a
deduplication step against inline content. Recall semantics become
"return what has been forgotten", not "return whatever matches".

Externalisation uses the **transactional outbox** idiom, with the
outbox kept on the `Conversation` itself
(`pending_vectorization`, see [Conversation state
fields](#conversation-state-fields)) so that the apply commit and
the outbox push are persisted atomically in one Redis stash write.
Compression therefore never blocks on, never fails because of, and
never has to be rolled back due to vector-store availability.

#### Compression-side push

When [Compression apply](#compression-apply) evicts the oldest
`summary` block(s) from the inline tail under `MAX_SUMMARY_COUNT`
pressure, those blocks are appended to
`copy.pending_vectorization` (transformation step 7). The graft +
merge that commits the apply also persists
`pending_vectorization` via the post-apply stash — see [Lock
model](#lock-model). The compression run then returns success,
regardless of whether the vector store is reachable.

#### Outbox flush

`Maintenance.flush_summary_outbox` runs once per Maintenance tick
(default 1 hour, configured at `mind.maintenance.tick_minutes`, the
same base period as compression — see [Single ticking
loop](#single-ticking-loop)). On each tick, it scans Conversations
with non-empty `pending_vectorization` and for each one, in FIFO
order:

1. `EmbeddingProvider.embed_batch(texts)` produces vectors for the
   pending summaries.
2. `VectorProvider.persist_summaries(chat_id, records)` writes them
   to Chroma.
3. On success, the corresponding entries are removed from
   `pending_vectorization` (atomically, via the same Conversation
   stash mechanism that the compression apply uses).
4. On failure, the entries stay in `pending_vectorization`; the
   next tick retries.

#### Deterministic record id

Each Chroma record uses a deterministic identifier:

```
record.id = sha256(
    chat_id, snapshot_ts,
    chunk_start_message_id, chunk_end_message_id
)
```

If a flush attempt half-succeeds — embedding done, Chroma write
failed at the network layer but actually landed — the next retry
overwrites the same record instead of inserting a duplicate. The
outbox flush is therefore safely idempotent at the cost of one extra
embedding call on retry (not free, but cheap and bounded).

#### Outbox health threshold

When any single Conversation accumulates more entries in
`pending_vectorization` than
`mind.memory.chat_compression.outbox_health_threshold` (default
`10`), `flush_summary_outbox` logs a warning per tick. This signals
a sustained embedding-API outage or a Chroma misconfiguration that
needs operator attention. There is no automatic drop policy — the
entries are recoverable and can be flushed once the underlying
problem is fixed.

#### Recall during the flush window

A summary that has been evicted from inline but not yet flushed to
Chroma is invisible to `recall_conversation` for up to one tick
(currently 1 hour). This is acceptable: the recall use case is
"remember conversations from days or weeks ago", not "from minutes
ago". The window is bounded by the flush period, which can be
tightened independently of the compression period if observed lag
ever becomes a problem.

#### Crash recovery

Because the outbox lives on `Conversation`, the apply commit and the
outbox push share a single Redis stash and are therefore atomic
together. On restart after a crash:

- If the stash had succeeded → apply and outbox push are both
  durable; flush picks up where it left off.
- If the stash had not yet succeeded → neither apply nor outbox
  push is persisted; the conversation reverts to its pre-snapshot
  state. The next compression run reattempts the same chunk. With
  deterministic record id (above), any half-completed Chroma write
  from a previous attempt is overwritten cleanly.

### Recall path

Retrieval is exposed as an **agent skill**, not as a built-in `Mind`
mechanism:

- Skill name: `recall_conversation(query: str, k: int = 5)`.
- Implementation: `EmbeddingProvider.embed(query)` →
  `VectorProvider.search(chat_id, query_embedding, k, where=optional_filters)`
  → top-K summaries returned to the agent as a system message.
- Available filters on the agent side: `participants`, `skills`,
  `topics`, `created_at` range. The agent decides which to use based
  on the user's prompt.

Yoda herself does not invoke recall on every turn; her chat replies
are formed from the inline tail and inline summaries only. Recall
fires only when the agent receives a task that explicitly needs older
context, e.g. "помнишь, мы обсуждали…".

Retrieved summaries are **not** promoted back into the inline summary
list. By the time the agent finishes the recall task, the retrieved
text already lives in the conversation as the `task_result` content
of the `recall_conversation` invocation, so Yoda sees it for the
current turn and the next several turns until that chunk is
compressed — no extra mechanism needed for the common case. Explicit
promotion into the inline summary list would break the load-bearing
chronological-order invariant of inline summaries (which FIFO
eviction, system-prompt rebuild and future readers all depend on)
for negligible token savings on what is in practice a cold path. If
telemetry later shows recurring follow-up recall patterns within
short windows, the right fix is an out-of-band in-process LRU keyed
by `summary_id`, not promotion into `Conversation.messages`.

### Security baseline

- **Chat isolation** — by collection (see above). No `VectorProvider`
  codepath accepts a query without a `chat_id`-scoped collection
  handle.
- **No raw user text in summaries** — already a property of
  summarisation by construction, but reinforced in the summarizer
  prompt with explicit redaction rules: e-mails, phone numbers,
  IBAN / card numbers, street-level postal addresses and similar PII
  are replaced with the literal token `[REDACTED]` in summary prose
  and **dropped entirely** from structured `profile_updates` fields
  (see [Profile extraction details / Redaction](#redaction)).
  User-typed URLs are kept verbatim because [agent-result
  fidelity](#single-summary-per-run-default) needs them; the operator
  accepts this trade-off.
- **At-rest encryption (baseline)** — the Chroma persistence directory
  is expected to live on a volume-encrypted partition (LUKS or
  equivalent). Configuration concern, no code.
- **Application-level encryption (hooks only)** — `VectorProvider`
  exposes `encrypt(plaintext) -> ciphertext` and `decrypt(ciphertext)
  -> plaintext` hooks around the `document` field. Default
  implementations are identity functions; AES-GCM with a key from
  settings can be wired in later without touching call sites.
  Embeddings are not encrypted (that would defeat retrieval); the
  operator accepts the residual risk of embedding-inversion research
  attacks.

### Cost envelope

| line | rough order |
|---|---|
| Disk | ~3–5 KB per record (text + 1536d float32 + metadata + index entry); 10K summaries ≈ 30–50 MB |
| RAM | HNSW index per collection, well under 10 MB for typical chat volumes |
| Embedding API | ~500 input tokens per summary → ~$0.00001 per record at `text-embedding-3-small` rates; recall queries are short, similar order |
| LLM tag extraction | absorbed into the summarizer call, no separate cost |

These numbers are non-binding; they confirm by orders of magnitude
that the design fits a single-VPS deployment, not specific budgets.

---

## Maintenance integration

Compression and other periodic background work live in a new
`Maintenance` integration. Initial sub-routines:
- `reconcile_active_jobs` — currently the `periodic_job_cleanup` closure
  in `yoda/yoda_chat_bot.py`;
- `compress_conversations` — this design;
- `flush_summary_outbox` — drains `Conversation.pending_vectorization`
  into Chroma, see [Persistence flow](#persistence-flow).

### Wiring

`Maintenance` is constructed in `yoda/yoda_chat_bot.py:main()` like any
other Integration, with dependencies on `storage_api`, `scheduler_api`,
`memory_provider`, `language_provider`, `embedding_provider`,
`vector_provider`, and any other Operations its sub-routines need. It exposes three handles to the wiring file:

- `run_initial_pass()` — called from `on_app_start` after state
  restoration; performs one-shot work that previously lived inline in
  `main()` (currently: the initial `reconcile_active_jobs` call).
- `start()` — installs the periodic loop.
- `stop()` — cancels the loop and awaits its task; called from
  `on_post_stop`.

This pulls the following out of `yoda_chat_bot.py:main()`:
`reconcile_active_jobs` (module function), `periodic_job_cleanup`
(closure), `periodic_cleanup_holder` and the cancel block in
`on_post_stop`, the initial reconciliation in `on_app_start`, and the
`asyncio.create_task(periodic_job_cleanup())` line.

`cleanup_job_metadata` (the per-job scheduler callback) **stays in the
wiring file** — it is a one-line infrastructure callback, not a routine.

### Single ticking loop

`Maintenance` runs **a single periodic loop**, not one task per
sub-routine. The loop ticks at a base period equal to the smallest
period needed by any sub-routine — currently 1 hour (compression),
configured at `mind.maintenance.tick_minutes`. On each tick the loop
decides which sub-routines are due:

- `compress_conversations` — every tick;
- `flush_summary_outbox` — every tick (independent of compression in
  the loop, to allow tightening its period later without touching
  compression);
- `reconcile_active_jobs` — every 24 ticks (≈ daily, matching today's
  behaviour).

This requires sub-routine periods to be integer multiples of the base
tick. Both current sub-routines fit cleanly. Any future sub-routine
either fits the multiple-of-base rule or forces a base-period rethink —
both options are explicit, no ambiguity.

---

## Prior art

Conversational long-term memory is a heavily explored area; this design
overlaps significantly with mainstream patterns. The table below
captures the overlap explicitly so future contributors don't relitigate
"are we reinventing the wheel?".

| concern                           | LangChain¹ | LlamaIndex² | MemGPT / Letta            | Mem0                        | Yoda                                                |
| --------------------------------- | ---------- | ----------- | ------------------------- | --------------------------- | --------------------------------------------------- |
| compression trigger               | token budget | token budget | token budget            | n/a (facts-focused)         | size-trigger (token budget) **+** timeout-trigger (activity) |
| summary shape                     | one rolling summary | one rolling summary | "archival memory" entries | per-fact records         | multiple parallel summary blocks (variant C)        |
| retrieval                         | n/a        | over messages | explicit `recall` tool   | similarity over facts       | Chroma per-chat collection over summary blocks, agent skill `recall_conversation` |
| fact / profile extraction         | no         | no           | partial (core memory)    | yes (primary feature)       | yes (during compression)                            |
| multi-user / group chats          | no         | no           | no                       | partial                     | yes (`user_introduction` lazy injection)                  |
| visibility / kind distinction     | no         | no           | partial (system vs msg)  | n/a                         | yes (gap detection on visible only)                 |
| activity-aware timing             | no         | no           | no                       | no                          | yes (quiet-for-N-runs)                              |

¹ `ConversationSummaryBufferMemory`.
² `ChatSummaryMemoryBuffer`.

**Where Yoda follows the standard** (and should not redesign):
- vector store + embeddings as the long-term substrate for summary
  retrieval;
- summarisation prompt patterns ("preserve facts verbatim, compress
  narrative") — to be borrowed from Mem0 / MemGPT prompt designs rather
  than authored from scratch;
- sliding window for the recent live tail;
- profile / fact extraction during compression — the Mem0 prompt family
  is a strong starting reference.

**Where Yoda is custom** (and where the design effort is warranted):
- the **two-trigger** model and especially the firing logic of the
  timeout-trigger — activity-aware, not budget-aware;
- **kind / visibility / activity** as first-class concepts driving
  boundary decisions;
- **group-chat dynamics** — `user_introduction` lifecycle, lazy profile
  injection, refresh-at-compression;
- **variant C** — multiple stable summary blocks coexisting, never
  re-summarised.

The custom parts follow from product specifics: Yoda is a multi-user
Telegram presence with tools, scheduler and emotional state, not a 1:1
chat agent. Adopting an existing memory framework wholesale is not
expected to pay off — the standard parts are best assembled from
primitives (vector DB SDK, embedding API, prompt patterns) without
taking on a heavy framework dependency.

---

## Open questions

None outstanding at design level. Future questions will accumulate
here as implementation surfaces them.
