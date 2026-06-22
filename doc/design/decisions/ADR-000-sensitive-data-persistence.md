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

Yoda processes private Telegram conversations: user messages, agent outcomes, and derived knowledge. Every byte written to disk, a vector database, or logs expands the breach and compliance surface. Operators run on a single VPS with embedded stores (Redis, Chroma) — there is no separate secure analytics warehouse for raw chat.

Chat context management (compression, profile extraction, vector recall) tempts designs that persist user replicas in more places (outbox flush timing, audit trails, durability after every apply). Without an explicit rule, incidental persistence creeps in through implementation convenience.

**Forces:**

- Users reasonably expect chat content not to outlive the running process except where the product clearly needs it.
- The bot must survive **graceful restarts** without wiping active conversations from memory.
- Long-term memory (summaries, profiles) must remain useful without storing verbatim user messages in cold storage.
- Debuggability before production deploy still needs visibility into message flow.

## Decision

**Do not persist replicas of user messages** except the conversation stash used to survive a **planned restart**.

All other design decisions (compression apply, Chroma, profiles, logging, agent tools) must respect this rule. Privacy and security are **best effort**, not a formal certification — but persistence minimization is the default bar.

### Affected subsystems

- **Process memory** — primary live copy of conversation content; expected.
- **Conversation stash** — sole at-rest exception for user message replicas; graceful shutdown only, not a general durability path.
- **Chroma** — derived narratives and topics only; no verbatim user lines.
- **User profiles** — structured facts and preferences only; no message replicas.
- **Logging** — no user replicas at info or above in production; debug only for pre-production troubleshooting.

## Rejected options

- **Durable chat log (Redis/DB for all messages)** — violates privacy posture; any backup or store leak exposes full message history; conflicts with persistence minimization.
- **In-memory only (no checkpoint)** — strongest privacy, but any restart drops in-flight conversations; unacceptable for a long-running Telegram bot.

## Consequences

**Positive:**

- Clear gate for reviews: “does this write user replicas to disk?”
- Cold path stays bounded: Chroma holds forgotten summaries, not a duplicate chat log.
- Task requirements can drop “post-apply Redis stash” criteria that contradicted this policy.

**Negative / accepted trade-offs:**

- **Crash before graceful shutdown** loses in-memory conversations (stash not updated).
- **`pending_vectorization`** and post-compression inline state survive only until the next successful `save_conversation_stash` on shutdown — a sustained outage before graceful stop may lose evicted summaries not yet flushed to Chroma.
- Profile and Chroma writes remain sensitive derived data — redaction is best effort, not a guarantee against model mistakes.

**Neutral:**

- `Chat.history` audit entries describe compression **events** (ids, counts, timestamps), not message bodies.
- In-memory `summary` blocks in the live tail are narratives, not raw user replicas; they still exist in RAM and in the restart stash.
- Out of scope: Telegram and LLM provider retention, legal hold/export/moderation workflows (would need a separate ADR).

## Related documents

<!-- Same level or higher only: ADR, Policy, Strategies, etc. Not epic/task design.md -->
