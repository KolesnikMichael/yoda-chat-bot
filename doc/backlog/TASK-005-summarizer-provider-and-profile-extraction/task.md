---
id: TASK-005
title: "summarizer provider and profile extraction"
status: todo
priority: high
size: M
created: 2026-06-09
updated: 2026-06-09
tags:
  - chat-context
---

# TASK-005: summarizer provider and profile extraction

## Description

Implement the summarisation unit as a self-contained Operation, decoupled from the apply mechanics so it can be developed and tested against a fake LLM: a `SummarizerProvider` that runs one LLM call per chunk and parses the JSON envelope (`summary`, `topics`, `profile_updates`), the mechanical computation of `participants` and `skills` from the chunk, and the application of `profile_updates` deltas through `MemoryProvider.update_user_profile`. This pulls the LLM/profile concern out of the apply pipeline (TASK-006), shrinking the program's largest task and giving the riskiest model interaction its own test surface.

## Master design

- [[chat_context_management#Summarizer envelope]]
- [[chat_context_management#Profile extraction details]]
- [[chat_context_management#Record schema]] (the mechanical fields half)
- [[design/prompts/summarizer|summarizer prompt]]

## Program

Part of the Chat Context Management chain — see the program map in [[main#Chat Context Management]].

## Scope boundary

**In scope:**
- `SummarizerProvider` (IODA Provider, depends only on the language API): `summarise(chunk)` runs one LLM call on a stripped chunk → parse and validate the envelope (`summary`, `topics`, `profile_updates`), per [[design/prompts/summarizer|summarizer prompt]]
- Mechanical post-call fields: `participants = sorted({m.user_id for m in chunk if m.kind == "user"})`; `skills` parsed from `task_result` content (relies on TASK-000's `Tools used: …`)
- Merge LLM output + mechanical fields into the complete summary record consumed by the Record schema
- Parse and **return** the per-user `profile_updates` deltas (scalar / list / dict-of-list shapes), applying the redaction rules (drop redactable items). The provider does **not** call `MemoryProvider` — Provider-to-Provider is forbidden by IODA; the apply Integration (TASK-006) invokes `update_user_profile` with these deltas in the correct order
- Tests against a fake LLM façade: envelope parsing/validation, empty `profile_updates`, redaction, mechanical participants/skills, returned delta shapes

**Out of scope:**
- snapshot / transform / apply / graft+merge (TASK-006)
- calling `MemoryProvider.update_user_profile` and the step-5 ordering before the `user_introduction` refresh (orchestrated by TASK-006)
- the delta-key application semantics **inside** `MemoryProvider.update_user_profile` (TASK-000)
- `user_introduction` strip/refresh
- inline `summary` blocks, eviction, audit entry, triggers
- Chroma / embeddings

## Related documents

- [[requirements]] — requirements and acceptance criteria
- [[design]] — architectural solution
- [[plan]] — implementation plan
- [[chat_context_management]] — master design
- [[main#Chat Context Management]] — program map and position in the chain

## Dependencies

- Depends on:
  - [[TASK-000-compression-prerequisites/task|TASK-000]] (delta keys, `skill_preferences`, skill names in `task_result`)
  - [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]] (`Message.kind` to identify `user` and `task_result` messages)
- Blocks: [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]]

## Notes

Extracted from the former monolithic apply task to de-risk it. The summariser shares none of the apply invariants, so it ends green on its own and TASK-006 can build against it (or a fake of it).
