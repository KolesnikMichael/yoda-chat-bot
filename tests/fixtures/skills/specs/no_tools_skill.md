---
name: no_tools_skill
description: A skill with no tools for testing.
purpose: Exercise a skill that has no tools.
when_to_use:
  - Tests that need a skill without tool bindings.
do_not_use_when:
  - Requests that require tool execution.
selection_examples:
  - '"answer without tools" -> use'
required_inputs: {}
tools: []
max_iterations: 2
---
# No Tools Skill

## Workflow
Just respond directly.
