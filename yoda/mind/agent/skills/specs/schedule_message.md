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
   - **Relative delay** ("in 30 minutes", "через час"): call `schedule_message` with `delay_minutes`. No timezone needed and no timezone clarification.
   - **Absolute time** ("at 3 PM tomorrow", "завтра в 15:00"): year/month/day/hour/minute plus an explicit valid IANA `timezone`.
   - **Recurring** ("every Monday at 9:00", "каждый день в 9 утра"): `cron` (5-field crontab) plus an explicit valid IANA `timezone`. Example: Monday 09:00 → `cron: "0 9 * * 1"`.
3. For **absolute or recurring** local time, resolve IANA timezone identity in this order (do not ask while a higher step already resolves it):
   1. A valid IANA name explicitly supplied in the current request — copy it into the scheduling arguments.
   2. A valid profile timezone accepted as IANA — copy it into the scheduling arguments (do not rely on hidden profile fallback).
   3. An unambiguous named location in the task or profile — infer the IANA name, call `update_profile` with both `timezone` and `location`, and pass that same explicit timezone to `schedule_message`. Batch the two tools only when every scheduling argument is already resolved (scheduling must not depend on the profile write completing).
   4. Otherwise one `ask_user` asking for city/region or an IANA timezone name. Never ask for the user's current clock. Never accept a bare UTC offset (`+03:00`, `UTC+03:00`) as timezone identity.
4. Build `reminder_text` with the right addressee semantics:
   - If user asks to remind a specific person ("напомни мне", "remind me"), include the addressee in `reminder_text` when needed for group clarity.
   - If user asks to remind everyone ("напомни нам", "remind us"), use group wording in `reminder_text` and avoid targeting one user.
   - In private chats, keep `reminder_text` concise and natural.
5. Call `schedule_message` with a self-contained explicit timezone for absolute/cron modes. If the tool returns success, set final_answer confirming the reminder.
6. If the tool returns an error, explain the issue in final_answer.

## Examples
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "delay_minutes": 30}}], "reasoning": "relative delay — no timezone clarification"}
{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "year": 2026, "month": 3, "day": 21, "hour": 15, "minute": 0, "timezone": "Europe/Moscow"}}], "reasoning": "absolute time with explicit or reused valid IANA timezone"}
{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "Which city or IANA timezone should I use (for example Europe/Berlin)?"}}], "reasoning": "ambiguous or missing location — one direct clarification"}
{"tool_calls": [{"tool_name": "update_profile", "arguments": {"fields": {"timezone": "Europe/Moscow", "location": "Saint Petersburg"}}}, {"tool_name": "schedule_message", "arguments": {"reminder_text": "take vitamins", "cron": "0 9 * * *", "timezone": "Europe/Moscow"}}], "reasoning": "inferred IANA from unambiguous location — persist and schedule with the same explicit timezone"}
{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "Which city or IANA timezone should I use? A UTC offset like +03:00 is not enough."}}], "reasoning": "reject offset-only identity and ask for city/region or IANA"}

## Completion
Stop when: reminder is scheduled and confirmed, OR an unrecoverable error occurred, OR max iterations reached.
