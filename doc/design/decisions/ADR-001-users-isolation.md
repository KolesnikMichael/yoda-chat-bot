---
id: ADR-001
title: "users isolation"
date: 2026-06-18
created: 2026-06-18
tags:
  - privacy
  - security
---

# ADR-001: users isolation

## Context

Yoda serves many Telegram users from one deployment. Each user reasonably expects that other bot users cannot see their identity metadata, read their conversations or profiles, or use Yoda to reach them — except where they already share a group chat.

**Scope of isolation:**

- **Direct access** — ids, avatars, names, chat replies, profiles, activity.
- **Indirect access** — using Yoda as a messenger (“tell user X…”) or data retriever (“what did user Y say in chat Z?”).

**Forces:**

- A single-process bot with shared stores (Redis, Chroma) makes accidental cross-user reads easy without explicit boundaries.
- Agent skills and tools can amplify leakage if they accept arbitrary `user_id` / `chat_id` targets.
- Group chats are a legitimate multi-user surface; isolation must not break shared context there.
- Prompt instructions alone are not a reliable enforcement layer.

## Decision

**Enforce user isolation by architecture** — data model, storage scoping, and skill/tool contracts — not by output filtering or LLM politeness.

One user must not discover, read, or act on another user's private data through Yoda. The only intentional multi-user context is a **shared group chat** the requester participates in; even there, access stays limited to that chat's participants and content.

### Affected subsystems

- **Conversation and chat state** — scoped per chat; no cross-chat reads in normal operation.
- **User profiles** — scoped per user within a chat; not a global user directory.
- **Vector recall** — chat-scoped collections only; no cross-chat retrieval.
- **Agent skills and tools** — must not target arbitrary users or expose other users' private stores.

## Rejected options

- **Prompt-only guardrails** — does not block wrong data from being loaded; indirect access and model mistakes remain possible.
- **Runtime output filters** — fragile last line of defense; hard to audit and easy to bypass as features grow.

## Consequences

**Positive:**

- Clear review gate: “does this API, key, or tool cross user/chat boundaries?”
- New persistence and recall designs can cite a single isolation rule alongside [[ADR-000-sensitive-data-persistence]].

**Negative / accepted trade-offs:**

- No “message any user” or global operator UX without revisiting this ADR.
- Group-chat features must still respect participant boundaries — shared context is not a licence to leak private chats or profiles from elsewhere.

**Neutral:**

- Telegram's own retention and visibility are outside Yoda's trust boundary.
- Server operators with infrastructure access are out of scope.

## Related documents

<!-- Same level or higher only: ADR, Policy, Strategies, etc. Not epic/task design.md -->

- [[ADR-000-sensitive-data-persistence]]
