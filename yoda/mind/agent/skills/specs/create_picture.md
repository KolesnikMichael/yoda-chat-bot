---
name: create_picture
description: Generate an image from the user's description using AI, send it to the chat, then the main assistant comments in character.
public: true
required_inputs:
  subject: "What to depict (style, scene, mood)"
tools:
  - text_to_image
  - send_picture
  - ask_user
max_iterations: 8
---
# Create Picture

## When to use
- User asks to draw, paint, generate, or create a picture or image
- User describes a visual they want (scene, character, style)

## Workflow
1. If the request is empty or hopelessly vague, call `ask_user` once to clarify what to depict.
2. From the task, formulate **one** concise **English-only** visual prompt (scene, subjects, style, mood, lighting). No meta-instructions to the model, no chit-chat. Pass it as `english_prompt` to `text_to_image` — translation and disambiguation are **your** job in this phase, not a separate tool.
3. **Important:** In each assistant message, call **at most one** tool. Never batch `text_to_image` and `send_picture` in the same `tool_calls` — the second needs the file path from the first.
4. After `text_to_image` succeeds, read the returned **file path** (plain string). Call `send_picture` with that exact `file_path` and a short `summary_for_chat` in the **same language as the user's task** (what was drawn, for the main chat model — this is **not** sent to Telegram).
5. Do not put long text on the image; the photo is sent **without caption**. The user's chat assistant will add a spoken reply afterward.

## Examples
{"tool_calls": [{"tool_name": "text_to_image", "arguments": {"english_prompt": "A small green frog wearing a Jedi robe on a swamp log at sunset, digital painting"}}], "reasoning": "single tool: English prompt ready for Pixazo"}

{"tool_calls": [{"tool_name": "send_picture", "arguments": {"file_path": "/abs/path/.file_cache/gen_abc.png", "summary_for_chat": "Лягушка-джедай на болоте на закате"}}], "reasoning": "send file after generation; summary for follow-up chat in user's language"}

{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "What should appear in the image — subject, style, or colors?"}}], "reasoning": "task too vague to generate"}

## Completion
The run ends when `send_picture` succeeds (`terminal` tool) or you return `final_answer` if generation is impossible.
