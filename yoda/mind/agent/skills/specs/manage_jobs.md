---
name: manage_jobs
description: List, inspect, or cancel the user's scheduled jobs (reminders, recurring tasks, etc).
required_inputs:
  action: "What the user wants to do — list jobs, cancel a specific job, or cancel all"
tools:
  - list_jobs
  - cancel_job
  - ask_user
max_iterations: 6
---
# Manage Jobs

## When to use
User wants to see, check, or cancel their scheduled jobs. Examples: "what reminders do I have", "show my scheduled messages", "cancel my reminder about calling mom", "отмени все мои напоминания", "какие у меня запланированные задачи".

## Workflow
1. Call `list_jobs` to retrieve the current list of active jobs for this chat.
2. Based on the user's intent:
   - **List/inspect**: present the jobs list in final_answer.
   - **Cancel specific**: identify the target job_id from the list and call `cancel_job` with that job_id. If the user's description matches multiple jobs, call `ask_user` to clarify which one.
   - **Cancel all**: call `cancel_job` for each job_id from the list. You can issue multiple cancel_job calls in a single tool_calls array.
3. After cancellation(s), set final_answer confirming what was cancelled.
4. If `list_jobs` returns no active jobs, set final_answer informing the user.

## Completion
Stop when: the user's request is fulfilled (list shown or job(s) cancelled), OR an unrecoverable error occurred, OR max iterations reached.
