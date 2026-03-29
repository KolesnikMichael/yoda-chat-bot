---
name: schedule_message
description: Schedule a one-time reminder message to be delivered at a specific time or after a delay.
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
2. Choose the scheduling mode:
   - **Relative delay** ("in 30 minutes", "через час"): call `schedule_message` with `delay_minutes`. No timezone needed.
   - **Absolute time** ("at 3 PM tomorrow", "завтра в 15:00"): requires timezone. Check user profile. If timezone is missing, call `ask_user` to ask for it. Then call `schedule_message` with year/month/day/hour/minute/timezone.
3. When you learn new user information (timezone, location) via ask_user, call `update_profile` to save it. You can call `update_profile` and `schedule_message` together in the same tool_calls.
4. If the tool returns success, set final_answer confirming the reminder.
5. If the tool returns an error, explain the issue in final_answer.

## Examples
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "delay_minutes": 30}}], "reasoning": "scheduling a relative reminder"}
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "year": 2026, "month": 3, "day": 21, "hour": 15, "minute": 0, "timezone": "Europe/Moscow"}}], "reasoning": "scheduling at absolute time"}
{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "What is your timezone?"}}], "reasoning": "need timezone for absolute time"}

## Completion
Stop when: reminder is scheduled and confirmed, OR an unrecoverable error occurred, OR max iterations reached.
