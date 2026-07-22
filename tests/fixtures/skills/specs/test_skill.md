---
name: test_skill
description: A test skill for unit tests.
purpose: Exercise catalog loading in unit tests.
when_to_use:
  - Running automated tests that need a public skill with tools.
do_not_use_when:
  - Production user requests that need a real skill.
selection_examples:
  - '"run unit test" -> use'
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
