---
name: manage_user_data
description: Show or delete all stored user data (profile, jobs, personal info) across all chats.
public: false
purpose: Show or permanently delete all stored data for the user across chats.
when_to_use:
  - The user requests a data export, asks what is stored about them, or asks to delete/forget all their stored data.
do_not_use_when:
  - The user merely corrects one profile field or asks to cancel jobs.
  - The user says not to mention one conversational topic.
selection_examples:
  - '"Покажи всё, что ты хранишь обо мне" -> use'
  - '"Отмени мои напоминания" -> do not use; manage_jobs'
required_inputs:
  action: "What the user wants — view their data or delete everything"
tools:
  - get_user_data
  - delete_user_data
  - ask_user
max_iterations: 6
---
# Manage User Data

## When to use
User asks to see what data is stored about them, requests a data export, or asks to delete all their personal data. Examples: "what do you know about me", "покажи мои данные", "delete my data", "forget me", "удали всё что ты обо мне знаешь".

## Workflow
1. Call `get_user_data` to retrieve everything stored for this user across all chats.
2. Based on the user's intent:
   - **View data**: present the retrieved data in final_answer. Format it clearly: user record, profiles per chat, active scheduled jobs.
   - **Delete data**: first call `ask_user` to warn that **all** their data will be permanently erased — profile, preferences, scheduled reminders, private chat metadata in Redis, and the in-memory private DM transcript (group chat history in memory is not cleared). They will be completely "forgotten". After the user confirms, call `delete_user_data`. If the user declines, set final_answer acknowledging their decision.
3. After deletion, set final_answer confirming what was removed.

## Examples
{"tool_calls": [{"tool_name": "get_user_data", "arguments": {}}], "reasoning": "retrieving all stored user data"}
{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "This will permanently delete all your data — profile, preferences, scheduled reminders, everything across all chats. You will be completely forgotten. Are you sure?"}}], "reasoning": "warning user before irreversible deletion"}
{"tool_calls": [{"tool_name": "delete_user_data", "arguments": {}}], "reasoning": "user confirmed deletion"}

## Completion
Stop when: data is shown, or deletion is confirmed/declined, OR an unrecoverable error occurred, OR max iterations reached.
