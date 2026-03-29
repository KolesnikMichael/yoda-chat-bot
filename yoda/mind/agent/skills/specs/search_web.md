---
name: search_web
description: Search the web for information, verify facts, or research a topic using web search and content extraction.
required_inputs:
  topic: "What the user wants to find out or verify"
tools:
  - web_search
  - web_extract
  - ask_user
max_iterations: 6
---
# Search Web

## When to use
- User asks for current/factual information about a topic
- User asks to verify or check a fact
- You need to back up your next statement with up-to-date facts

## Workflow
1. Build a search query in the same language as the user's task. If the task is too short or vague, expand it with relevant keywords before searching.
2. Call `web_search` with the query.
3. If results are insufficient, extract content from one or more relevant URLs with `web_extract`.
4. Synthesize findings into a coherent answer.
5. If gaps remain and iterations allow, refine or narrow the search query.

## Examples
{"tool_calls": [{"tool_name": "web_search", "arguments": {"query": "курс доллара к рублю сегодня"}}], "reasoning": "searching in Russian to match the task language"}
{"tool_calls": [{"tool_name": "web_extract", "arguments": {"urls": ["https://example.com/article"]}}], "reasoning": "extracting full content from a relevant URL"}
{"final_answer": "According to search results, ...", "reasoning": "sufficient data collected"}

## Completion
Stop when: enough data for a comprehensive answer, OR max iterations reached.
