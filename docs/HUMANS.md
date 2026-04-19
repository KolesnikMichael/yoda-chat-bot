# Human Actions to Take
## Figure out
- No connection pooling for Redis - what's that?

## Fix
- Problems with Skill create_picture: 
  1. Yoda is hallucinating about the picture created by agent because he has no description of it.
  2. When tool is failig Yoda suggests extended user's description as a substitude.
  3. The quality of created picture is often suboptimal.
- How to address:
  1. Extend the skill with the image-to-text step (new tool using the same API as VisionProvider is needed)
  2. If the discription differs significantly from that of the user, return to skill's step 2 and  slightly adjust generation prompt. Make no more than three generation attempts, then choose the best matching picture and send it to chat.
  - Add the description of the sent picture in the system prompt
- ReAct loop doesn't survive tool crashes like exception when using ask_user

## Improve
- Stop calculating chat_type each time - it doesn't change
- Scheduling jobs: Daylight saving is unlikely taken into account (and there are countries that do not use it)
- Calculating timezone can be done when user provides his current time - add this hint to skill
- Error handling:
  - network errors to Telegram
  - Redis failures
  - speech/vision/LLM errors
  - file operations
- Add more logging, enforce log formats consistency
- Add rate limits for APIs

## Implement
- [internall skill] Conversation compression:
  - Triggers:
    - Size over 300 messages
    - Scheduled run
  - Entries to compress: 1/2 of oldest but no less than 30
  - Non-linear compression: exponential or outlook-style
  - Alternatively, use diary-style compression with skill-like catalog of records with frontmatters with date/topic.
    - Research persistence techniques: Redis, MDs, vector db
  - Rebuild system prompt after compression is done
  - Re-insert users metadata if removed during compression
- Internal skill: [local_buddy_]small_talk
  - Gather in advance or lazily-collect facts on potential topics of interest and propose those for discussion with user
- Skill: schedule_task
- In group chats rather use reply than send_message
- Tool: web_scrape_tool with Crawl4AI (https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4)
- Make periodic_job_cleanup sub-routine of general maintenance routine. Add sub-routine for updating chat and user profiles. Randomize sub-routines start time to distribute load (for instance, make it running every hour, but update only profiles that belong to entities that were inactive since last run (that is having: utc_now-2 < update_time < utc_now-1). Questions:
   - Which module should own those sub-routines? Could it be Memory?
- Add more context to the Conversation (critical after compression is in place):
  - Load Chats metadata (history) when building system prompt
  - Add user profile to system prompt or insert it with the system message when user sends first message

## Refactor
- _classify_intent returns "chat" but it's never handled. It should be handled explicitly, and last elif in Mind.process_message_batch should log WARNING or something

## Consider
- Skill flavours/hierarchy: search web could have a number of options (sub-specs with specific workflow/sources/hints), depending on the topic. Should this be stored in catalog, or in user preferences?
- Trafilatura as another extraction option
- Add fact-checking for Yoda replies
- _classify_intent could return 'pass' to replace CognitionCore.should_reply. And _classify_intent could have a better name, e.g. "decide_next_action"
- Provide not just the last messages, but preceeding ones as well (current approach doesn't work when previous skill outcome isn't satisfactory)
- Regulate Еmotional state with system messages, instead of the system prompt (should those be acually saved?). 
- Lazy-adding chat/user profiles to the system prompt/messages
- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message
- Switch to another Vision provider. Options:
  - OCR.space API
  - Google Cloud Vision OCR
  - OCRAPI.cloud
  - AI Universal OCR API (RapidAPI)