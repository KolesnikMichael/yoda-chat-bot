---
name: schedule_message
description: Schedule a reminder message (one-time or recurring) to be delivered at a specific time, after a delay, or on a cron schedule.
purpose: Deliver static user-specified reminder text at a later time.
when_to_use:
  - The payload is known now and should be delivered later once or repeatedly.
do_not_use_when:
  - The payload requires fresh data, web search, computation, or monitoring at trigger time.
selection_examples:
  - '"Каждый день в 9 напоминай принять витамины" -> use'
  - '"Каждый день в 9 присылай актуальную погоду" -> do not use; search_web'
required_inputs:
  reminder_text: "What to remind the user about"
  time: "When to deliver — either a relative delay or an absolute time"
tools:
  - schedule_message
  - ask_user
  - update_profile
max_iterations: 4
---
# Schedule Message

## When to use
User asks to be reminded about something, to schedule a message, or to send a notification at a specific time. Examples: "remind me in 30 minutes to call mom", "send me a message at 3 PM tomorrow", "напомни мне через час купить молоко".

## Workflow
1. Parse the user's request to extract **reminder_text** (what to remind about) and **time** (when).
2. Choose the scheduling mode (exactly one):
   - **Relative delay** ("in 30 minutes", "через час"): call `schedule_message` with `delay_minutes`. No timezone needed.
   - **Absolute time** ("at 3 PM tomorrow", "завтра в 15:00"): requires timezone. Check user profile. If timezone is missing, call `ask_user` to ask for it. Then call `schedule_message` with year/month/day/hour/minute/timezone.
   - **Recurring** ("every Monday at 9:00", "каждый день в 9 утра"): call `schedule_message` with `cron` (5-field crontab) and `timezone` (from profile or ask_user). Example: Monday 09:00 → `cron: "0 9 * * 1"`.
3. Build `reminder_text` with the right addressee semantics:
   - If user asks to remind a specific person ("напомни мне", "remind me"), include the addressee in `reminder_text` when needed for group clarity.
   - If user asks to remind everyone ("напомни нам", "remind us"), use group wording in `reminder_text` and avoid targeting one user.
   - In private chats, keep `reminder_text` concise and natural.
4. When you learn new user information (timezone, location) via ask_user, call `update_profile` to save it. You can call `update_profile` and `schedule_message` together in the same tool_calls.
5. If the tool returns success, set final_answer confirming the reminder.
6. If the tool returns an error, explain the issue in final_answer.

## Examples
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "delay_minutes": 30}}], "reasoning": "scheduling a relative reminder"}
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "year": 2026, "month": 3, "day": 21, "hour": 15, "minute": 0, "timezone": "Europe/Moscow"}}], "reasoning": "scheduling at absolute time"}
{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "What is your timezone?"}}], "reasoning": "need timezone for absolute time"}
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "take vitamins", "cron": "0 9 * * 1", "timezone": "Europe/Moscow"}}], "reasoning": "recurring weekly reminder"}

## Completion
Stop when: reminder is scheduled and confirmed, OR an unrecoverable error occurred, OR max iterations reached.
