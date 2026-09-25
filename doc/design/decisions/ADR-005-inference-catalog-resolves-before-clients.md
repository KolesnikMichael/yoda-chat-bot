---
id: ADR-005
title: "inference catalog resolves before clients"
date: 2026-09-25
created: 2026-09-25
tags:
  - inference
  - ioda
  - settings
---

# ADR-005: inference catalog resolves before clients

## Context

Chat, cognition, the agent, the summarizer, vision, embeddings, and live eval
each need a backend, credentials, and a model name. Those used to live in
scattered settings fields, and a Provider both read configuration and held the
HTTP client.

Under IODA a Provider must not own config policy or call another Operation.
Fail-fast on a bad profile or provider reference has to happen before any
network client exists. Later work (live-eval improvements, new backends) must
extend one settings contract rather than grow new credential fields.

**Forces:**

- Profile and provider validation is pure logic and belongs in a Core.
- Constructing HTTP clients is a side effect and belongs in an Integration.
- Providers stay testable with a façade and a resolved model name, without
  profile ids or API keys.
- One consumer's model choice must not force the others.

## Decision

Resolve the inference catalog in a pure Core. Integrations (`main`, the
live-eval CLI) build one chat or embeddings façade per consumer from that
result and pass the façade plus the resolved model name into existing
Providers. Providers never see profile ids or API keys. Changing a consumer's
model id retargets that consumer.

The catalog lives next to the chat and embeddings façades. The Core still
depends only on Data and does no I/O. Only the Integration that builds clients
imports those façades.

### Affected subsystems

- **Startup and live eval** — resolve the catalog, construct façades, inject them.
- **Language, summarizer, vision, embeddings** — accept a resolved model name and a façade; do not read the catalog.
- **Later backends** — extend the catalog and the client factory; do not add credential fields on consumers.

## Rejected options

- **Providers accept a profile id plus the catalog** — puts config policy and
  credentials in Providers and couples them to the settings shape.
- **Branch inside a Provider on a backend name and import both clients** —
  makes the Provider depend on concrete façades and hides the Integration's
  wiring job.

## Consequences

**Positive:**

- Invalid catalog entries fail before any client exists.
- Chat and the agent can use different profiles without sharing a client.
- New backends extend one catalog instead of new per-consumer credential fields.

**Negative / accepted trade-offs:**

- Every startup path that needs a model must resolve first, then construct.
- A new backend is a catalog value plus a factory branch, not a Provider edit alone.

**Neutral:**

- Provider call shapes stay "resolved model name plus a façade."
- Which concrete model ids are the defaults can change in settings without revisiting this decision.

## Related documents

- [[backlog/TASK-023-ai-inference-profiles/task|TASK-023]]
- [[design/decisions/ADR-002-agent-orchestration-is-an-integration|ADR-002]]
