# Conversation Modes Integration (Intent + Style Layer)

## 🧠 Core Idea

Introduce a second classification dimension alongside intent:

- **Intent** → *what to do*
- **Mode** → *how to do it*

These are selected **in parallel** and applied jointly during response generation.

---

## 🧩 Updated Pipeline

```
User input
   ↓
[1] Intent classification        → what is needed (search, help, explain)
[2] Mode classification          → how to respond (empathetic, analytical, casual)
   ↓
[3] Skill selection (by intent)
   ↓
[4] Mode overlay (style policy)
   ↓
[5] Tool selection (conditioned by intent + mode)
   ↓
[6] Response generation
```

---

## ⚙️ Integration Strategy (Non-breaking)

### 1. Add Mode as a Secondary Tag

Extend classifier output without modifying existing intent logic:

```json
{
  "intent": "information_request",
  "mode": "analytical_discussion"
}
```

---

### 2. Treat Mode as a Policy Layer

Mode should NOT:
- invoke tools directly
- replace intent

Mode SHOULD:
- modify prompts
- define tone and structure
- constrain or enable behaviors

---

### 3. Preserve Intent → Skill Mapping

```
intent → skill
mode → execution style
```

Example:
- intent: `mental_health_support`
- skill: `support_response`
- mode: `empathetic_support`

Same skill can operate under different modes.

---

### 4. Introduce Compatibility Matrix

Reduce misclassification and conflicts:

| intent               | allowed modes                    |
|---------------------|---------------------------------|
| small_talk          | casual, engagement              |
| mental_support      | empathetic, reflective          |
| business_analysis   | analytical, professional        |

---

### 5. Mode-Conditioned Tool Usage

Examples:

- `analytical_discussion_mode`
  - enables structured reasoning
  - promotes decomposition

- `empathetic_support_mode`
  - avoids aggressive questioning
  - emphasizes reflective responses

---

## 🎯 Recommended Minimal Mode Set

Keep the set small to avoid classification errors:

- `casual_engagement_mode`
- `empathetic_support_mode`
- `analytical_discussion_mode`
- `task_execution_mode`
- `exploratory_mode`

---

## ⚠️ Key Risks

### 1. Mode Drift
Model gradually shifts style unintentionally

**Mitigation:**
- strong system prompts
- reinforcement in intermediate steps

---

### 2. Intent vs Mode Conflict

Example:
- intent: task execution
- mode: casual

**Mitigation:**
- intent has priority
- enforce compatibility constraints

---

### 3. Over-fragmentation

Too many modes → classifier degradation

**Mitigation:**
- limit to 5–8 modes
- merge similar styles

---

## 🔬 Relevant Research Directions

### Dialogue Policy & Adaptive Systems
- Deep Reinforcement Learning for Dialogue Generation (Li et al., 2016)
- A Survey on Dialogue Systems (Zhang et al., 2020)

Key idea:
- separation of policy (how) and action (what)

---

### Persona & Style Control
- A Persona-Based Neural Conversation Model (Li et al., 2016)
- CTRL: Controllable Text Generation (Keskar et al., 2019)

Key idea:
- explicit conditioning enables style control

---

### LLM Behavior Steering
- Steerability of Large Language Models (OpenAI, 2023)
- Constitutional AI (Anthropic, 2023)

Key idea:
- behavior defined via policy constraints

---

### Tool-Augmented Reasoning
- ReAct (Reasoning + Acting)
- Toolformer

Key idea:
- separation of reasoning and acting layers

---

### Agent Frameworks
- LangChain
- Semantic Kernel

Trend:
- separation of planning, execution, and control layers

---

## 💡 Summary

This approach introduces a:

> **Style-aware orchestration layer**

Benefits:
- faster adaptation to conversational context
- more predictable behavior
- reduced reliance on implicit LLM flexibility

---

## 🚀 Next Steps (Optional)

- Define prompt templates per mode
- Implement mode classifier (few-shot / embeddings / hybrid)
- Add runtime mode switching logic
- Log mode transitions for evaluation
- Design mode overlay: modes should define variations to system prompt without contradictions
- Think about real-time mode steering (during long periods without applying skills where modes are chosen explicitly)


