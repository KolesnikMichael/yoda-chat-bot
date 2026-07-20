# Notes

## Fix

- Stop calculating chat_type each time - it doesn't change
- Add modify_job tool for manage_jobs skill, otherwise job just gets cancelled
- Job's description repeats message_text, but at least skill name should be present in description, so that list_jobs is aware of task nature. Ideally it should contain distilled_task
- Agent routing, skill-selection contracts, phase protocol, preference propagation,
  truthful completion, deterministic commands, and evaluation:
  [[EPIC-002-agent-routing-reliability/epic|EPIC-002 — agent routing reliability]].
  Related context-noise fix:
  [[TASK-010-only-visible-kinds-for-intent-context/task|TASK-010]].
- Agent: no test for batched ask_user + failing companion tool (e.g. update_profile) — suspend path works but untested
- Agent: Mind._handle_agent_task / resume have no try/except — LLM, Redis session, or other failures during agent run can crash message handling
- TASK-015 follow-up: strengthen Core coverage for blank `selected_skill`, empty `tool_calls`, `no_skill` without `unsupported`, and exhausted execution correction; fix session round-trip fixture phase consistency; update AGENTS.md legacy-upgrade wording

## Add

- Design invariants to the root (?) AGENTS.md: chat isolation, chats nonpersistence, low hardware requirements, low budget, logging, exception handling, etc.
- Retry after 429 where needed
- Scheduling jobs: add timezone/DST transition tests; scheduling already uses
  IANA `ZoneInfo` + timezone-aware `CronTrigger`, so verify behavior rather than
  adding offset-based DST logic
- Admin notifications
- Record skill usages in Chat.history:
  - create_picture: iterations
  - manage_jobs: task
  - manage_user_data: task
  - schedule_message: daily/once
  - search_web: tools
- Error handling (logging + retry, where needed + admin notification, where needed):
  - network errors to Telegram
  - Redis failures
  - ChromaDB failures
  - speech/vision/LLM/embeddings/text-to-image errors
  - file operations
- More logging, enforce log formats consistency
- Rate limits for APIs
- Make periodic_job_cleanup sub-routine of general maintenance routine. - Should Memory be its owner?
- Conversation compression sub-routine, open questions:
  - recall_conversation skill: can it retrieve Chroma entries basing on data/distance
  - rebuild system prompt after compression is done - not really needed if it's being updated during restarts already
  - "saved=true/false" for summary entries, if close to edge - notify admin
- Tool: web_scrape_tool with Crawl4AI ([https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4](https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4))
- In group chats use reply rather than send_message
- Introduce conversation modes (doc/design/conversation_modes.md) and apply when delivering agent results
- Internal skill: [local_buddy_]small_talk
  - Gather in advance or lazily-collect facts on potential topics of interest and propose those for discussion with user

## Try

- Trafilatura as another extraction option
- _classify_intent could return 'pass' to replace CognitionCore.should_reply. And _classify_intent could have a better name, e.g. "decide_next_action"
- Regulate Еmotional state with system messages, instead of the system prompt (should those be acually saved?). 
- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message

## See

- No connection pooling for Redis - what's that?
- The winner's approach:
[https://github.com/idzivinskyi/bitgn-trustworthy-agent/tree/main](https://github.com/idzivinskyi/bitgn-trustworthy-agent/tree/main)
- Misplaced DTOs in `yoda/mind/memory/data/` (don't belong to memory persistence): - still true?
  - `pending_message.py` — perception/embodiment concept
  - `system_prompt.py` — mind-level
  - `emotional_state.py` — affect concept

# Backlog

```dataviewjs
const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
const priorityLabel = {
  critical: "🔴 critical",
  high:     "🟠 high",
  medium:   "🟡 medium",
  low:      "🟢 low"
};
const statusLabel = {
  "in-progress": "🔵 in-progress",
  "in-review":   "🟣 in-review",
  "blocked":     "🔴 blocked",
  "todo":        "⬜ todo",
  "done":        "✅ done"
};

const allEpics = dv.pages('"backlog"')
  .where(p => p.id && p.file.name === "epic");

const activeEpics = allEpics
  .where(p => p.status !== "done")
  .sort(p => priorityOrder[p.priority] ?? 99);

const comleteEpics = allEpics
  .where(p => p.status === "done")
  .sort(p => p.updated, "desc");

// ── Active epics ───────────────────────────────────────────────────────────
dv.header(2, "Active epics (" + activeEpics.length + ")");

if (activeEpics.length === 0) {
  dv.paragraph("_No epics._");
} else {
  dv.table(
    ["ID", "Title", "Tags", "Link", "Status", "Priority", "Created"],
    activeEpics.map(p => [
      p.id,
      p.title,
      p.tags,
      p.file.link,
      statusLabel[p.status]   ?? p.status,
      priorityLabel[p.priority] ?? p.priority,
      p.created
    ])
  );
}

// ── Complete epics ────────────────────────────────────────────────────────
dv.header(2, "Complete epics (" + comleteEpics.length + ")");

if (comleteEpics.length === 0) {
  dv.paragraph("_No epics._");
} else {
  dv.table(
    ["ID", "Title", "Tags", "Link", "Status", "Size", "Created"],
    comleteEpics.map(p => [
      p.id,
      p.title,
      p.tags,
      p.file.link,
      statusLabel[p.status]   ?? p.status,
      p.size,
      p.created
    ])
  );
}

const allTasks = dv.pages('"backlog"')
  .where(p => p.id && p.file.name === "task");

const activeTasks = allTasks
  .where(p => p.status !== "done")
  .sort(p => priorityOrder[p.priority] ?? 99);

const comleteTasks = allTasks
  .where(p => p.status === "done")
  .sort(p => p.updated, "desc");

// ── Active tasks ───────────────────────────────────────────────────────────
dv.header(2, "Active tasks (" + activeTasks.length + ")");

if (activeTasks.length === 0) {
  dv.paragraph("_No tasks._");
} else {
  dv.table(
    ["ID", "Title", "Epic", "Tags", "Link", "Status", "Priority", "Size", "Created"],
    activeTasks.map(p => [
      p.id,
      p.title,
      p.epic,
      p.tags,
      p.file.link,
      statusLabel[p.status]   ?? p.status,
      priorityLabel[p.priority] ?? p.priority,
      p.size,
      p.created
    ])
  );
}

// ── Complete tasks ────────────────────────────────────────────────────────
dv.header(2, "Complete tasks (" + comleteTasks.length + ")");

if (comleteTasks.length === 0) {
  dv.paragraph("_No tasks._");
} else {
  dv.table(
    ["ID", "Title", "Tags", "Link", "Status", "Size", "Created"],
    comleteTasks.map(p => [
      p.id,
      p.title,
      p.tags,
      p.file.link,
      statusLabel[p.status]   ?? p.status,
      p.size,
      p.created
    ])
  );
}
```

