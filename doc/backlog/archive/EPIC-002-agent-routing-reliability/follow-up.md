---
id: EPIC-002
doc: follow-up
updated: 2026-07-22
status: open
---

# EPIC-002 follow-ups

← [[backlog/archive/EPIC-002-agent-routing-reliability/epic|Back to epic]] |
[[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/task|TASK-021]] |
[[backlog/archive/TASK-021-stage-telemetry-and-live-eval-runner/review|TASK-021 review]]

Harvested after **TASK-021** close (`verdict: pass-with-follow-ups`) plus
post-close product asks. Epic itself is **done**; these items are **not**
blocking epic merge. They are candidates for new standalone backlog tasks
(or a small follow-on epic) — create via the `new-task` Templater template,
then run requirements → design → plan as usual.

## How a cold agent should use this file

1. Read this document end-to-end, then skim TASK-021 `design.md` /
   `implementation-notes.md` and `yoda/mind/evaluation/` as needed.
2. Group related items into tasks (suggested groupings below). Prefer few
   coherent tasks over one mega-task or many one-liners.
3. For each new task: clear scope boundary, FR-style acceptance criteria,
   IODA placement, and explicit non-goals (especially: do **not** make live
   eval PR-blocking unless a future task explicitly says so).
4. Respect ADR-000: reports and logs must not store user-message replicas,
   prompt bodies, raw model responses, or credentials.
5. Default branch: if still integrating EPIC-002 work, use
   `feat/EPIC-002-agent-routing-reliability`; otherwise open a new branch /
   epic as the developer prefers.
