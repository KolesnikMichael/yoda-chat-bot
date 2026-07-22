# Agent Module

Two-phase ReAct loop with declarative skills and typed tools. `Agent`
(Integration) orchestrates; `ReactLoop` (Core) builds phase-specific context and
validates decisions; `ExecutionContextCore` owns preference aliasing, host
normalization, and pre-dispatch constraint preparation; Providers adapt language,
sessions, and tools.

## Two-phase execution

1. **Selection** — tool-free. LLM sees a compact skill catalog (control message)
   and returns a `SelectionDecision`: `select_skill` (with distilled task +
   typed `request_constraints`) or `no_skill` (`reason=unsupported`). No tools,
   no clarification, no final answer. Selection prompts must **not** inject
   `skill_preferences`.
2. **Execution** — after skill activation. Full skill spec + filtered tool schemas
   are injected. Only the **active skill's** effective preferences appear in a
   delimited untrusted `<profile_data>` block. The user message carries `<task>`
   and `<request_constraints>`. LLM returns an `ExecutionDecision`: `call_tools`,
   `finish`, or `fail` (`failure_reason=unsupported` only).

Phase-specific Pydantic models use `extra="forbid"`. Semantic cross-field and
membership rules live in `ReactLoop.validate_selection_decision` /
`validate_execution_decision` and return `ProtocolIssue`, never answer strings.
Before tool dispatch, `Agent` calls `ExecutionContextCore.prepare_tool_requests`;
`INVALID_CONSTRAINT` consumes the execution corrective budget and dispatches
nothing.

### Preferences vs constraints

- **Stored preferences** (`UserProfile.skill_preferences`) are durable defaults.
  Reads for `search_web` merge canonical `search_web` values first, then legacy
  `web_search`, with case-insensitive dedupe; the profile is never mutated by
  reads. New writes canonicalize to `search_web` (via summarizer /
  `update_profile` / `ExecutionContextCore.canonicalize_profile_update_fields`).
- **Request constraints** (`RequestConstraints`) are per-request strict/soft
  source domains carried beside the self-contained `distilled_task`. Precedence:
  strict → soft → stored → skill default. One-off restrictions are not promoted
  to profile data.

### IANA timezone (absolute / recurring schedules)

After skill selection, `schedule_message` and deferred/recurring `search_web`
resolve local-time identity in this order: explicit valid IANA name → valid
profile timezone → infer from an unambiguous named location (persist via
`update_profile` with both `timezone` and `location`) → one `ask_user` for
city/region or IANA. Never ask for the user's current clock; never accept a bare
UTC offset as identity. Absolute and cron tool calls must carry an explicit
`ZoneInfo`-valid timezone; inferred values are copied into both the profile
update and the scheduling arguments (batching is allowed only when scheduling
does not depend on the write). Relative `delay_minutes` skips timezone
clarification. `ScheduleCore.validate_timezone_name` owns validation;
`relative_timezone_name` is display/metadata fallback for relative delays only.

### Corrective retry

Each phase has one persisted boolean budget (`selection_retry_used` /
`execution_retry_used`). On malformed or invalid output (including
`INVALID_CONSTRAINT`), `ReactLoop.append_correction` appends a closed-template
`system` message and marks the budget used. A second failure returns typed
`AgentFailure(category="protocol_exhausted")` and deletes any pending session.
Rejected model output is never appended as accepted history. Correction text
never interpolates user/query/domain strings.

### Message accumulation

Messages accumulate in `AgentContext.messages` across the active phase:

```
[system]    Selection or execution role + phase JSON schema
[system]    Selection control catalog (selection) OR untrusted profile_data (execution)
[user]      Selection input OR <task> + <request_constraints>
[system]    Skill activation + tools (execution)
[assistant] Phase decision JSON
[system]    Tool results (execution)
[assistant] {"mode":"finish","final_answer":"..."}
```

UTC time is appended as a trailing system message on each LLM call only — not
stored in context.

## Suspend / resume

When `ask_user` fires (execution only), the loop suspends and `AgentContext`
(including `phase`, retry flags, `protocol_version`, `request_constraints`,
`outcome_evidence`, and any unresolved terminal failure) is saved via
`AgentSessionProvider`. New sessions use
`protocol_version=4`. On `resume()`, sessions with `protocol_version < 4` are
upgraded lazily: the named skill is reloaded; recognized generated execution
system/task/activation messages are refreshed to the protocol-4 schema (including
`fail`); task, clarification, assistant, tool history, constraints, and retries
are preserved. Missing `outcome_evidence` / `request_constraints` on legacy
sessions decode as empty. Session is deleted after a terminal
`ExecutionOutcome` or typed protocol failure.

If a resumed session is still in pre-selection (`active_skill is None`),
`Agent` refreshes the selection seed from the current validated catalog before
the next selector call. Legacy combined catalog-in-user transcripts are rewritten
into the control/input split while preserving the user-data prefix and later
clarification messages.

## Outcomes and delivery

`AgentResult` is exclusive: either `outcome: ExecutionOutcome` or
`clarification: ClarificationResult`. Success is authorized only by
code-derived `OutcomeEvidence` (from successful tools / typed
`TerminalResultFacts`); a model `finish` without relevant evidence becomes a
`transient` failure. A failed terminal tool also blocks a later `finish`, even
when earlier non-terminal evidence exists; a subsequent successful terminal
retry remains authoritative. Execution `fail/unsupported` maps to an
`unsupported` safe failure. `OutcomeCore` maps internal failures to
`ambiguous` / `transient` / `unsupported` without skill, tool, schema, or
provider strings. `Mind` passes outcomes through `DeliveryCore`, which emits
semantic allowed/prohibited claim tokens and an authoritative
`GROUNDED DELIVERY:` instruction (JSON-delimited untrusted source text). Static
`job_kind=message` creation and firing never authorize live recomputation;
`job_kind=task` never claims a future result before the job runs.

