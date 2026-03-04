# Ideas on possible code structure, integration flows and testing approach
## Project Structure

```
yoda_chat_bot.py                        # Construction: wires everything, starts event loop

embodiment/
  telegram_portal.py               # Portal (async): receives updates (text/audio/photo), sends replies
  cron_portal.py                   # Portal (async): scheduled triggers
  site_watcher_portal.py           # Portal (async): website event triggers

mind/
  # ── Providers / APIs (A) ──────────────────────────────────────
  intelligence/
    language_provider.py           # async: LLM completions
    audio_provider.py              # async: Speech-to-text
    vision_provider.py             # async: Image-to-text
  memory_provider.py               # async: conversation history + user profiles

  # ── Agent Cell (Hexagonal inside IODA) ────────────────────────
  agent/
    core/
      react_loop.py                # Pure sync logic: decide(context) → Decision
    ports/
      tool_port.py                 # Abstract base: Tool.execute(call) → ToolResult
    adapters/
      web_search_tool.py           # async Tool adapter
      browser_tool.py              # async Tool adapter
      memory_tool.py               # async Tool adapter
    agent_provider.py              # IODA façade: async run(task, profile) → AgentResult

  # ── Operations (O) ────────────────────────────────────────────
  ops/
    conversation_ops.py            # append, trim, build_system_prompt
    emotion_ops.py                 # update_state, decay, influence_prompt
    memory_ops.py                  # extract_facts, build_profile
    message_ops.py                 # parse_update, detect_media_type, from_agent_result, from_trigger
    group_ops.py                   # should_respond, mention_detection

  # ── Data (D) ──────────────────────────────────────────────────
  data/
    message.py                     # Message { role, text, media_type, timestamp }
    conversation.py                # Conversation { user_id, messages: [Message] }
    emotional_state.py               # EmotionalState { valence, arousal }
    user_profile.py                # UserProfile { facts, preferences, emotion }
    agent_result.py                # AgentResult { answer, tools_used }
    trigger_event.py               # TriggerEvent { topic, payload, source }

  # ── Integrations (I) ──────────────────────────────────────────
  processor.py                     # "Body": all core pipelines (async, no logic)
  application.py                   # "Head": binds Portals to Processor (async)
```

---

## Core Pipelines (processor.py)

All functions in `processor.py` are **async Integrations**: no `if/else` business logic, only `await` and passing data between Ops and Providers. Use `asyncio.gather()` for independent steps.

```python
# Pipeline 1: standard dialogue
async def handle_message(user_id, raw_update):
    message             = MessageOps.parse_update(raw_update)          # sync Op
    conversation, profile = await asyncio.gather(                      # parallel I/O
        MemoryProvider.load(user_id),
        MemoryProvider.load_profile(user_id)
    )
    emotion             = EmotionOps.update_state(profile.emotion, message)  # sync Op
    conversation        = ConversationOps.append(conversation, message)      # sync Op
    conversation        = ConversationOps.trim(conversation, max_tokens=4000)# sync Op
    llm_response        = await LanguageProvider.complete(conversation, emotion, profile)
    reply_message       = MessageOps.from_llm_response(llm_response)         # sync Op
    conversation        = ConversationOps.append(conversation, reply_message) # sync Op
    new_emotion         = EmotionOps.decay(emotion)                           # sync Op
    await MemoryProvider.save(conversation, profile, new_emotion)
    return llm_response.text

# Pipeline 2: agentic task
async def handle_agent_task(user_id, task):
    profile      = await MemoryProvider.load_profile(user_id)
    agent_result = await AgentProvider.run(task, profile)
    message      = MessageOps.from_agent_result(agent_result)
    conversation = await MemoryProvider.load(user_id)
    conversation = ConversationOps.append(conversation, message)
    await MemoryProvider.save(conversation)
    return agent_result.answer

# Pipeline 3: cron / site watcher trigger
async def handle_trigger(trigger_event):
    subscribers = await MemoryProvider.load_subscribers(trigger_event.topic)
    task        = MessageOps.from_trigger(trigger_event)
    await asyncio.gather(*[
        handle_agent_task(user_id, task) for user_id in subscribers
    ])

# Pipeline 4: group chat
async def handle_group_message(group_id, raw_update):
    message      = MessageOps.parse_update(raw_update)
    should_reply = GroupOps.should_respond(message, bot_config)   # sync Op
    if not should_reply:
        return None
    return await handle_message(group_id, raw_update)
```

