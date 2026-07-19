---
id: TASK-008
doc: requirements
updated: 2026-06-22
---

# TASK-008: summary store and outbox flush — Requirements

← [[task|Back to task]]

## Context

The Chat Context Management program ([[chat_context_management]], [[EPIC-001-chat-context-management/epic|EPIC-001]]) externalises evicted inline summaries into a per-chat vector store so history beyond `MAX_SUMMARY_COUNT` remains recallable on demand. Upstream tasks delivered the outbox data shape (`SummaryOutboxEntry` on `Conversation.pending_vectorization`, [[TASK-001-message-kinds-and-conversation-state-v3/task|TASK-001]]), FIFO eviction into the outbox during compression apply ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]], extended by [[TASK-007-timeout-trigger-wiring/task|TASK-007]]), and a `Maintenance` tick that currently invokes a no-op `flush_summary_outbox` stub ([[TASK-004-maintenance-integration-shell/task|TASK-004]]).

This task implements the summary store stack and drains the outbox: an embeddings HTTP façade mockable in tests, `EmbeddingProvider`, Chroma-backed `VectorProvider` (persistent under `data/`), real `Maintenance.flush_summary_outbox`, same-process idempotent retry via deterministic `summary_id`, startup removal of **incomplete** Chroma records when outbox retry is impossible, and `outbox_health_threshold` operator warnings. **Complete** Chroma records are always retained (including after crash when the in-memory outbox is empty de-facto following a successful persist). Chroma holds **derived narratives only** per [[ADR-000-sensitive-data-persistence]]; flush does not write conversation stash (graceful-shutdown-only).

Stakeholders: users (forgotten history becomes recallable after ≤ one Maintenance tick), operators (outbox depth warnings, Chroma hygiene), and downstream [[TASK-009-recall-conversation-skill/task|TASK-009]] (`VectorProvider.search` / `EmbeddingProvider.embed` must exist but recall skill wiring is out of scope here).

## Functional requirements

### FR-1: Embeddings API façade

The embedding HTTP call must be isolated behind an API-layer façade so Providers and tests never touch raw HTTP.

