# Human Actions to Take
## Fix
- ReAct loop doesn't survive tool crashes like exception when using ask_user
- Misplaced DTOs in `yoda/mind/memory/data/` (don't belong to memory persistence):
  - `pending_message.py` — perception/embodiment concept
  - `system_prompt.py` — mind-level
  - `emotional_state.py` — affect concept

## Improve
- Double-check changes:
  - conversations temporary persistence during service restarts
  - extended context (recent messages) is now provided for intent classification and task distillation (the last one caused significant changes in ReAct loop and AgentProvider)
- schedule_message: add recurrency
- Stop calculating chat_type each time - it doesn't change
- Add auto-retry after 429 (not) everywhere?
- Scheduling jobs: Daylight saving is unlikely taken into account (and there are countries that do not use it)
- Error handling:
  - network errors to Telegram
  - Redis failures
  - speech/vision/LLM errors
  - file operations
- Add more logging, enforce log formats consistency
- Add rate limits for APIs

## Implement
- Make periodic_job_cleanup sub-routine of general maintenance routine. - Should Memory be its owner?
- Conversation compression sub-routine: Messages compression/archiving/drop off:
  - Triggers:
    - Size-driven: over 300 messages
    - Time-driven (distributed scheduled run): check every hour, compress only conversations that have were active since last compression and were quiet since last run
  - Entries to compress: 1/2 of oldest but no less than 30
  - Non-linear compression: exponential or outlook-style
  - Alternatively, use diary-style compression with skill-like catalog of records with frontmatters with date/topic.
    - Research persistence options: Redis, MDs, vector db, or Telegram itself (if it's possble to read a range of messages)
  - Update chat and user_profiles from the archived messages
  - Re-insert users metadata if removed during routine
  - Rebuild system prompt with chat metadata after routine is done
- Add more context to the Conversation (critical after conversation compression is in place):
  - Load Chats metadata when building system prompt
  - Lazily inject user profile into the conversation with the system message when (re-)joins it
- Tool: web_scrape_tool with Crawl4AI (https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4)
- Skill schedule_task: run skill with certain parameters periodically or just once
- In group chats use reply rather than send_message
- Introduce conversation modes (docs/conversation_modes.md)
- Internal skill: [local_buddy_]small_talk
  - Gather in advance or lazily-collect facts on potential topics of interest and propose those for discussion with user

## Refactor
- _classify_intent returns "chat" but it's never handled. It should be handled explicitly, and last elif in Mind.process_message_batch should log WARNING or something

## Consider
- Skill flavours/hierarchy: search web could have a number of options (sub-specs with specific workflow/sources/hints), depending on the topic. Should this be stored in catalog, or in user preferences?
- Trafilatura as another extraction option
- _classify_intent could return 'pass' to replace CognitionCore.should_reply. And _classify_intent could have a better name, e.g. "decide_next_action"
- Regulate Еmotional state with system messages, instead of the system prompt (should those be acually saved?). 
- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message
- Switch to another Vision provider. Options:
  - https://openrouter.ai/google/gemma-4-31b-it:free
  - https://openrouter.ai/qwen/qwen-vl-plus
  - https://openrouter.ai/qwen/qwen3-vl-235b-a22b-thinking

## Figure out
- No connection pooling for Redis - what's that?
- The winner's approach:
  https://github.com/idzivinskyi/bitgn-trustworthy-agent/tree/main