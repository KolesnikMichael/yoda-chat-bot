---
id: ADR-001
title: "users isolation"
date: 2026-06-18
created: 2026-06-18
tags: []
---

# ADR-001: users isolation

## Context

The chat bot users cannot see other chat bot users (ids, avatars, metainformation), cannot access other users' data (chat replies, profiles, activity), and cannot interact with each (send messages using their user_id, chat_id, or usernames) other than by participating in shared group chats. This covers both direct and indirect access (that is using Yoda as a messenger or data retriever). 

This isolation should be by all possible means enforced by architecture (data model, separation of concerns, Yoda skills/tools design) rather than runtime filters.

## Options

### Option 1: Name

Description.

**Pros:**
- ...

**Cons:**
- ...

---

### Option 2: Name

Description.

**Pros:**
- ...

**Cons:**
- ...

## Decision

**Option N chosen.**

Rationale: why this option in this context.

## Consequences

**Positive:**
- ...

**Negative / accepted trade-offs:**
- ...

**Neutral:**
- ...

## Related documents

<!-- Tasks, designs, or other ADRs this decision relates to -->
- [[]]
