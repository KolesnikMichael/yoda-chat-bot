from yoda.mind.agent.data.agent_data import (
    AgentContext,
    Decision,
    ToolResult,
)

EXECUTOR_SYSTEM_PROMPT = (
    "You are an executor agent. Your job is to complete tasks using available tools. "
    "Be precise, follow the skill workflow, and produce structured decisions.\n"
    "Current UTC time: {utc_now}\n\n"
    "You MUST respond with a JSON object matching this schema:\n"
    '{{\n'
    '  "selected_skill": "skill_name or null",\n'
    '  "tool_calls": [{{"tool_name": "name", "arguments": {{...}}}}],\n'
    '  "final_answer": "answer text or null",\n'
    '  "reasoning": "brief explanation of your decision"\n'
    '}}\n'
    "Rules: set exactly ONE of: selected_skill (phase 1), tool_calls (phase 2), or final_answer (done)."
)

SELECTION_INSTRUCTION = (
    "Select the best skill for this task. Set selected_skill to the skill name. "
    "If no skill fits, set final_answer with a brief explanation. "
    "Do NOT set tool_calls in this phase."
)

EXECUTION_INSTRUCTION = (
    "Follow the active skill's workflow.\n"
    "CRITICAL: Every response MUST contain either tool_calls OR final_answer. "
    "Never return both as null — that is an invalid response.\n"
    "Do NOT just describe what you plan to do in reasoning — actually DO it by setting tool_calls.\n\n"
    "Example — calling schedule_message with a relative delay:\n"
    '{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "delay_minutes": 30}}], "reasoning": "scheduling a reminder in 30 minutes"}\n\n'
    "Example — calling schedule_message with an absolute time:\n"
    '{"tool_calls": [{"tool_name": "schedule_message", "arguments": {"reminder_text": "call mom", "year": 2026, "month": 3, "day": 21, "hour": 15, "minute": 0, "timezone": "Europe/Moscow"}}], "reasoning": "scheduling at specific time"}\n\n'
    "Example — asking the user:\n"
    '{"tool_calls": [{"tool_name": "ask_user", "arguments": {"question": "What is your timezone?"}}], "reasoning": "need timezone for absolute time"}\n\n'
    "Example — done:\n"
    '{"final_answer": "Reminder set for 30 minutes from now.", "reasoning": "confirmed"}'
)


class ReactLoop:
    """Core (sync): builds LLM context, validates Decision, manages state."""

    @staticmethod
    def build_context(
        context: AgentContext,
        tool_schemas: list[dict],
        utc_now: str,
    ) -> list[dict]:
        messages: list[dict] = []

        system_parts = [EXECUTOR_SYSTEM_PROMPT.format(utc_now=utc_now)]

        if context.active_skill is None:
            system_parts.append(_format_catalog(context))
            system_parts.append(SELECTION_INSTRUCTION)
        else:
            system_parts.append(_format_active_skill(context))
            system_parts.append(_format_tool_schemas(tool_schemas))
            system_parts.append(_format_profile_context(context))
            system_parts.append(EXECUTION_INSTRUCTION)

        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": f"Task: {context.task}"})

        for result in context.history:
            if result.tool_name == "ask_user":
                content = f"User answered: {result.output}"
            else:
                status = "OK" if result.success else "FAILED"
                content = f"[{result.tool_name}] ({status}) {result.output}"
            messages.append({"role": "user", "content": content})

        return messages

    @staticmethod
    def validate_decision(
        decision: Decision,
        context: AgentContext,
        available_tools: set[str],
    ) -> Decision:
        if context.active_skill is None:
            if decision.selected_skill and not any(
                s.name == decision.selected_skill
                for s in context.catalog_summaries
            ):
                return Decision(
                    final_answer=f"Unknown skill: {decision.selected_skill}",
                    reasoning="Validation: skill not in catalog",
                )
            return decision

        for tc in decision.effective_tool_calls:
            if tc.tool_name not in available_tools:
                return Decision(
                    final_answer=f"Unknown tool: {tc.tool_name}",
                    reasoning="Validation: tool not available",
                )

        return decision

    @staticmethod
    def observe(context: AgentContext, results: list[ToolResult]) -> AgentContext:
        new_history = list(context.history) + results
        new_tools_used = list(context.tools_used)
        for r in results:
            if r.tool_name not in new_tools_used:
                new_tools_used.append(r.tool_name)

        return AgentContext(
            task=context.task,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=context.catalog_summaries,
            active_skill=context.active_skill,
            history=new_history,
            iteration=context.iteration + 1,
            tools_used=new_tools_used,
        )

    @staticmethod
    def is_done(context: AgentContext) -> bool:
        max_iter = (
            context.active_skill.max_iterations
            if context.active_skill
            else 5
        )
        return context.iteration >= max_iter


def _format_catalog(context: AgentContext) -> str:
    if not context.catalog_summaries:
        return "No skills available."
    lines = ["Available skills:"]
    for s in context.catalog_summaries:
        lines.append(f"- {s.name}: {s.description}")
    return "\n".join(lines)


def _format_active_skill(context: AgentContext) -> str:
    skill = context.active_skill
    parts = [f"Active skill: {skill.name}", f"Description: {skill.description}"]
    if skill.required_inputs:
        inputs_str = ", ".join(
            f"{k} ({v})" for k, v in skill.required_inputs.items()
        )
        parts.append(f"Required inputs: {inputs_str}")
    parts.append(f"Workflow:\n{skill.instructions}")
    return "\n".join(parts)


def _format_tool_schemas(tool_schemas: list[dict]) -> str:
    if not tool_schemas:
        return "No tools available."
    lines = ["Available tools:"]
    for schema in tool_schemas:
        params = schema.get("parameters", {})
        required = schema.get("required", [])
        param_parts = []
        for pname, pinfo in params.items():
            req_mark = " (required)" if pname in required else ""
            desc = pinfo.get("description", pinfo.get("type", ""))
            param_parts.append(f"    {pname}: {desc}{req_mark}")
        lines.append(f"- {schema['name']}:")
        lines.extend(param_parts)
    return "\n".join(lines)


def _format_profile_context(context: AgentContext) -> str:
    p = context.profile
    parts = ["User profile context:"]
    if p.timezone:
        parts.append(f"  timezone: {p.timezone}")
    if p.location:
        parts.append(f"  location: {p.location}")
    if p.nickname:
        parts.append(f"  name: {p.nickname}")
    if len(parts) == 1:
        parts.append("  (no timezone or location on file)")
    return "\n".join(parts)
