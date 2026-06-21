---
id: TASK-012
doc: requirements
updated: 2026-06-18
---

# TASK-012: memory provider cache ownership — Requirements

← [[task|Back to task]]

## Context

`MemoryProvider` stores live conversations in `_conversations: dict[str, Conversation]`. Keys use `MemoryCore.conversation_key(chat_id)` → `str(chat_id)` — sensible at the **stash wire** boundary (`conversations_to_stash_dict`), but invoked on every in-memory cache accessor.

### Cache CRUD trio (symmetric ceremony)

| Method | Effect | Core hop | External callers |
|--------|--------|----------|------------------|
| `get_conversation` | `dict.get` | `conversation_key` | `Mind` (4×), tests |
| `save_conversation` | `dict[key] = conv` | `conversation_key` | `Mind` (5×), `commit_compression`, tests |
| `forget_conversation` | `dict.pop` | `conversation_key` | `DeleteUserDataTool` |

All three are thin dict ops; Provider → Core for `str(chat_id)` is wire-convention leakage on the hot path.

### Mutation flow today

1. `Mind`: `get_conversation(chat_id)` → mutable reference (or `None`).
2. `append_*`: lock + `MemoryCore.add_conversation_line`; **no cache register**.
3. `Mind`: `save_conversation` — required for new chat, redundant for existing.
4. `commit_compression`: mutates `live` from `get_conversation` in place, then redundant `save`.
5. `DeleteUserDataTool`: Redis deletes + `forget_conversation(user_id)` for in-memory drop.

`append_*` accepts both `conversation: Conversation | None` **and** `chat_id` — sign that cache lookup ownership is split between caller and Provider.

### IODA framing

- **Not a layer violation:** Integration → Provider (`Mind` calling `get_conversation`) is valid IODA.
- **Encapsulation gap:** Integration and agent tools manage **cache object lifecycle** (get handle, save, forget) instead of Provider owning it under lock.
- **Leak risk:** `get_conversation` returns a **shared mutable reference** into `_conversations`; callers can mutate outside `append_*` / lock (fragile, not forbidden by IODA).
- **Tool orchestration:** `DeleteUserDataTool` is mini-Integration (storage + scheduler + `forget_conversation`); low-level `forget` could move behind a Provider-level GDPR helper.

### Naming tension

`save_conversation` sounds like persistence; `save_conversation_stash` is the Redis checkpoint. Easy to misread during compression / ADR reviews.

## Problem statement

| Issue | Detail |
|-------|--------|
| Register vs re-put | `save_conversation` conflates two cases; always called → redundant on hot path |
| CRUD exposed | `get` / `save` / `forget` are public infra; callers shouldn't need them for normal ingest |
| Core hop | `conversation_key` on every cache op; real value at stash serialize only |
| Handle passing | `Mind` threads `Conversation` through pipeline; could be `chat_id`-only |
| Forget symmetry | `forget_conversation` mirrors `save_conversation`; tool calls it after Redis `hdel` |

## Solution alternatives

Choose **one** (or hybrid) at design time; document rejected options in [[design]].

### Alternative A: Register inside Provider mutate methods

`append_*`, `commit_compression` end with private `_register(conversation)` under lock. Remove external `save` from `Mind` and redundant save from `commit_compression`.

| Pros | Cons |
|------|------|
| Provider owns cache after lock | Audit all mutation entry points |
| Fixes register-forget asymmetry partially | `get` / `forget` may still be public |

**Size:** S

### Alternative B: `dict[int, Conversation]` in Provider

In-memory `chat_id: int` keys; `str(chat_id)` only in Core at stash/Redis boundaries. Removes Core hop from get/save/forget.

| Pros | Cons |
|------|------|
| Drops ceremony on hot path | Type boundary at `restore_conversation_stash` / iter |
| Pairs well with A or E | Slight ripple in tests/fakes |

**Size:** S–M

### Alternative C: Rename only

`save_conversation` → `register_conversation` (or private `_register`). Document cache ≠ stash. Remove provable no-op saves.

| Pros | Cons |
|------|------|
| Minimal diff | Doesn't fix handle-passing or forget exposure |

**Size:** XS

### Alternative D: Hybrid A + C (default for register/save)

Register in mutators + rename. Recommended baseline for the save/register side.

**Size:** S

### Alternative E: Hide CRUD trio; `chat_id`-only public API

Make `get` / `save` / `forget` private (or test-only). Public surface: `append_*`, `commit_compression`, `iter_conversations`, and domain methods only. `Mind` passes `chat_id` — Provider resolves or creates `Conversation` under lock. `append_*` signature drops redundant `conversation` parameter (breaking change).

| Pros | Cons |
|------|------|
| Strongest encapsulation; fixes IODA smell | Largest API break; Mind + all tests |
| No mutable handle leak to Integration | Agent paths that need `Conversation` for routing must adapt |

**Size:** M

### Alternative F: High-level forget for GDPR path

Replace `DeleteUserDataTool` → `forget_conversation` with `MemoryProvider.drop_in_memory_conversation(chat_id)` (private) or fold into `delete_user_data`-shaped Provider method. Tool stops calling raw cache CRUD.

| Pros | Cons |
|------|------|
| Symmetric with hiding `save` | Scope creep if full GDPR moves to Provider |
| Tool stays storage-focused | |

**Size:** XS (if F alone); included in E or D

### Recommended design-review combos

| Combo | When |
|-------|------|
| **D + B** | Pragmatic: register + rename + int keys |
| **D + E + F** | Thorough: full cache encapsulation |
| **C only** | Doc pass / rename if no bandwidth |

## Functional requirements

### FR-1: No redundant cache writes on the hot path

Mutating an existing in-memory conversation does not require an external `save`/`register` from `Mind`.

**Acceptance criteria:**
- [ ] `Mind` has no post-`append_*` `save`/`register` (or documented exceptions in [[design]])
- [ ] New-chat path registers without caller ceremony
- [ ] `commit_compression` does not no-op re-put unless design keeps it explicitly

### FR-2: Durability boundary unchanged

`save_conversation_stash` unchanged per [[ADR-000-sensitive-data-persistence]].

**Acceptance criteria:**
- [ ] No new stash writes from append/compression paths
- [ ] Full suite green

### FR-3: CRUD trio policy documented and enforced

Design chooses visibility for `get` / `save` / `forget` and `conversation_key` placement.

**Acceptance criteria:**
- [ ] [[design]] records: public / private / removed per method
- [ ] `conversation_key` not called from Provider cache accessors on hot path **or** rationale documented if kept
- [ ] `DeleteUserDataTool` updated if `forget_conversation` is hidden (Alternative F)

## Constraints & assumptions

- **Constraint (IODA):** Core stays pure — no writes to `_conversations`.
- **Constraint:** No new top-level Integration class.
- **Assumption:** Low urgency; correct behaviour today.

## Out of scope

- Stash schema, compression, lock model
- Persisting conversation on every message (ADR-000)
- Full relocation of `DeleteUserDataTool` Redis orchestration into Provider (only in-memory forget piece in scope for F)
