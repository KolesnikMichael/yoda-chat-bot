from yoda.mind.agent.data.agent_data import (
    AgentContext,
    Decision,
    SkillSpec,
    SkillSummary,
    ToolResult,
)
from yoda.mind.data.routing_context import format_recent_messages_block
from yoda.mind.memory.data.user_profile import UserProfile

EXECUTOR_SYSTEM_PROMPT = (
    "You are an executor agent. Your job is to complete tasks using available tools. "
    "Be precise, follow the skill workflow, and produce structured decisions.\n\n"
    "You MUST respond with a JSON object matching this schema:\n"
    '{{\n'
    '  "selected_skill": "skill_name or null",\n'
    '  "distilled_task": "self-contained execution brief or null",\n'
    '  "tool_calls": [{{"tool_name": "name", "arguments": {{...}}}}],\n'
    '  "final_answer": "answer text or null",\n'
    '  "reasoning": "brief explanation of your decision"\n'
    '}}\n'
    "Phase 1 (no skill active yet): set exactly ONE of:\n"
    "  - selected_skill: when you pick a skill you MUST set distilled_task to a neutral, "
    "self-contained description of what to accomplish (constraints, times, entities). "
    "No chat meta, no \"the user said\". Use null for distilled_task only when not selecting a skill.\n"
    "  - tool_calls: ONLY ask_user or update_profile to clarify before choosing a skill.\n"
    "  - final_answer: decline or answer without tools.\n"
    "Phase 2 (skill already active): set tool_calls or final_answer only; "
    "selected_skill and distilled_task must be null."
)

SELECTION_INSTRUCTION = (
    "Select the best skill for this task. Set selected_skill to the skill name and "
    "distilled_task to a clear execution brief (as required by the system rules). "
    "If something critical is missing to choose or specify the task, call ask_user. "
    "If no skill fits, set final_answer with a brief explanation. "
    "Do not call skill-specific tools (only ask_user or update_profile here)."
)

EXECUTION_INSTRUCTION = (
    "Now execute the skill workflow. "
    "Each response must contain tool_calls or final_answer."
)

INFRA_TOOLS = frozenset({"ask_user", "update_profile"})

PHASE1_TOOL_CALL_WHITELIST = INFRA_TOOLS


