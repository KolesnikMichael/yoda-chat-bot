---
name: test_skill
description: A test skill for unit tests.
required_inputs:
  query: "The search query"
tools:
  - web_search
  - ask_user
max_iterations: 3
---
# Test Skill

## When to use
When running tests.

## Workflow
1. Search for the query using `web_search`.
2. Return the result.
