# Ideas on possible code structure, integration flows and testing approach
## Project Structure

```
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

```
## Core Pipelines 

# Pipeline 2: agentic task
async def handle_agent_task(user_id, task):
    profile      = await MemoryProvider.load_profile(user_id)
    agent_result = await AgentProvider.run(task, profile)
    message      = MessageCore.from_agent_result(agent_result)
    conversation = await MemoryProvider.load(user_id)
    conversation = ConversationCore.append(conversation, message)
    await MemoryProvider.save(conversation)
    return agent_result.answer

# Pipeline 3: cron / site watcher trigger
async def handle_trigger(trigger_event):
    subscribers = await MemoryProvider.load_subscribers(trigger_event.topic)
    task        = MessageCore.from_trigger(trigger_event)
    await asyncio.gather(*[
        handle_agent_task(user_id, task) for user_id in subscribers
    ])

```
## Rules for Adding New Features

### New agentic tool (e.g. calendar, email)
1. Add `adapters/calendar_tool.py` implementing `Tool` port — async.
2. Register in `agent_provider.py`. 
3. No changes to `react_loop.py`, `processor.py`, or any Core.

### New input modality (e.g. video)
1. Add `intelligence/video_provider.py` — async Provider.
2. Add `MessageCore.detect_video()` in `core/message_core.py` — sync Core.
3. Wire in `processor.py` pipeline — add `await` call, no logic.

### New trigger source (e.g. email, RSS)
1. Add `embodiment/email_portal.py` — async Portal.
2. Wire to `application.py` → `processor.handle_trigger()`.
3. No changes to Ops or domain logic.

### New pipeline
1. Add a new `async def handle_*(...)` in `processor.py`.
2. It must contain zero business logic — only calls to existing Ops and Providers.
3. If you need new logic, add it as a new function in the appropriate `*_core.py`.

---