## Invariants

- **Immutability**: `append_assistant()` / `append_tool_results()` /
  `append_correction()` return a new `AgentContext`, never mutate.
- **Stateless tools**: tools receive only their `ToolCall`, never `AgentContext`.
- **Terminal tools**: `terminal=True` → loop exits immediately on success and
  builds success from typed terminal facts / evidence.
- **Typed outcomes**: unsupported / protocol / iteration exhaustion /
  evidence-free finish use `AgentResult.outcome` failures; there is no free-form
  `"Task completed."` fallback for those paths.
- **Metadata injection**: `chat_id`, `user_id`, `profile_timezone` are added to
  every `ToolCall.metadata` by `Agent`.
- **Constraint preparation**: every `web_search` / `web_extract` / `schedule_task`
  dispatch path goes through `ExecutionContextCore.prepare_tool_requests`.

## Adding a new skill

1. Create `skills/specs/<name>.md` — YAML frontmatter (`name`, `description`, `tools`) + workflow instructions + tool_calls examples.
2. No code changes. `catalog.py` auto-discovers specs at startup.

### Public vs private skills

Skills have a `public` field in frontmatter (default: `true`).

- **Public** skills are advertised to users in the chat system prompt (== CAPABILITIES == block). When a user asks "what can you do?", the chat LLM describes these naturally.
- **Private** skills (`public: false`) are hidden from the capabilities list but still available to the agent during skill selection. Use for internal/operational skills (e.g. `manage_user_data`).

The agent selection phase always sees the full catalog (public + private).

## Deterministic routing evaluation (TASK-020)

Structural routing quality is gated by a versioned synthetic corpus and a
test-only harness — not by judging final Yoda prose.

- **Corpus fixture:** `tests/fixtures/routing_evaluation/corpus-v1.json`
  (`schema_version`, `corpus_version`, stable per-case IDs). All text is
  synthetic; never copy production transcripts (ADR-000).
- **Reusable contracts:** `yoda/mind/evaluation/` — Data (`data.py`), pure scorer
  (`RoutingEvaluationCore` in `core.py`), async loader (`RoutingCorpusProvider`).
- **Observation Integrations:** `ObservingMind` / `ObservingAgent` /
  `ObservingCognitionProvider` in `yoda/mind/evaluation/observation.py`
  (shared with live eval). The test harness imports these; recorded LLM/tool
  adapters stay under `tests/routing_evaluation/`.
- **Test-only runner:** `tests/routing_evaluation/` — `RoutingEvaluation` and
  recorded adapters. Normal CI runs `tests/test_routing_evaluation.py`;
  focused rerun:
  `ROUTING_EVAL_CASE=<stable-id> .venv/bin/python -m pytest tests/test_routing_evaluation.py -q`

## Live routing evaluation (TASK-021)

On-demand live-model runs over the same corpus. **Not** PR/CI gating — cost,
rate limits, and model drift make scores informational only. Pytest never
invokes the live CLI and does not require live credentials.

```bash
.venv/bin/python -m yoda.mind.evaluation.live_runner \
  [--case CASE_ID] \
  [--corpus PATH] \
  [--report-dir PATH] \
  [--settings PATH]
```

- **Defaults:** checked-in `tests/fixtures/routing_evaluation/corpus-v1.json`,
  report dir `artifacts/live_routing_eval/`, project `settings.json` with
  `agent.model_name` + `llm.api_key`.
- **Full corpus:** omit `--case`. **Single case:** `--case <stable-id>` (unknown
  IDs fail before any model call).
- **Side-effect boundary:** only the configured `LLMApi` may network; Telegram,
  Tavily, media, Redis, scheduler, and Chroma are fail-on-call. Tool outcomes
  still come from corpus-recorded fixtures.
- **Reports:** unique JSON under `artifacts/live_routing_eval/` (gitignored)
  with model id, prompt id/hash pairs, corpus version, exclusions, stage
  metrics, and scored eligible cases. Console summary prints the artifact path.
- **Metrics:** incomplete/excluded/unattempted cases do not inflate stage
  pass rates. Forced-malformed/recovery fixtures are excluded with stable
  reasons; deterministic CI still scores them.
- **Production telemetry:** `Mind` / `Agent` / `CognitionProvider` emit
  privacy-safe INFO/WARNING stage diagnostics via `RoutingTelemetryCore`
  (no user content at those levels).

## Adding a new tool

1. Create `tools/<name>_tool.py` implementing the `Tool` port (`tool_port.py`) with a Pydantic `parameters_schema`.
2. Instantiate in `yoda_chat_bot.py` and inject into `Agent`.
3. Reference the tool name in skill specs that need it.
4. Set `terminal=True` if the tool completes the entire task by itself.

## Infrastructure tools (available after skill activation)

- **`ask_user`** — suspends loop, signals clarification needed. Mind delivers the question in Yoda's voice. Not available during selection.
- **`update_profile`** — saves user profile fields (timezone, location,
  `skill_preferences` / `skill_preferences_to_add` with canonical skill-name
  keys) via MemoryProvider. Can be batched with other tool calls. Agent
  canonicalizes preference write deltas before dispatch.