class ReactLoop:
    """Core (sync): builds LLM context, validates Decision, manages state."""

    @staticmethod
    def build_system_message(profile: UserProfile) -> dict:
        """Static system prompt: role, JSON schema, profile. No tools, no time."""
        content = "\n\n".join([
            EXECUTOR_SYSTEM_PROMPT,
            _format_profile_context(profile),
        ])
        return {"role": "system", "content": content}

    @staticmethod
    def build_context(context: AgentContext, utc_now: str) -> list[dict]:
        time_msg = {"role": "system", "content": f"Current UTC time: {utc_now}"}
        return list(context.messages) + [time_msg]

    @staticmethod
    def build_selection_control_message(
        catalog_summaries: list[SkillSummary],
    ) -> dict:
        lines = [
            "<skill_selection_control>",
            "Select by requested outcome. Catalog order has no semantic priority.",
            SELECTION_INSTRUCTION,
        ]
        if catalog_summaries:
            for summary in sorted(catalog_summaries, key=lambda s: s.name):
                lines.append(f'<skill name="{summary.name}">')
                lines.append(f"purpose: {summary.purpose}")
                lines.append("when_to_use:")
                lines.extend(f"- {item}" for item in summary.when_to_use)
                lines.append("do_not_use_when:")
                lines.extend(f"- {item}" for item in summary.do_not_use_when)
                lines.append("selection_examples:")
                lines.extend(f"- {item}" for item in summary.selection_examples)
                lines.append("</skill>")
        else:
            lines.append("No skills available.")
        lines.append("</skill_selection_control>")
        return {"role": "system", "content": "\n".join(lines)}

    @staticmethod
    def build_selection_input_message(
        task: str,
        recent_messages: list[dict] | None = None,
    ) -> dict:
        parts = ["<selection_input>"]
        if recent_messages:
            block = format_recent_messages_block(recent_messages)
            if block:
                parts.append("<recent_conversation>")
                parts.append(block)
                parts.append("</recent_conversation>")
        parts.append("<task>")
        parts.append(task)
        parts.append("</task>")
        parts.append("</selection_input>")
        return {"role": "user", "content": "\n".join(parts)}

    @staticmethod
    def refresh_selection_messages(
        context: AgentContext,
        catalog_summaries: list[SkillSummary],
    ) -> AgentContext:
        messages = list(context.messages)
        control_msg = ReactLoop.build_selection_control_message(catalog_summaries)

        seed_pairs: list[int] = []
        for i in range(len(messages) - 1):
            control = messages[i]
            selection_input = messages[i + 1]
            control_content = str(control.get("content", ""))
            input_content = str(selection_input.get("content", ""))
            if (
                control.get("role") == "system"
                and control_content.startswith("<skill_selection_control>\n")
                and control_content.endswith("\n</skill_selection_control>")
                and selection_input.get("role") == "user"
                and input_content.startswith("<selection_input>\n")
                and input_content.endswith("\n</selection_input>")
            ):
                seed_pairs.append(i)

        if seed_pairs:
            if len(seed_pairs) != 1:
                raise ValueError(
                    "Unrecognized selection transcript: multiple selection seeds"
                )
            messages[seed_pairs[0]] = control_msg
            return AgentContext(
                task=context.task,
                profile=context.profile,
                chat_id=context.chat_id,
                user_id=context.user_id,
                catalog_summaries=catalog_summaries,
                active_skill=context.active_skill,
                messages=messages,
                iteration=context.iteration,
                tools_used=list(context.tools_used),
            )

        if context.catalog_summaries:
            legacy_catalog_lines = ["Available skills:"]
            legacy_catalog_lines.extend(
                f"- {summary.name}: {summary.description}"
                for summary in context.catalog_summaries
            )
            legacy_catalog = "\n".join(legacy_catalog_lines)
        else:
            legacy_catalog = "No skills available."
        legacy_suffix = f"\n\n{legacy_catalog}\n\n{SELECTION_INSTRUCTION}"
        legacy_idxs = [
            i for i, message in enumerate(messages)
            if message.get("role") == "user"
            and str(message.get("content", "")).endswith(legacy_suffix)
        ]
        if len(legacy_idxs) != 1:
            raise ValueError(
                "Unrecognized selection transcript: no selection seed found"
            )

        legacy_idx = legacy_idxs[0]
        legacy_content = str(messages[legacy_idx]["content"])
        prefix = legacy_content[:-len(legacy_suffix)]

        input_msg = {
            "role": "user",
            "content": "\n".join([
                "<selection_input>",
                prefix,
                "</selection_input>",
            ]),
        }
        new_messages = (
            messages[:legacy_idx]
            + [control_msg, input_msg]
            + messages[legacy_idx + 1:]
        )
        return AgentContext(
            task=context.task,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=catalog_summaries,
            active_skill=context.active_skill,
            messages=new_messages,
            iteration=context.iteration,
            tools_used=list(context.tools_used),
        )

    @staticmethod
    def filter_tool_schemas(
        all_schemas: list[dict], skill: SkillSpec,
    ) -> list[dict]:
        relevant = set(skill.tools) | set(INFRA_TOOLS)
        return [s for s in all_schemas if s["name"] in relevant]

    @staticmethod
    def allowed_tool_names_for_skill(skill: SkillSpec) -> set[str]:
        return set(skill.tools) | set(INFRA_TOOLS)

    @staticmethod
    def build_compact_execution_messages(
        profile: UserProfile,
        task: str,
        skill: SkillSpec,
        activation_msg: dict,
    ) -> list[dict]:
        """Fresh message list for Phase 2: no selection noise or raw Phase-1 JSON."""
        system = ReactLoop.build_system_message(profile)
        task_msg = {"role": "user", "content": f"Task:\n{task}"}
        return [system, task_msg, activation_msg]

    @staticmethod
    def build_activation_message(
        skill: SkillSpec, tool_schemas: list[dict],
    ) -> dict:
        parts = [
            f"Skill '{skill.name}' activated.",
            f"Description: {skill.description}",
        ]
        if skill.required_inputs:
            inputs_str = ", ".join(
                f"{k} ({v})" for k, v in skill.required_inputs.items()
            )
            parts.append(f"Required inputs: {inputs_str}")
        parts.append(_format_tool_schemas(tool_schemas))
        parts.append(f"Workflow:\n{skill.instructions}")
        parts.append(EXECUTION_INSTRUCTION)
        return {"role": "system", "content": "\n\n".join(parts)}

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
            return ReactLoop._validate_phase1_modes(
                decision, available_tools)

        if decision.selected_skill is not None or decision.distilled_task is not None:
            decision = decision.model_copy(
                update={"selected_skill": None, "distilled_task": None},
            )

        for tc in decision.effective_tool_calls:
            if tc.tool_name not in available_tools:
                return Decision(
                    final_answer=f"Unknown tool: {tc.tool_name}",
                    reasoning="Validation: tool not available",
                )

        return decision

    @staticmethod
    def _validate_phase1_modes(
        decision: Decision,
        available_tools: set[str],
    ) -> Decision:
        has_fa = decision.final_answer is not None and str(decision.final_answer).strip() != ""
        has_skill = (
            decision.selected_skill is not None
            and str(decision.selected_skill).strip() != ""
        )
        has_tools = len(decision.effective_tool_calls) > 0
        modes = int(has_fa) + int(has_skill) + int(has_tools)
        if modes > 1:
            return Decision(
                final_answer=(
                    "Invalid Phase 1: use exactly one of final_answer, "
                    "selected_skill, or tool_calls."
                ),
                reasoning="Validation: mutually exclusive fields",
            )
        if modes == 0:
            return Decision(
                final_answer="Invalid Phase 1: empty response.",
                reasoning="Validation: no actionable fields",
            )
        if has_tools:
            allowed = PHASE1_TOOL_CALL_WHITELIST & available_tools
            for tc in decision.effective_tool_calls:
                if tc.tool_name not in allowed:
                    return Decision(
                        final_answer=(
                            f"Phase 1 only allows {sorted(allowed)}; "
                            f"got {tc.tool_name!r}."
                        ),
                        reasoning="Validation: tool not allowed in phase 1",
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
    if profile.preferred_name:
        parts.append(f"  name: {profile.preferred_name}")
    if len(parts) == 1:
        parts.append("  (no timezone or location on file)")
    return "\n".join(parts)
