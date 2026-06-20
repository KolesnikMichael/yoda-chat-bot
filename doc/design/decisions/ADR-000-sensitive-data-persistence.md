---
id: ADR-000
title: "sensitive data persistence"
date: 2026-06-17
created: 2026-06-17
status: draft
tags:
  - privacy
  - security
  - persistence
---

# ADR-000: sensitive data persistence

**Status:** draft — foundational policy; downstream designs and requirements must align with it.

## Context

Yoda processes private Telegram conversations: user messages, agent outcomes, and derived knowledge. Every byte written to disk, a vector database, or logs expands the breach and compliance surface. Operators run on a single VPS with embedded stores (Redis, Chroma) — there is no separate “secure analytics warehouse” to offload raw chat into.

The Chat Context Management program ([[chat_context_management]]) adds compression, profile extraction, and vector recall. Those features tempt designs that persist user replicas in more places (outbox flush timing, audit trails, “durability after every apply”). Without an explicit rule, incidental persistence creeps in through implementation convenience.

**Forces:**

- Users reasonably expect chat content not to outlive the running process except where the product clearly needs it.
- The bot must survive **graceful restarts** without wiping active conversations from memory.
- Long-term memory (summaries, profiles) must remain useful without storing verbatim user messages in cold storage.
- Debuggability before production deploy still needs visibility into message flow.

## Options

### Option 1: Durable chat log (Redis/DB for all messages)

Persist the full `Conversation.messages` list continuously or after every mutation.

**Pros:**

- Simple crash recovery; easy backup/restore.
- No ambiguity about when state is “committed”.

**Cons:**

- Violates privacy posture: user replicas live on disk for the lifetime of the deployment.
- Expands scope of any Redis/Chroma/backup leak to full message history.
- Conflicts with “best effort” minimization goal.

---

### Option 2: In-memory only (no checkpoint)

Never write `Conversation.messages` to external storage.

**Pros:**

- Strongest privacy: no user replicas at rest outside RAM.

**Cons:**

- Any restart (deploy, crash, OOM) drops in-flight conversations — unacceptable for a long-running Telegram bot.

---

### Option 3: In-memory primary + restart checkpoint only (chosen direction)

Treat user message replicas as **in-memory only** in normal operation. Allow **one** narrow exception: a conversation stash written for **graceful shutdown / restart**, not as a general durability or outbox mechanism.

**Pros:**

- Aligns persistence with actual product need (survive restart, not archival).
- Keeps cold-path stores (Chroma, profiles) limited to derived, redacted artefacts.
- Gives a single rule other ADRs and task requirements can cite.

**Cons:**

- Crash mid-session loses conversations not yet checkpointed (accepted).
- Compression apply and outbox state are durable only after the next graceful stash (accepted — see Consequences).
- Requires discipline: designs must not add “helpful” post-apply or per-tick stash writes without revisiting this ADR.

## Decision

**Adopt Option 3** as the project-wide rule:

> **Do not persist replicas of user messages** except the conversation stash used to survive a **planned restart**.

All other design decisions (compression apply, Chroma, profiles, logging, agent tools) must respect this rule. Privacy and security are **best effort**, not a formal certification — but persistence minimization is the default bar.

### Where user content may exist

| Surface | What is stored | User replicas? |
|---|---|---|
| **Process memory** (`Conversation.messages`) | Full live tail: `user`, `assistant`, `task_result`, `summary`, `user_introduction`, etc. | Yes — primary copy |
| **Conversation stash** (Redis key `conversation_stash`) | Serialised in-memory conversations at **graceful shutdown** (and restored once at startup) | Yes — **sole at-rest exception** |
| **Chroma** (summary store) | Narrative summary text, topic tags, mechanical metadata (`participants`, `skills`, chunk bounds) | No verbatim user lines; summariser prompt enforces narrative compression + `[REDACTED]` in prose |
| **User profiles** (Redis `user_profiles`) | Durable facts and preferences the user chose to share, plus skill-specific preference buckets | No message replicas; structured fields only; PII redaction drops items (see [[design/prompts/summarizer|summarizer prompt]]) |
| **Logs** | Operational metadata | No user replicas at **info** or above in production; message text / profile payloads only at **debug**, for pre-production troubleshooting |

### Rules by subsystem

1. **Chroma** — store only compressed **narratives** and **topics** (plus non-verbatim metadata needed for recall filters). Apply summariser redaction rules; never mirror the inline message list.
2. **User profiles** — store only **publicly shareable facts and preferences** relevant to future turns and skills (`interests`, `facts`, `skill_preferences`, scalars the user explicitly stated). Apply the same structured-field redaction as compression (`profile_updates` drops redactable items; no `[REDACTED]` tokens in profile fields).
3. **Logging** — in production configuration, **do not log user message text or profile snapshots** at info/warning/error. `logger.debug` may include truncated user content for local debugging before deploy; operators enable debug only in non-production.
4. **Conversation stash** — the **only** intentional persistence of full `Conversation.messages`. Written on **graceful shutdown** (`post_stop`), restored on startup, then the Redis key is removed (existing `MemoryProvider` contract). **Not** written after each compression apply, each ingest, or each Maintenance tick unless this ADR is explicitly revised.

### What this ADR does *not* cover

- Telegram’s own retention (messages exist on Telegram servers and client devices).
- LLM provider retention (API calls leave the trust boundary while the model runs).
- Legal hold, export, or moderation workflows — out of scope; would need a separate ADR.

## Consequences

**Positive:**

- Clear gate for reviews: “does this write user replicas to disk?”
- [[EPIC-001-chat-context-management/epic|EPIC-001]] cold path stays bounded: Chroma holds forgotten summaries, not a duplicate chat log.
- TASK requirements can drop “post-apply Redis stash” style criteria that contradicted this policy.

**Negative / accepted trade-offs:**

- **Crash before graceful shutdown** loses in-memory conversations (stash not updated).
- **`pending_vectorization`** and post-compression inline state survive only until the next successful `save_conversation_stash` on shutdown — a sustained outage before graceful stop may lose evicted summaries not yet flushed to Chroma (TASK-008 flush is best-effort after restart if stash still held them).
- Profile and Chroma writes remain sensitive derived data — redaction is best effort, not a guarantee against model mistakes.

**Neutral:**

- `Chat.history` audit entries describe compression **events** (ids, counts, timestamps), not message bodies — consistent with this ADR.
- In-memory `summary` blocks in the live tail are narratives, not raw user replicas; they still exist in RAM and in the restart stash.

## Related documents

- [[chat_context_management]] — compression, outbox, persistence flow (must be reconciled with this ADR; remove or correct any “post-apply stash” wording)
- [[design/prompts/summarizer|summarizer prompt]] — prose and `profile_updates` redaction
- [[EPIC-001-chat-context-management/epic|EPIC-001]] — chat context management program
- [[TASK-006-compression-apply-and-size-trigger/requirements|TASK-006 requirements]] — FR-12 stash criterion to align on review
- [[TASK-008-summary-store-and-outbox-flush/task|TASK-008]] — Chroma flush (derived data only)
