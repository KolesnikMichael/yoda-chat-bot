from yoda.mind.agent.data.agent_data import (
    AgentContext,
    Decision,
    SkillSpec,
    SkillSummary,
    ToolResult,
)
from yoda.mind.memory.data.user_profile import UserProfile

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
    "Now execute the skill workflow. "
    "Each response must contain tool_calls or final_answer."
)


class ReactLoop:
    """Core (sync): builds LLM context, validates Decision, manages state."""

    @staticmethod
    def build_context(
        context: AgentContext,
        tool_schemas: list[dict],
        utc_now: str,
    ) -> list[dict]:
        system = _build_system_prompt(tool_schemas, context.profile, utc_now)
        return [{"role": "system", "content": system}] + list(context.messages)

    @staticmethod
    def build_selection_message(
        task: str,
        catalog_summaries: list[SkillSummary],
    ) -> dict:
        parts = [f"Task: {task}"]
        if catalog_summaries:
            lines = ["Available skills:"]
            for s in catalog_summaries:
                lines.append(f"- {s.name}: {s.description}")
            parts.append("\n".join(lines))
        else:
            parts.append("No skills available.")
        parts.append(SELECTION_INSTRUCTION)
        return {"role": "user", "content": "\n\n".join(parts)}

    @staticmethod
    def build_activation_message(skill: SkillSpec) -> dict:
        parts = [
            f"Skill '{skill.name}' activated.",
            f"Description: {skill.description}",
        ]
        if skill.required_inputs:
            inputs_str = ", ".join(
                f"{k} ({v})" for k, v in skill.required_inputs.items()
            )
            parts.append(f"Required inputs: {inputs_str}")
        parts.append(f"Workflow:\n{skill.instructions}")
        parts.append(EXECUTION_INSTRUCTION)
        return {"role": "user", "content": "\n\n".join(parts)}

    @staticmethod
    def append_assistant(
        context: AgentContext, decision: Decision,
    ) -> AgentContext:
        msg = {"role": "assistant", "content": decision.model_dump_json()}
        return context.with_messages(context.messages + [msg])

    @staticmethod
    def append_tool_results(
        context: AgentContext, results: list[ToolResult],
    ) -> AgentContext:
        new_messages = list(context.messages)
        new_tools_used = list(context.tools_used)

        for r in results:
            if r.tool_name == "ask_user":
                content = f"User was asked: {r.output}"
            else:
                status = "OK" if r.success else "FAILED"
                content = f"[{r.tool_name}] ({status}) {r.output}"
            new_messages.append({"role": "system", "content": content})
            if r.tool_name not in new_tools_used:
                new_tools_used.append(r.tool_name)

        return AgentContext(
            task=context.task,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=context.catalog_summaries,
            active_skill=context.active_skill,
            messages=new_messages,
            iteration=context.iteration + 1,
            tools_used=new_tools_used,
        )

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
    def is_done(context: AgentContext) -> bool:
        max_iter = (
            context.active_skill.max_iterations
            if context.active_skill
            else 5
        )
        return context.iteration >= max_iter


def _build_system_prompt(
    tool_schemas: list[dict],
    profile: UserProfile,
    utc_now: str,
) -> str:
    parts = [EXECUTOR_SYSTEM_PROMPT.format(utc_now=utc_now)]
    parts.append(_format_tool_schemas(tool_schemas))
    parts.append(_format_profile_context(profile))
    return "\n\n".join(parts)


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


def _format_profile_context(profile: UserProfile) -> str:
    parts = ["User profile context:"]
    if profile.timezone:
        parts.append(f"  timezone: {profile.timezone}")
    if profile.location:
        parts.append(f"  location: {profile.location}")
    if profile.nickname:
        parts.append(f"  name: {profile.nickname}")
    if len(parts) == 1:
        parts.append("  (no timezone or location on file)")
    return "\n".join(parts)
