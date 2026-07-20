---
name: search_web
description: Search the web for current information to deliver results immediately, or schedule web searches for ongoing monitoring.
purpose: Retrieve current external information now or run a fresh web search at a scheduled time.
when_to_use:
  - The user asks for current/changing externally verified information.
  - A deferred or recurring result must be recomputed at trigger time.
do_not_use_when:
  - The user only wants static text delivered later.
  - The question is conceptual and answerable without current external data.
selection_examples:
  - '"Какая погода завтра?" -> use'
  - '"Каждое утро буди прогнозом с AccuWeather" -> use and schedule a search_web task'
  - '"Через час напомни проверить погоду" -> do not use; schedule_message'
required_inputs:
  topic: "What the user wants to find out, verify, or monitor"
optional_inputs:
  schedule: "When the search should run (specific time, delay) and how often to repeat it (e.g. daily, weekly, every 6 hours)"
  notify_condition: "What qualifies as a meaningful update worth notifying about"
  sources: "Preferred websites or source types"
tools:
  - web_search
  - web_extract
  - schedule_task
  - ask_user
  - update_profile
max_iterations: 8
---
# Search Web

## When to use
- User asks for current or factual information
- User asks to verify or check a fact
- You need up-to-date information before responding
- User wants deferred or periodic searches
- User asks to track news, weather, prices, etc. over time

## Precedence
Apply source policy in this fixed order:
1. **Strict request constraints** (`request_constraints.strict_source_domains`) — mandatory; never widen or omit.
2. **Soft request preferences** (`request_constraints.soft_source_domains`) — prefer these when no strict constraint applies; may fall back if they yield nothing useful.
3. **Stored active-skill preferences** (`skill_preferences` for `search_web`) — durable defaults from the profile.
4. **Skill defaults** — unrestricted search when none of the above apply.

One-off “only from X” requests stay in `request_constraints` / `distilled_task`. Persist a preference only when the user explicitly wants it from now on, via `update_profile` with `skill_preferences_to_add.search_web` (never `web_search`).

## Workflow
1. If the user wants **deferred or recurring** execution (e.g. "every morning", "at 6 PM", "watch the dollar rate daily") — clarify topic, schedule, and timezone (`ask_user` / `update_profile` if needed). Then call `schedule_task` with `skill_name=search_web`, a **self-contained** `distilled_task` (what to find, language, output needs, and strict/soft source choices), and a short `description` for the jobs list. Core injects `request_constraints` into the job; do not invent a different sidecar. Use `cron`, `delay_minutes`, or absolute date/time fields. **Do not** run `web_search` in the same run — `schedule_task` is terminal.
2. Build a search query in the same language as the user's task. If the task is too short or vague, expand it with relevant keywords before searching.
3. Call `web_search` with the query. When strict source domains apply, always pass the exact `include_domains` list (or omit it so Core injects the same exact list). On refinements, keep an equal restriction — never empty, omit, or widen domains under a strict constraint.
4. If results are insufficient, extract content from one or more relevant URLs with `web_extract` (hosts must equal or sit under an allowed strict host when strict policy applies).
5. Synthesize findings into a coherent answer.
6. If gaps remain and iterations allow, refine or narrow the search query **while retaining the same strict `include_domains`**. Soft preferences may fall back only when no strict constraint applies.
7. If there are no usable results under a strict restriction, report the limitation and ask whether to widen — never retry with empty/omitted/broader domains.

## Examples
{"tool_calls": [{"tool_name": "schedule_task", "arguments": {"skill_name": "search_web", "distilled_task": "Find today's Saint Petersburg forecast in Russian using only accuweather.com.", "description": "Daily AccuWeather forecast", "cron": "0 9 * * *", "timezone": "Europe/Moscow"}}], "reasoning": "recurring constrained search — schedule only"}
{"tool_calls": [{"tool_name": "web_search", "arguments": {"query": "прогноз погоды Санкт-Петербург", "include_domains": ["accuweather.com"]}}], "reasoning": "strict source — include_domains mandatory"}
{"tool_calls": [{"tool_name": "update_profile", "arguments": {"fields": {"skill_preferences_to_add": {"search_web": ["weather forecast: accuweather.com"]}}}}], "reasoning": "user said from now on prefer AccuWeather"}
{"tool_calls": [{"tool_name": "web_extract", "arguments": {"urls": ["https://www.accuweather.com/en/ru/saint-petersburg"]}}], "reasoning": "extracting under allowed host"}
{"final_answer": "According to search results, ...", "reasoning": "sufficient data collected"}

## Completion
Stop when: enough data for a comprehensive answer, OR max iterations reached, OR a strict search returned no usable results and the user must decide whether to widen.