**Acceptance criteria:**
- [ ] A new async API class (e.g. `EmbeddingsApi` under `yoda/api/`) wraps the OpenRouter-compatible embeddings endpoint (`POST …/embeddings`); MVP wiring reads `openrouter_api_key` from `summary_store.embeddings`.
- [ ] Public method accepts a model name and a batch of input strings; returns a list of float vectors in input order.
- [ ] Default model is `openai/text-embedding-3-small`; `model_name` and `openrouter_api_key` are read from `mind.memory.summary_store.embeddings` (see [Proposed settings structure](#proposed-settings-structure)). Expected vector length is derived from `model_name` in code (not a settings field); MVP registry maps `openai/text-embedding-3-small` → 1536 and fails fast on unknown models.
- [ ] HTTP failures raise a clear exception after logging response status (no silent empty vectors).
- [ ] Unit tests use a fake/mock of the façade — no live network calls in `python -m pytest`.

### FR-2: `EmbeddingProvider`

Async Provider adapting the embeddings façade for Maintenance and future recall.

**Acceptance criteria:**
- [ ] `EmbeddingProvider` depends only on the embeddings API façade and settings (IODA Provider).
- [ ] `embed_batch(texts: list[str]) -> list[list[float]]` returns one vector per input string, preserving order; empty input returns `[]` without calling the API.
- [ ] `embed(text: str) -> list[float]` is a thin single-text wrapper over `embed_batch`.
- [ ] Provider does not import Chroma, Redis, or `MemoryProvider`.

### FR-3: `VectorProvider` and Chroma persistence

Async Provider owning Chroma lifecycle, per-chat isolation, record mapping, and document encryption hooks.

**Acceptance criteria:**
- [ ] `VectorProvider` uses Chroma **persistent** mode; storage path from `summary_store.persist_directory` (default `data/chroma`; directory created on first use if missing).
- [ ] Collections are named `{collection_prefix}{chat_id}` (default prefix `chat_`) and created lazily on first `persist_summaries` for that chat.
- [ ] `persist_summaries(chat_id, records)` accepts a batch of summary records derived from `SummaryOutboxEntry` and upserts them into the chat-scoped collection.
- [ ] Each Chroma record uses `id = summary_id` (deterministic sha256 from compression apply — see [[chat_context_management#Deterministic record id]]).
- [ ] `document` stores the narrative text only (from outbox `document`); lists in metadata are flattened to comma-separated strings (`skills`, `topics`); scalar metadata includes `compressed_at` (float), `content_from_ts`, `content_to_ts` (ISO-8601 strings) per [[chat_context_management#Record schema]].
- [ ] `encrypt(plaintext) -> str` and `decrypt(ciphertext) -> str` hooks wrap the `document` field on write/read; **default implementations are identity** (no encryption at rest in this task).
- [ ] `list_stored_records(chat_id)` returns each record's `summary_id`, decrypted `document`, and `embedding` for reconciliation (empty list when the collection is absent).
- [ ] `delete_summary_ids(chat_id, ids)` removes records by id (no-op when `ids` is empty or the collection is absent).
- [ ] No code path performs cross-chat search without a `chat_id`-scoped collection handle ([[chat_context_management#Security baseline]]).
- [ ] `chromadb` is added to `requirements.txt`; test strategy (ephemeral in-process Chroma vs fake) is documented in `design.md` and reflected in tests.

### FR-4: `Maintenance.flush_summary_outbox`

Replace the TASK-004 no-op with the transactional outbox drain described in [[chat_context_management#Persistence flow]].

**Acceptance criteria:**
- [ ] `flush_summary_outbox` runs on **every** Maintenance tick (unchanged tick order: after `compress_conversations`, before reconcile cadence).
- [ ] For each `Conversation` from `MemoryProvider.iter_conversations()` with non-empty `pending_vectorization`, entries are processed in **FIFO** order (list order as produced by compression eviction).
- [ ] Per batch: `EmbeddingProvider.embed_batch(documents)` → `VectorProvider.persist_summaries(chat_id, records)` → on **full success**, remove the flushed entries from that conversation's in-memory `pending_vectorization` (mutate the live `Conversation` object held by `MemoryProvider`).
- [ ] On embedding or Chroma failure for a conversation, **no** entries are removed from `pending_vectorization` for that failed batch; the next tick retries.
- [ ] Compression and apply paths are unchanged: flush never blocks compression; compression never awaits the vector store ([[chat_context_management#Persistence flow]]).
- [ ] Successful flush does **not** call `save_conversation_stash`; durability of the shrunk outbox waits for the next graceful shutdown per [[ADR-000-sensitive-data-persistence]].
- [ ] `Maintenance` receives `EmbeddingProvider` and `VectorProvider` via constructor injection; it does **not** import `yoda.api.*` embedding/Chroma modules directly (existing maintenance import guard remains satisfied).

### FR-5: Same-process flush idempotency

Deterministic record ids make retries safe within one process lifetime.

**Acceptance criteria:**
- [ ] When a flush attempt fails after Chroma actually persisted a record but before outbox removal, a subsequent tick retries with the **same** `summary_id` and **overwrites** the existing Chroma record instead of creating a duplicate.
- [ ] Automated test simulates embed success + persist called + simulated failure before outbox pop; second flush leaves exactly one Chroma record for that `summary_id` and clears the outbox entry.

### FR-6: Startup Chroma hygiene for incomplete records

After abnormal termination, Chroma may contain **incomplete** records (missing `document` and/or `embedding`) from a partial persist. Complete records produced by a successful flush are recall-ready and must be retained even when the in-memory outbox is empty (crash de-facto pop). `Chat.history` is audit only — reconciliation does **not** read it.

**Acceptance criteria:**
- [ ] A **complete** record has non-empty `document` and an `embedding` whose length matches the configured model dimension; **complete** records are **never** deleted by startup reconciliation.
- [ ] An **incomplete** record whose `summary_id` is still present in some `Conversation.pending_vectorization` (union across `MemoryProvider.iter_conversations()` after stash restore) is **kept** — the next flush tick can re-embed and upsert.
- [ ] An **incomplete** record whose `summary_id` is absent from every in-memory `pending_vectorization` is **deleted** from the appropriate `chat_{chat_id}` collection (narrative unrecoverable without outbox).
- [ ] Reconciliation runs once at application startup in `Maintenance.run_initial_pass` (after `restore_conversation_stash`, before the periodic loop); it is not part of every flush tick.
- [ ] Reconciliation scans all Chroma collections matching `collection_prefix`; it does **not** drop entire collections (deleted-chat lifecycle cleanup is out of scope — see [Out of scope](#out-of-scope)).
- [ ] Automated test: seed Chroma with an **incomplete** record and no matching outbox entry → reconciliation removes it.
- [ ] Automated test: seed Chroma with a **complete** record and empty outbox → reconciliation **keeps** it.
- [ ] Automated test: seed Chroma with an **incomplete** record and a matching outbox entry → reconciliation **keeps** it (retry path).

### FR-7: Outbox health threshold warnings

Operators need a signal when the outbox backs up during sustained embedding or Chroma outages.

**Acceptance criteria:**
- [ ] When `len(conversation.pending_vectorization) > ChatCompressionSettings.outbox_health_threshold` (default `10` from settings), `flush_summary_outbox` logs a **warning** each tick for that conversation (include `chat_id` and depth; no summary `document` text).
- [ ] No automatic drop or truncation of outbox entries — entries remain until a successful flush.
- [ ] Threshold is read from existing `ChatCompressionSettings.outbox_health_threshold` (no new settings key required unless design adds embedding-specific config).

### FR-8: Wiring in `yoda_chat_bot.py`

Providers are constructed and injected like other Operations.

**Acceptance criteria:**
- [ ] `SummaryStoreSettings` (or equivalent dataclass) is loaded from `mind.memory.summary_store` in `settings.json`; missing required keys fail fast at startup.
- [ ] `EmbeddingsApi` (or equivalent façade), `EmbeddingProvider`, and `VectorProvider` are constructed in `yoda/yoda_chat_bot.py` from `SummaryStoreSettings` (`embeddings.model_name` + `embeddings.openrouter_api_key`).
- [ ] `Maintenance` constructor is extended to accept `embedding_provider` and `vector_provider`; wiring passes the instances built above.
- [ ] The `summary_store` block is added to repo `settings.json` with MVP defaults; keys not consumed in TASK-008 (`search`, `document_encryption`) may be present for forward compatibility but are not required for wiring.

### FR-9: Automated tests

Behaviour is locked before [[TASK-009-recall-conversation-skill/task|TASK-009]] builds recall on top of the store.

**Acceptance criteria:**
- [ ] Tests cover: happy-path flush (outbox entry removed after embed + persist); flush failure retains outbox entries; same-process idempotent retry (FR-5); outbox health warning when depth exceeds threshold; incomplete-record cleanup (FR-6: delete when no outbox, keep when complete or outbox present).
- [ ] `VectorProvider.search` is **not** required in this task (TASK-009); persist + collection isolation tests are sufficient here.
- [ ] `python -m pytest` from the project root passes with the new tests.

## Constraints & assumptions

- **Constraint (IODA):** `Maintenance` orchestrates flush only — embedding HTTP in API façade, Chroma I/O in `VectorProvider`, no Provider-to-Provider calls; `MemoryProvider` exposes `iter_conversations` and in-memory `Conversation` mutation for outbox removal.
- **Constraint (delivery profile):** Epic `internal_compat: none` — no acceptance criteria for partial deploy states between member tasks on the shared branch. Epic `external_contract: migrate-on-merge` — existing Redis conversation stashes from TASK-001 v3 migration are unchanged; this task adds Chroma on disk and does not bump stash schema version.
- **Constraint (ADR-000):** Chroma `document` holds derived summary narrative only; no verbatim user message replicas. Flush and Chroma hygiene do not write conversation stash or expand logging of user content beyond `logger.debug` conventions.
- **Constraint:** Fail fast on missing embedding API key, Chroma misconfiguration, or malformed outbox entries — no partial outbox removal on a failed batch.
- **Constraint:** Summaries evicted inline but not yet flushed remain invisible to recall for up to one Maintenance tick — acceptable per master design; no FR to tighten flush period here.
- **Assumption:** [[TASK-006-compression-apply-and-size-trigger/task|TASK-006]] and [[TASK-007-timeout-trigger-wiring/task|TASK-007]] are complete: `pending_vectorization` is populated on FIFO eviction with full `SummaryOutboxEntry` metadata and deterministic `summary_id`.
- **Assumption:** Embeddings credentials live in `mind.memory.summary_store.embeddings` (`model_name` + `openrouter_api_key`; key duplicated from other sections is acceptable for decoupling). MVP is OpenRouter-only — provider is implied by the key name; a future non-OpenRouter backend adds a sibling key (e.g. `openai_api_key`) rather than a `provider` enum.
- **Assumption:** The only code path that writes Chroma summary records is `flush_summary_outbox` via `VectorProvider.persist_summaries`; a complete record is therefore usable for recall regardless of outbox or `Chat.history` state.
- **Assumption:** Multiple conversations with pending outbox entries on the same tick may be flushed sequentially; parallel flush is out of scope unless design documents it without changing tick structure.

## Proposed settings structure

New block under `mind.memory`, sibling to `chat_compression` and Redis keys. Outbox health stays in `chat_compression.outbox_health_threshold` (compression/outbox concern, not Chroma storage).

`embeddings.openrouter_api_key` is colocated with `model_name` so the summary-store stack is self-contained and decoupled from `perception` / `agent`. Duplicating the API key across sections is intentional. Vector dimension is **not** a setting — it follows from `model_name` via an in-code registry (avoids model/dimension mismatch).

```json
"mind": {
  "memory": {
    "redis_host": "localhost",
    "redis_port": 6379,
    "redis_db": 0,
    "chat_compression": {
      "outbox_health_threshold": 10
    },
    "summary_store": {
      "persist_directory": "data/chroma",
      "collection_prefix": "chat_",
      "embeddings": {
        "model_name": "openai/text-embedding-3-small",
        "openrouter_api_key": "<key>"
      },
      "search": {
        "default_k": 5,
        "space": "cosine"
      },
      "document_encryption": {
        "enabled": false
      }
    }
  }
}
```

**TASK-008 loads and uses:** `persist_directory`, `collection_prefix`, `embeddings.model_name`, `embeddings.openrouter_api_key`. **`search`** and **`document_encryption`** are reserved for TASK-009 and post-MVP encryption; defaults in the dataclass are sufficient until those tasks wire them.

## Open questions

All items below are **settled** in [[design]]:

| Topic | Status | Resolution |
|-------|--------|------------|
| Settings tree (`mind.memory.summary_store`) | **Settled** | `SummaryStoreSettings` dataclass + `from_dict` |
| Embeddings backend (OpenRouter MVP) | **Settled** | `openrouter_api_key` + `model_name`; dimensions from model registry in code |
| Reconciliation algorithm | **Settled** | Keep complete records; delete incomplete only when `summary_id ∉ ⋃ pending_vectorization`; `Chat.history` not used |
| Reconciliation hook placement | **Settled** | `Maintenance.run_initial_pass` after stash restore |
| Chroma test strategy | **Settled** | Ephemeral `tmp_path` Chroma for integration tests; fakes for Maintenance unit tests |
| HNSW / `search.space` tuning | **Deferred** | Keys reserved in JSON; defaults in code until recall quality or volume demands tuning |
| `flush_batch_size` | **Deferred** | Not in MVP settings |
| Deleted-chat Chroma cleanup | **Deferred** | Follow-up task (`delete_user_data`, collection drop) — not TASK-008 |

## Out of scope

- `recall_conversation` agent skill and `VectorProvider.search` filter surface ([[TASK-009-recall-conversation-skill/task|TASK-009]]).
- Changes to compression apply, window selection, or outbox push logic ([[TASK-006-compression-apply-and-size-trigger/task|TASK-006]], [[TASK-007-timeout-trigger-wiring/task|TASK-007]]).
- Promotion of retrieved summaries into the inline tail ([[chat_context_management#Recall path]]).
- `save_conversation_stash` on flush, apply, ingest, or Maintenance tick ([[ADR-000-sensitive-data-persistence]]).
- Real AES-GCM application-level encryption (identity hooks only; encryption wiring deferred).
- In-process LRU cache keyed by `summary_id`.
- Volume encryption (LUKS) — operator configuration, no code.
- Tightening Maintenance tick period independently of `mind.maintenance.tick_minutes`.
- Dropping Chroma collections when a chat or user is deleted (`delete_user_data`, `manage_user_data` skill) — follow-up task.
