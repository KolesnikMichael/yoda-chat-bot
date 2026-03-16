# IODA architecture guide, coding style and more for Yoda chatbot

## Context
This project is a Telegram chatbot with LLM integration, memory, and planned emotional dynamics and agentic capabilities (web research, cron triggers, site watching, group chat).

## Architectural Approach: IODA + Hexagonal Hybrid
This project leverages the combination of two design patterns: IODA architecture for top-level workflows of the application, and Hexagonal architecture for agentic sub-workflows.

### Top-level: IODA Architecture
There are two key differences between IODA and other widely adopted Hexagonal, Onion and Clean architectures:
 - IODA focuses more on minimizing functional depedencies by strictly following this principle: "Functions can be either Integrations or Operations". Integration function is a function composed only of calls to functions in the same code base. Operation function is a function composed only of calls to functions in another code base (i.e. standard/external library functions, etc)."
 - IODA less strictly follows dependency inversion principle: "inner" Operations may depend on "outside" data or external services.

**IODA separates concerns using these four categories:**

---
| Layer | Role | Rules |
|-------|------|-------|
| **I** — Integration | Orchestrates pipelines, composes workflows | Only calls to Operations or other Integrations and then awaits. Pure data flow. No business logic. |
| **O** — Operation | Divides into three sub-types: </br> **Core** (sync, static): pure logic, transformations, decisions — independent of the environment, </br> **Portal** (async): adapters facing other software or users, </br> **Provider** (async): adapters facing services or infrastructure like databases or system timer. | Core depends only on Data. Portals and Providers may also depend on API. Operations cannot depend on other Operations or Integrations. |
| **D** — Data | Data structures / DTOs to be used by Operations to exchange data | Minimal logic only (data consistency, accessors). No dependencies on functional modules. |
| **A** — API | Represents services/infrastructure outside the application | All `async def`. Always behind a thin façade. Side effects. Mocked in tests. |
---

**Key rules:**
- **No functional dependencies between Operations.** If Op A needs data from Op B — the Integration passes it explicitly as a parameter.
- **An Integration may call other Integrations** to compose complex workflows from simpler pipelines. Each sub-Integration follows the same rules: no business logic, only calls and awaits.
- Class naming convention: `*Core` for Core operations, `*Provider` for Providers, `*Portal` for Portals. This makes the IODA sub-type immediately visible from the class name.

### Inside Agent Module: Hexagonal Architecture
TBD

## Project Structure
Project structure follows anthropomorphic separation of concerns rather than following IODA categories. For example, memory.py combines Operation and Provider functions.

```
yoda_chat_bot.py        # Wires everything, starts event loop. Then binds embodiment to mind (async)

api/
  llm_api.py            # API (async): facade for LLM APIs (language, vision)
  speech_api.py         # API (async): speech-to-text conversion using Google library
  storage_api.py        # API (async): API for Redis storage
  telegram_api.py       # API (async): facade for Telegram API

embodiment/
  telegram_bot.py       # Portal (async): receives updates (text/audio/photo), sends replies

mind/
  mind.py               # Integration (async): orchestrates Mind pipelines

  perception/             
    language.py         # Provider (async): uses LLM API for completions
    audio.py            # Provider (async): uses Google library for speech-to-text conversion
    vision.py           # Provider (async): uses vision AI model API for image-to-text conversion
    
  memory/
    memory.py           # MemoryCore (sync, static): extracts facts, builds profile;
                        # MemoryProvider (async): owns in-memory conversations and storage API
                        
    data/
      user_profile.py   # Data: UserProfile { facts, preferences, emotion }
      conversation.py   # Data: Conversation { user_id, chat_id, messages: [Message] }
      message.py        # Data: Message { role, text, media_type, timestamp }
      emotional_state.py  # Data: EmotionalState { glad, mad, sad, scared }
      
  cognition.py          # CognitionCore (sync, static): operates on messages and conversations, make decisions
  affect.py             # AffectCore (sync, static): updates mood, decays, influences system prompt;
                        # AffectProvider (async): owns EmotionalState, can use external context later
```
## Core Pipelines

TBD

## Workflow
- Use TDD where applicable and reasonable
- Run tests before proposing any changes for review

### How to run tests
**When running tests, prefer `python -m pytest` from the project root, using the interpreter in `.venv\Scripts\python.exe` or `.venv/bin/python`.**

## Coding Style and Patterns
- Use f-string formatting for concatenation
- It is preferable to use static methods for Core operations that don't need to be instantiated
- It is preferable to use builder pattern for Providers 
- It is preferable to follow "fail fast" principle for error handling
- Use explicit type hints for all functions and methods
- Use `asyncio.gather()` whenever two or more Providers/Portals are called and their inputs are independent