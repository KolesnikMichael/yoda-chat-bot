# Yoda Chatbot

Telegram chatbot with LLM integration, memory, emotional dynamics, and agentic capabilities.

## Architecture: IODA

Every class belongs to exactly one IODA category. Enforce by naming convention:

| Category | Naming | What it does | Constraints |
|---|---|---|---|
| Integration | bare noun (`Mind`, `Perception`) | Orchestrates data flow between Operations | Only calls Operations/Integrations + await. **No business logic.** |
| Core | `*Core` | Sync, static. Pure logic, transforms, decisions | Depends only on Data. |
| Provider | `*Provider` | Async. Adapts infrastructure (DB, LLM, scheduler) | May depend on API. |
| Portal | `*Portal` | Async. Adapts user-facing interfaces | May depend on API. |
| Data | — | DTOs, dataclasses | Minimal logic (accessors, consistency). No functional deps. |
| API | — | Async façades for external services | Side effects. Mocked in tests. |

**Hard rules:**
- Operations (Core/Provider/Portal) **never** depend on other Operations or Integrations.
- If Operation A needs data from Operation B, the Integration passes it as a parameter.
- A file may contain both a Core and Provider class (e.g. `memory.py` → `MemoryCore` + `MemoryProvider`).

## Project layout

Anthropomorphic separation of concerns — not by IODA category:

```
yoda/
  yoda_chat_bot.py    # Wiring + startup
  api/                # External service façades (LLM, Telegram, Redis, Tavily, scheduler, speech)
  embodiment/         # Telegram portal (receives updates, sends replies)
  mind/
    mind.py           # Top-level Integration: routes intents, orchestrates pipelines
    perception/       # Text/voice/photo intake
    memory/           # Conversation + user profile persistence, data models
    cognition.py      # Intent classification (agent_task / chat / pass), text normalization
    affect.py         # Emotional state updates, mood influence on prompts
    agent/            # Agentic capabilities → see agent/AGENTS.md
```

## Coding style

- `@staticmethod` on methods that don't need instance state
- Private names: `_name` (PEP 8)
- Explicit type hints on all functions and methods
- f-strings for concatenation
- Fail fast on config/validation — no lenient fallbacks
- `logger.debug` for anything with user data (messages, profile, jobs)
- `asyncio.gather()` when 2+ Providers/Portals have independent inputs

## Workflow

- TDD where applicable and reasonable
- Run tests before proposing changes: `python -m pytest` from project root (venv: `.venv/bin/python`)