> **Note:** `handle_group_message` contains one `if` — this is acceptable as a routing guard, not business logic. If routing grows complex, extract to a dedicated Integration.

---

## asyncio Rules

| Location | async? | Reason |
|----------|--------|--------|
| `ops/*.py` — all Operations | **No** | Pure logic, no I/O. Sync is simpler to test. |
| `data/*.py` — Data models | **No** | Just data structures. |
| `*_provider.py`, `*_portal.py` | **Yes** | All network/disk I/O lives here. |
| `processor.py` | **Yes** | Calls async Providers. No logic added. |
| `application.py` | **Yes** | Calls async Processor and Portals. |
| `agent/core/react_loop.py` | **No** | Pure reasoning logic. |
| `agent/adapters/*.py` | **Yes** | Tool execution is I/O. |
| `agent/agent_provider.py` | **Yes** | Façade over async tool calls. Uses `asyncio.gather()` for parallel tool execution. |

Use `asyncio.gather()` whenever two or more Providers/Portals are called and their inputs are independent.

---

## Sleepy Hollow Split (Testability Boundary)

```
┌──────────────────────────────────────────────────┐
│  HEAD (hard to auto-test)                         │
│  telegram_portal, cron_portal, site_watcher_portal│
│  application.py                                   │
├──────────────────────────────────────────────────┤  ← cut here
│  BODY (acceptance-testable)                       │
│  processor.py          ← attach acceptance tests  │
│  mind/ops/*            ← pure unit tests, no mocks│
│  agent/core/react_loop ← pure unit tests, no mocks│
│  Providers/Portals     ← mocked at this boundary  │
└──────────────────────────────────────────────────┘
```

**Testing strategy:**
- `ops/*` and `agent/core/react_loop.py`: unit tests with plain data objects, zero mocks.
- `processor.py`: acceptance/integration tests mocking only Providers (`LanguageProvider`, `MemoryProvider`, `AgentProvider`).
- Head (portals): manual or e2e tests only.

---

## Rules for Adding New Features

### New agentic tool (e.g. calendar, email)
1. Add `adapters/calendar_tool.py` implementing `Tool` port — async.
2. Register in `agent_provider.py`. 
3. No changes to `react_loop.py`, `processor.py`, or any Op.

### New input modality (e.g. video)
1. Add `intelligence/video_provider.py` — async Provider.
2. Add `MessageOps.detect_video()` in `ops/message_ops.py` — sync Op.
3. Wire in `processor.py` pipeline — add `await` call, no logic.

### New trigger source (e.g. email, RSS)
1. Add `embodiment/email_portal.py` — async Portal.
2. Wire to `application.py` → `processor.handle_trigger()`.
3. No changes to Ops or domain logic.

### New pipeline
1. Add a new `async def handle_*(...)` in `processor.py`.
2. It must contain zero business logic — only calls to existing Ops and Providers.
3. If you need new logic, add it as a new function in the appropriate `ops/*.py`.

---

## Anti-patterns to Avoid

| Anti-pattern | Why forbidden | Fix |
|---|---|---|
| Op calling another Op directly | Creates functional dependency, breaks testability | Integration passes data explicitly |
| Logic inside processor.py | Violates IOSP | Extract to an Op |
| async in ops/*.py | Ops must be sync pure functions | Move I/O to a Provider |
| Provider containing business logic | Mixes concerns | Extract logic to Op, keep Provider as thin I/O wrapper |
| react_loop.py importing tool adapters | Breaks Hexagonal isolation | Use Tool port abstraction only |
| Growing AgentProvider with logic | Façade should stay thin | Logic → react_loop.py (Op), orchestration → agent_provider.py (Integration) |
