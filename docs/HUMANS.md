# Human Actions to Take
## Figure out
- How tools specs/descriptions are currently stored, do they have examples, how this information is added to the context if at all.
- No connection pooling for Redis - what's that?

## Fix
- ReAct loop doesn't survive tool crashes like exception when using ask_user

## Improve
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
- Make periodic_job_cleanup sub-routine of general maintenance routine. Add sub-routine for updating chat and user profiles. Randomize sub-routines start time to distribute load. - Which module should own those sub-routines? Memory?
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
    - https://www.pixazo.ai/api/pricing-plan

## Refactor
- _classify_intent returns "chat" but it's never handled. It should be handled explicitly, and last elif in Mind.process_message_batch should log WARNING or something

## Consider
- Skill flavours/hierarchy: search web could have a number of options (sub-specs with specific workflow/sources/hints), depending on the topic. Should this be stored in catalog, or in user preferences?
- Trafilatura as another extraction option
- Use Crawl4AI (https://medium.com/@speaktoharisudhan/crawling-with-crawl4ai-the-open-source-scraping-beast-9d32e6946ad4) for regular advanced scraping
- Add fact-checking for Yoda replies
- _classify_intent could return 'pass' to replace CognitionCore.should_reply. And _classify_intent could have a better name, e.g. "decide_next_action"
- Add agent.py as sub-integration for agent entities - BUT: currently the provided context is too limited for this decision. Actually it appears limited for intent classification as well: consider an example where intent is unfolding in series of replies. Solution would be to provide not just the last messages, but preceeding ones as well. 
- ReactLoop._format_profile_context: not that much of information just yet. For digests there should be more
- It seems that the only reason why system_prompt is passed to every add_conversation_line is because get_emotional_state is supposed to affect it. Еmotional state will be regulated in system messages, not with the system prompt so that Yoda LLM could see it's own emotional dynamics. On the other hand it that could be used for lazy-adding chat/user profiles to the system prompt.
- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message
- Schema migration inside `update_chat_info` is a nice touch but a bit dense inside a single method; could be refactored into versioned migrators.
- Switch to another Vision provider. Options:
  - OCR.space API
  - Google Cloud Vision OCR
  - OCRAPI.cloud
  - AI Universal OCR API (RapidAPI)