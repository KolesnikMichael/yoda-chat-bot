# Human Actions to Take
## Figure out
- No connection pooling for Redis - what's that?

## Fix
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
- Skill: schedule_task
- Skill: draw_picture
- In group chats rather use reply than send_message
- Tool: web_scrape_tool with Crawl4AI (https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4)
- Make periodic_job_cleanup sub-routine of general maintenance routine. Add sub-routine for updating chat and user profiles. Randomize sub-routines start time to distribute load (for instance, make it running every hour, but update only profiles that belong to entities that were inactive since last run (that is having: utc_now-2 < update_time < utc_now-1). Questions:
   - Which module should own those sub-routines? Could it be Memory?
- Load chat profile when building system prompt
- Add user profile to system prompt when user sends first message
- Add create_picture skill. Options:
  - Cloudflare Workers AI
    - https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-lightning/
    - https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-base-1.0/
    - https://developers.cloudflare.com/workers-ai/models/stable-diffusion-v1-5-img2img/
    - https://developers.cloudflare.com/workers-ai/models/stable-diffusion-v1-5-inpainting/
    - https://developers.cloudflare.com/workers-ai/models/dreamshaper-8-lcm/
  - AI Horde (community API)
    - https://stablehorde.net/guis#section-guis-image
  - Pixazo Free API Hub
    - https://www.pixazo.ai/models/flux
    - https://www.pixazo.ai/models/stable-diffusion
    - https://www.pixazo.ai/models/sdxl

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