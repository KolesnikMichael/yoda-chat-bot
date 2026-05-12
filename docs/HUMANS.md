# Human Actions to Take
## DROP
- Stop calculating chat_type each time - it doesn't change

## ADD
- schedule_message: add recurrency
- Retry after 429 where needed
- Scheduling jobs: Daylight saving is unlikely taken into account (and there are countries that do not use it)
- Admin notifications
- _classify_intent returns "chat" but it's never handled. It should be handled explicitly, and last elif in Mind.process_message_batch should log WARNING or something
- Record skill usages in Chat.history
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
- Tool: web_scrape_tool with Crawl4AI (https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4)
- Skill schedule_task: run skill with certain parameters periodically or just once
- In group chats use reply rather than send_message
- Introduce conversation modes (docs/conversation_modes.md) and apply when delivering agent results
- Internal skill: [local_buddy_]small_talk
  - Gather in advance or lazily-collect facts on potential topics of interest and propose those for discussion with user

## TRY
- Skill flavours/hierarchy: search web could have a number of options (sub-specs with specific workflow/sources/hints), depending on the topic. - Actuall, should this be stored in catalog, or in user preferences - like agent updating user_profile with object skill_preferences > web_search > weather > accuweather.com?
- Trafilatura as another extraction option
- _classify_intent could return 'pass' to replace CognitionCore.should_reply. And _classify_intent could have a better name, e.g. "decide_next_action"
- Regulate Еmotional state with system messages, instead of the system prompt (should those be acually saved?). 
- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message
- Switch to another Vision provider, options:
  - https://openrouter.ai/google/gemma-4-31b-it:free
  - https://openrouter.ai/qwen/qwen-vl-plus
  - https://openrouter.ai/qwen/qwen3-vl-235b-a22b-thinking

## DISCOVER
- No connection pooling for Redis - what's that?
- The winner's approach:
  https://github.com/idzivinskyi/bitgn-trustworthy-agent/tree/main
- ReAct loop doesn't survive tool crashes like exception when using ask_user - still true?
- Misplaced DTOs in `yoda/mind/memory/data/` (don't belong to memory persistence): - still true?
  - `pending_message.py` — perception/embodiment concept
  - `system_prompt.py` — mind-level
  - `emotional_state.py` — affect concept