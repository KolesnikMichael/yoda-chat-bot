---
name: search_web
description: Search the web for current information to deliver results immediately, or schedule web searches for ongoing monitoring.
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

## Workflow
1. If the user wants **deferred or recurring** execution (e.g. "every morning", "at 6 PM", "watch the dollar rate daily") — clarify topic, schedule, and timezone (`ask_user` / `update_profile` if needed). Then call `schedule_task` with `skill_name=search_web`, a **self-contained** `distilled_task` (what to find, in which language), and a short `description` for the jobs list. Use `cron`, `delay_minutes`, or absolute date/time fields. **Do not** run `web_search` in the same run — `schedule_task` is terminal.
2. Build a search query in the same language as the user's task. If the task is too short or vague, expand it with relevant keywords before searching.
3. Call `web_search` with the query.
4. If results are insufficient, extract content from one or more relevant URLs with `web_extract`.
5. Synthesize findings into a coherent answer.
6. If gaps remain and iterations allow, refine or narrow the search query.

## Examples
{"tool_calls": [{"tool_name": "schedule_task", "arguments": {"skill_name": "search_web", "distilled_task": "Find today's USD to RUB exchange rate and summarize briefly in Russian.", "description": "Daily USD/RUB rate check", "cron": "0 9 * * *", "timezone": "Europe/Moscow"}}], "reasoning": "recurring search — schedule only, do not search now"}
{"tool_calls": [{"tool_name": "web_search", "arguments": {"query": "курс доллара к рублю сегодня"}}], "reasoning": "searching in Russian to match the task language"}
{"tool_calls": [{"tool_name": "web_extract", "arguments": {"urls": ["https://example.com/article"]}}], "reasoning": "extracting full content from a relevant URL"}
{"final_answer": "According to search results, ...", "reasoning": "sufficient data collected"}

## Completion
Stop when: enough data for a comprehensive answer, OR max iterations reached.