6. Mark each item `done` / `deferred` / `dropped` in this file when handled
   (or delete the item and note the TASK id under [Disposition](#disposition)).

### Suggested task groupings

| Suggested task | Items | Size (hint) |
|----------------|-------|-------------|
| Live eval UX + settings | F-4, F-5, F-6, F-7 | M |
| PromptIdentityCore import hygiene | F-1 | S |
| Resume bypass telemetry coverage | F-2 | XS |
| Dedup live fakes (when triggered) | F-3 | S — **defer until third consumer** |

---

## Context (as-built baseline)

Live routing evaluation was delivered by TASK-021:

| Concern | Current behavior |
|---------|------------------|
| Entry | `python -m yoda.mind.evaluation.live_runner` |
| Credentials / model | Read from `settings.json`: `agent.model_name` + `llm.api_key` (CLI `--settings`) |
| Report dir default | `artifacts/live_routing_eval` (`DEFAULT_REPORT_DIR` in `live_evaluation.py`; gitignored) |
| Report format | Unique privacy-safe **JSON** only (`LiveEvalReport` via `LiveEvalReportProvider`) |
| Console | Short summary string + artifact path (`LiveRoutingEvaluationCore.format_console_summary`) |
| Side effects | Only `LLMApi` may network; other boundaries fail-closed (`live_fakes.py`) |
| CI | Deterministic corpus (TASK-020) stays PR-gating; live runner is opt-in |

Key paths:

- `yoda/mind/evaluation/live_runner.py`
- `yoda/mind/evaluation/live_evaluation.py`
- `yoda/mind/evaluation/live_report_provider.py`
- `yoda/mind/evaluation/live_core.py`
- `yoda/mind/evaluation/prompt_identity_core.py`
- `yoda/mind/evaluation/observation.py`
- `yoda/mind/evaluation/live_fakes.py`
- `tests/routing_evaluation/fakes.py` (test-only twin of storage/tools fakes)
- `yoda/mind/agent/AGENTS.md` (live-runner docs)

---

## Items

### F-1 — PromptIdentityCore: control-plane strings only (drop lazy imports)

| | |
|--|--|
| **Origin** | TASK-021 `implementation-notes.md` tech-debt; review Low finding |
| **Kind** | Tech debt / IODA hygiene |
| **Size hint** | S |
| **Depends on** | None |
| **Epic membership** | Standalone (or light EPIC-002 follow-on); not required for epic merge |

**Problem.** `PromptIdentityCore` stage helpers (`intent_identity`,
`selection_identity`, `execution_identity`, `delivery_identity`) **lazy-import**
prompt constants from `cognition` / `react_loop` / `delivery_core` to break a
circular import (`CognitionProvider` → `PromptIdentityCore` → `cognition`).
That makes a Core depend on Provider/Integration modules at runtime.

**Desired outcome.** Core hashes only Data / caller-supplied strings.
Integrations (or Providers) pass already-built control-plane material into
identity helpers. Eager imports of production prompt modules from Core go away.
ID string constants may stay re-exported from `prompt_identity_core` for stable
values, or live beside prompts with Core importing only Data.

**Acceptance sketch.**

- No lazy imports inside `PromptIdentityCore` methods.
- Core module does not import `yoda.mind.cognition` / agent Integration modules
  at import time or call time.
- Existing `tests/test_prompt_identity.py` and telemetry/live tests stay green;
  hashes for the same control-plane inputs remain stable.
- Document the call-site ownership in TASK design or `agent/AGENTS.md` briefly.

**Non-goals.** Changing prompt ID strings or hash algorithm; changing which
material is hashed.

---

### F-2 — Telemetry assert for resume bypass (`agent_resume`)

| | |
|--|--|
| **Origin** | TASK-021 `review.md` Info / Follow-ups |
| **Kind** | Test coverage gap |
| **Size hint** | XS |
| **Depends on** | None |
| **Epic membership** | Standalone |

**Problem.** `Mind._classify_intent` has a resume `BYPASSED` path with
`detail=agent_resume`. Chat `not_applicable` / rejected paths are covered in
`tests/test_routing_telemetry.py`; resume bypass has no dedicated assert.

**Desired outcome.** One focused test that a resume / agent-session bypass emits
stage diagnostic with `outcome=bypassed` (or the project’s canonical resume
label) and closed `detail=agent_resume`, with no user content at INFO/WARNING.

**Acceptance sketch.**

- New or extended case in `tests/test_routing_telemetry.py`.
- Asserts stage + outcome + detail tokens only (ADR-000).

**Non-goals.** Changing resume routing behavior.

---

### F-3 — Deduplicate live fakes vs test routing fakes (deferred)

| | |
|--|--|
| **Origin** | TASK-021 `implementation-notes.md`; review Info |
| **Kind** | Tech debt — **defer until trigger** |
| **Size hint** | S |
| **Depends on** | A **third** consumer of the same adapters |
| **Epic membership** | Standalone; create task only when trigger fires |

**Problem.** `InMemoryStorageApi` / `RecordedToolProvider` (and related) exist
under both `tests/routing_evaluation/fakes.py` (TASK-020 harness) and
`yoda/mind/evaluation/live_fakes.py` so live evaluation never imports `tests.*`.

**Desired outcome.** When a third consumer appears, extract a shared
**production-safe** module under `yoda/mind/evaluation/` (or similar). Tests and
live runner both import that module; `tests.*` stays out of production.

**Acceptance sketch.**

- Single source of truth for shared adapters.
- Live runner and deterministic harness still isolate side effects.
- No `from tests...` in `yoda/`.

**Non-goals.** Dedup “just because”; premature abstraction before a third call
site.

**Trigger to open a task.** New production or evaluation code needs the same
in-memory storage / recorded-tool adapters.

---

### F-4 — Human-readable report alongside JSON

| | |
|--|--|
| **Origin** | Post-close product ask (2026-07-22) |
| **Kind** | Feature |
| **Size hint** | S–M (group with F-5…F-7) |
| **Depends on** | None (builds on TASK-021 report pipeline) |
| **Epic membership** | Follow-on task; may share task with F-5–F-7 |

**Problem.** Live runs write only a unique JSON artifact. Console summary is
short. Operators want a durable **human-readable** sibling report for review
without parsing JSON.

**Desired outcome.** Each successful write produces JSON **and** a readable
artifact (e.g. Markdown or plain text) in the same report directory, derived
from the same `LiveEvalReport` (single source of truth — do not diverge
metrics). Filename pairing should be obvious (same run id / stem).

**Suggested contents (minimum).**

- Run id, status, model id, corpus version, timestamps
- Counts: attempted / passed / failed / excluded / incomplete
- Per-stage metrics (pass rates)
- Exclusion list (case id + reason)
- Failed / incomplete case ids (no user utterance text)
- Path to the JSON sibling
- Distinct `prompts_used` (id + hash only)

**Acceptance sketch.**

- Provider (or Core formatter + Provider write) emits both files atomically
  enough for CLI to print both paths.
- Privacy: same redaction rules as JSON (ADR-000).
- Unit test: round-trip or snapshot of formatter from a fixture `LiveEvalReport`.
- Docs in `yoda/mind/agent/AGENTS.md` updated.

**Non-goals.** HTML dashboards, upload to remote storage, PR comments.

---

### F-5 — Configurable LLM `rate_limit` and `retry_count` for live eval

| | |
|--|--|
| **Origin** | Post-close product ask (2026-07-22) |
| **Kind** | Feature |
| **Size hint** | S–M (group with F-4, F-6, F-7) |
| **Depends on** | F-7 settings section (or implement together) |
| **Epic membership** | Follow-on task |

**Problem.** Live corpus runs issue many LLM calls. Providers rate-limit;
transient failures need bounded retries. Today the live runner constructs
`LLMApi(api_key=...)` without eval-specific pacing/retry knobs.

**Desired outcome.** Live evaluation respects configurable:

- **`rate_limit`** — pacing between LLM calls (define unit clearly in
  requirements: e.g. max requests per minute, or minimum delay between calls).
- **`retry_count`** — max retries on retryable provider errors (429 / transient
  network), with fail-fast on auth / non-retryable errors.

Behavior must still classify operational errors into existing
`OperationalErrorCategory` / incomplete case handling — retries that exhaust
must not count as stage passes.

**Acceptance sketch.**

- Settings-driven (see F-7); CLI override optional but not required.
- Fail fast on missing/invalid config (project convention).
- Tests with fakes: assert delay/retry policy without real network (fake clock
  or call counters).
- Document defaults and semantics in AGENTS.md / task requirements.

**Non-goals.** Changing production bot chat path rate limits unless explicitly
scoped; unbounded backoff; making live eval CI-blocking.

**Design note for the implementer.** Prefer applying policy at the live
evaluation / LanguageProvider boundary used by the runner, not scattering sleep
calls across stage Integrations. Keep IODA: Core for pure retry/eligibility
decisions if needed; Provider/API for actual waits and HTTP.

---

### F-6 — Default report path → `evals/live_routing`

| | |
|--|--|
| **Origin** | Post-close product ask (2026-07-22) |
| **Kind** | Feature / config default change |
| **Size hint** | XS–S (group with F-4, F-5, F-7) |
| **Depends on** | F-7 preferred (default may live in settings) |
| **Epic membership** | Follow-on task |

**Problem.** Default report directory is `artifacts/live_routing_eval`. Desired
default is **`evals/live_routing`**.

**Desired outcome.**

- Code default / settings default: `evals/live_routing`.
- `.gitignore` updated so generated reports under that tree are ignored (keep
  directory placeholder if the repo uses `.gitkeep` pattern elsewhere).
- CLI `--report-dir` still overrides.
- Docs (`agent/AGENTS.md`, any runbook mentions) updated.
- Existing references to `artifacts/live_routing_eval` migrated or redirected.

**Acceptance sketch.**

- `DEFAULT_REPORT_DIR` (or settings-derived path) points at `evals/live_routing`.
- Tests that assert the default path updated.
- No secrets or user content committed under `evals/`.

**Non-goals.** Migrating historical local artifacts; uploading reports.

---

### F-7 — Dedicated `evals` section in `settings.json`

| | |
|--|--|
| **Origin** | Post-close product ask (2026-07-22) |
| **Kind** | Feature / config |
| **Size hint** | S (group with F-4…F-6) |
| **Depends on** | None (foundation for F-5 / F-6) |
| **Epic membership** | Follow-on task |

**Problem.** Live runner peeks at `agent.model_name` and `llm.api_key` only.
There is no dedicated eval configuration block for report path, pacing, retries,
or eval-specific model overrides.

**Desired outcome.** Add a top-level (or clearly documented) **`evals`** section
in `settings.json` with everything needed to run live routing eval. Fail fast if
required keys are missing when the live runner starts.

**Proposed shape (adjust in requirements/design; illustrative):**

```json
{
  "evals": {
    "live_routing": {
      "model_name": "…",
      "api_key": "…",
      "report_dir": "evals/live_routing",
      "rate_limit": { "…": "define unit in requirements" },
      "retry_count": 3,
      "corpus_path": "tests/fixtures/routing_evaluation/corpus-v1.json"
    }
  }
}
```

**Requirements for the implementing agent.**

- Decide whether `api_key` / `model_name` are **required in `evals`** or may
  fall back to `llm` / `agent` with an explicit documented precedence (prefer
  fail-fast dedicated keys if the product wants eval isolation).
- Typed settings loader (Data) consistent with other settings DTOs in the repo
  (`from_dict` / fail fast).
- `live_runner` reads this section; CLI flags remain overrides where they exist
  today (`--case`, `--corpus`, `--report-dir`, `--settings`).
- Example / documented stub in AGENTS.md (no real secrets in docs).
- Update `.gitignore` for the default report tree (with F-6).

**Acceptance sketch.**

- Missing required `evals.live_routing` keys → clear `SystemExit` / validation
  error before any model call.
- Unit tests for settings parse + precedence.
- Live unit tests still use fakes and do not need real credentials.

**Non-goals.** Remote config services; encrypting keys beyond existing local
`settings.json` practice; CI secrets wiring for mandatory live runs.

---

## Explicitly out of scope (do not invent tasks unless asked)

- Making live evaluation **PR-blocking** or defining **release pass thresholds**
  (carried over from EPIC-002 master design close-out).
- Changing corpus expectations to chase model variance.
- Calling real Telegram / Tavily / Redis / Chroma / scheduler from the live
  runner.

---

## Disposition

| Item | Status | Resulting task / note |
|------|--------|------------------------|
| F-1 | open | |
| F-2 | open | |
| F-3 | deferred (trigger) | |
| F-4 | open | |
| F-5 | open | |
| F-6 | open | |
| F-7 | open | |

When creating tasks, link them here and set `epic:` only if you intentionally
open a follow-on epic; otherwise leave standalone and link from
[[backlog/main|main]] Notes if useful.
