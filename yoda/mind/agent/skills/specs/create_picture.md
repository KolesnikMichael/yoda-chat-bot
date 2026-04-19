---
name: create_picture
description: Generate an image from the user's description using AI, send it to the chat, then the main assistant comments in character.
public: true
required_inputs:
  subject: "What to depict (style, scene, mood)"
tools:
  - text_to_image
  - image_to_text
  - send_picture
  - ask_user
max_iterations: 11
---
# Create Picture

## When to use
- User asks to draw, paint, generate, or create a picture or image
- User describes a visual they want (scene, character, style)

## Workflow
1. If the request is empty or hopelessly vague, call `ask_user` once to clarify what to depict.
2. From the task, formulate **one** concise **English-only** visual prompt (scene, subjects, style, mood, lighting). No meta-instructions to the model, no chit-chat. Pass it as `english_prompt` to `text_to_image` — translation and disambiguation are **your** job in this phase, not a separate tool.
3. **Important:** In each assistant message, call **at most one** tool. Do not batch tools whose inputs depend on a prior tool's output in the same `tool_calls` (e.g. `text_to_image` then `image_to_text` or `send_picture` in one step).
4. After `text_to_image` succeeds, read the returned **file path** (plain string). Call `image_to_text` with that exact `file_path` and obtain a detailed description of the generated image. If that description differs **significantly** from what you intended at step 2, go back to step 2 with an adjusted English prompt and generate again. Use **at most three** `text_to_image` calls in total.
5. Pick the best result and call `send_picture` with its `file_path` and `summary_for_chat`: a detailed description of the image, in the **same language as the user's task** (for the main chat model — **not** sent to Telegram as a caption).
6. Do not rely on long text printed on the image; the photo is sent **without caption**. The user's chat assistant will add a spoken reply afterward.

## Examples
{"tool_calls": [{"tool_name": "text_to_image", "arguments": {"english_prompt": "A small green frog wearing a Jedi robe on a swamp log at sunset, digital painting"}}], "reasoning": "single tool: English prompt ready for Pixazo"}

{"tool_calls": [{"tool_name": "image_to_text", "arguments": {"file_path": "/abs/path/.file_cache/gen_abc.png"}}], "reasoning": "verify generated image matches intent before sending"}

{"tool_calls": [{"tool_name": "send_picture", "arguments": {"file_path": "/abs/path/.file_cache/gen_abc.png", "summary_for_chat": "На картинке — лягушка в мантии джедая на бревне в закатном болоте, цифровая живопись; тёплый свет, детализированная шкура."}}], "reasoning": "send chosen file; detailed description in user's language for follow-up chat"}

{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "What should appear in the image — subject, style, or colors?"}}], "reasoning": "task too vague to generate"}

## Completion
The run ends when `send_picture` succeeds (`terminal` tool) or you return `final_answer` if generation is impossible.
