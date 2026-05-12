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
SIZE_TRIGGER_THRESHOLD` (default `300`, exact value TBD). Visible-only
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

N is a setting with **two separate values** — one for private chats, one
for group chats. Both default to `8`. The settings section name in
`settings.json` is TBD.

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
will therefore explicitly instruct the model to preserve such values
**verbatim** in the summary, separately from the narrative compression of
the surrounding dialogue. Detailed prompt design is deferred.

#### Constants and entry threshold

- **`MIN_CHUNK_LENGTH = 30`** — the same constant serves two roles by
  design: minimum visible length of the live tail (so Yoda always
  retains roughly the screen of recent messages a returning user
  sees), and minimum visible length of a compressed chunk (so we never
  spend an LLM call on a chunk smaller than what humans themselves
  would still recall in detail).
- **`GAP_TO_TRIGGER_RATIO = 0.5`** — single tunable that ties gap
  detection to the silence threshold. `GAP_THRESHOLD` is derived
  per-chat-type as `N(chat_type) * GAP_TO_TRIGGER_RATIO`, i.e. 4h for
  the default `N = 8`. Tying the two together guarantees by
  construction that an internal gap can never be longer than the
  silence required to fire the trigger, and that groups with larger
  `N` (time-zone-spread) automatically get proportionally larger gap
  thresholds, matching their slower natural rhythm. The ratio is a
  named constant rather than two independent settings to keep the
  invariant `GAP_THRESHOLD < N` non-optional.
- **`MAX_SUMMARY_COUNT = 30`** — hard cap on the number of `summary`
  blocks coexisting inline in a single `Conversation`. When a
  compression run would push the count above the cap, the same atomic
  apply that inserts the new summary also evicts as many oldest
  `summary` blocks from the head of `Conversation.messages` — typically
  one in, one out. Eviction is FIFO by position, which equals FIFO by
  creation order since variant C never reorders summaries. Without this
  cap, variant C would let the prompt grow unboundedly on long-lived
  chats; with it, the inline conversation lives in a known envelope.
  Evicted summary blocks remain available through the externalised
  summary store (see open question on summary retrieval) — eviction
  here is purely about inline footprint, not data loss.

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

The pipeline runs strictly in this order, atomically with summary
application:

1. Identify the chunk via [window selection](#window-selection-algorithm).
2. Strip every `user_introduction` message from the chunk; remember the set
   `removed_users` of user_ids whose marker was stripped. The
   `user_introduction` markers do **not** participate in summarisation: they
   are projected metadata, not content, and the source of truth is
   `UserProfile` itself.
3. Run summarisation on the stripped chunk.
4. Run profile extraction on the chunk and update `UserProfile` for
   each author of compressed `user`-kind messages.

   *Invariant:* the set of compressed `user`-kind authors equals
   `removed_users` exactly, by construction of insertion (every
   `user_introduction` is inserted directly before that user's first reply,
   so it shares chunk membership with that reply). The implementation
   should assert this invariant.

5. For each `user_id ∈ removed_users`, scan the tail (the portion of
   the copy's `messages` after the just-inserted summary) for that
   user's first `user`-kind message:
   - **Found** → build a fresh `user_introduction` from the just-updated
     `UserProfile` and insert it immediately before that message;
     keep `user_id` in the copy's `introduced_users`.
   - **Not found** → drop `user_id` from the copy's
     `introduced_users`. The user will be re-introduced lazily on
     their next message via the ingest rule above.

   This scan only sees the snapshot tail. Messages that arrived on
   the live conversation during the LLM call are reconciled
   separately at apply time — see
   [Compression apply](#compression-apply).
6. The user_introduction work above is one phase of the larger compression
   run. Replacing the chunk with the new summary, FIFO eviction
   under `MAX_SUMMARY_COUNT`, decrement of `visible_messages`,
   update of `last_compressed_at`, the audit line on `Chat.history`,
   and the commit back to the live conversation are all described in
   [Compression apply](#compression-apply).

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
2. Strip `user_introduction` markers from the chunk into `removed_users`
   ([`user_introduction` lifecycle](#refresh-during-compression) step 2).
3. Summarise the stripped chunk (lifecycle step 3).
4. Profile extraction on the chunk; `UserProfile` updates are
   persisted to the user-profile store directly — they do not live
   on `copy` (lifecycle step 4).
5. Replace the chunk in `copy.messages` with the new `summary`
   block.
6. If the resulting `summary`-block count exceeds
   `MAX_SUMMARY_COUNT`, FIFO-evict the oldest summary block(s) from
   the head of `copy.messages` — same number as added in this run,
   typically one — and append each evicted block to
   `copy.pending_vectorization` so that the externalised summary
   store eventually picks it up via [Persistence
   flow](#persistence-flow).
7. `user_introduction` refresh on `copy`'s tail (lifecycle step 5). The
   scan sees only the snapshot tail; new arrivals are handled in the
   merge phase below.
8. Update derived fields on `copy`:
   - `copy.visible_messages -= chunk_visible_count`;
   - `copy.last_compressed_at = snapshot_ts`;
   - `copy.introduced_users` was already mutated by step 7.
9. Append the audit line to `copy.chat.history`:
   `"Compressed <n_visible> messages into 1 summary on <iso8601>"`,
   with `<n_visible> = chunk_visible_count` and
   `<iso8601> = snapshot_ts`. The same form is used by the
   size-trigger so future audits do not need a parser.

After step 9, `copy` is a valid `Conversation` representing the state
the live conversation **would** have ended up in had no concurrent
ingest happened.

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
essentially `user_introduction` lifecycle step 5 applied to the
post-snapshot range. For each distinct `user_id` whose `user`-kind
message appears in `new_arrivals`:

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
  transformation step 5) but whose new message arrived during
  compression while ingest still saw them as introduced (because
  `live.introduced_users` had not yet been overwritten and so ingest
  correctly skipped insertion). Build a fresh `user_introduction` from the
  just-updated `UserProfile`, insert it in `new_arrivals` immediately
  before this user's first `user`-kind message there, and add
  `user_id` to `live.introduced_users`.

The same code that implements lifecycle step 5 should be reused for
this scan; the only difference is the range it operates on
(`new_arrivals` here, copy's tail there).

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

### Tag extraction

`participants`, `skills`, and `topics` are produced **by the same LLM
call** that writes the summary itself. The summarizer prompt asks for a
JSON envelope:

```json
{
  "summary": "...",
  "participants": [user_id, ...],
  "skills": ["weather", "calendar"],
  "topics": ["погода", "выезд за город"]
}
```

`participants` is also computable mechanically from the chunk; the
LLM-reported value is cross-checked against the mechanical one and any
mismatch is logged (the LLM side is the suspect side). `skills` and
`topics` are LLM-only.

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
`copy.pending_vectorization` (transformation step 6). The graft +
merge that commits the apply also persists
`pending_vectorization` via the post-apply stash — see [Lock
model](#lock-model). The compression run then returns success,
regardless of whether the vector store is reachable.

#### Outbox flush

`Maintenance.flush_summary_outbox` runs once per Maintenance tick
(1 hour, the same base period as compression — see [Single ticking
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

When any single Conversation accumulates **more than 10 entries** in
`pending_vectorization`, `flush_summary_outbox` logs a warning per
tick. This signals a sustained embedding-API outage or a Chroma
misconfiguration that needs operator attention. There is no
automatic drop policy — the entries are recoverable and can be
flushed once the underlying problem is fixed.

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
context, e.g. "помнишь, мы обсуждали…". Whether retrieved summaries
should also be promoted back into the inline tail as a hit-cache (so
that immediately following turns see them without another retrieval)
is an open optimisation — see [Open
questions](#open-questions).

### Security baseline

- **Chat isolation** — by collection (see above). No `VectorProvider`
  codepath accepts a query without a `chat_id`-scoped collection
  handle.
- **No raw user text in summaries** — already a property of
  summarisation by construction, but reinforced in the summarizer
  prompt with explicit redaction rules: e-mails, phone numbers,
  IBAN/card numbers, postal addresses and similar PII are replaced
  with placeholders (`<redacted_email>`, `<redacted_phone>`, ...).
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
period needed by any sub-routine — currently 1 hour (compression). On
each tick the loop decides which sub-routines are due:

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

To be resolved in subsequent iterations:

- **Recall hit-cache promotion.** When the agent's
  `recall_conversation` skill returns a summary that was previously
  evicted from the inline tail, should that summary be temporarily
  re-inserted into the live tail (until it falls out again under
  ordinary `MAX_SUMMARY_COUNT` pressure) so that immediately following
  turns can use it without another retrieval round-trip? Cheap to
  implement, but interacts with the FIFO eviction order. Deferred
  until usage data shows whether it's worth it.
- **Summarizer prompt and redaction details.** Concrete prompt
  templates for the summarisation/tag-extraction LLM call, including
  the verbatim-preserve list (URLs, IDs, parameters from
  `task_result`), the redaction list (e-mails, phones, etc.), and
  how `participants/skills/topics` are formatted. Mem0 / MemGPT prompt
  patterns are the starting reference per [Prior art](#prior-art).
- **Profile / Chat metadata extraction during compression.** What is
  extracted, by which Operation, and how the system prompt is rebuilt
  afterwards. The `user_introduction` refresh path (lifecycle step 4)
  consumes whatever this extraction produces.
- **Settings section name** for the two `N` knobs in `settings.json`.
