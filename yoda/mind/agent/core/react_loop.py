from __future__ import annotations

from yoda.mind.agent.data.agent_data import (
    AgentContext,
    AgentPhase,
    ExecutionDecision,
    ProtocolIssue,
    ProtocolIssueCategory,
    SelectionDecision,
    SkillSpec,
    SkillSummary,
    ToolResult,
)
from yoda.mind.data.routing_context import format_recent_messages_block
from yoda.mind.memory.data.user_profile import UserProfile

SELECTION_SYSTEM_PROMPT = (
    "You are a skill-selection agent. Choose exactly one skill for the task "
    "or report that no skill applies.\n\n"
    "You MUST respond with a JSON object matching this schema:\n"
    "{{\n"
    '  "mode": "select_skill" | "no_skill",\n'
    '  "selected_skill": "skill_name or null",\n'
    '  "distilled_task": "self-contained execution brief or null",\n'
    '  "reason": "unsupported" | null,\n'
    '  "reasoning": "brief explanation of your decision"\n'
    "}}\n"
    "Rules:\n"
    '- mode="select_skill": set selected_skill to a catalog skill name and '
    "distilled_task to a neutral, self-contained description of what to "
    "accomplish (constraints, times, entities). No chat meta. reason must be null.\n"
    '- mode="no_skill": set reason to "unsupported"; selected_skill and '
    "distilled_task must be null.\n"
    "Do not call tools, ask questions, or produce a final answer."
)

EXECUTION_SYSTEM_PROMPT = (
    "You are an executor agent. Complete the active skill using available tools.\n\n"
    "You MUST respond with a JSON object matching this schema:\n"
    "{{\n"
    '  "mode": "call_tools" | "finish",\n'
    '  "tool_calls": [{{"tool_name": "name", "arguments": {{...}}}}] or null,\n'
    '  "final_answer": "answer text or null",\n'
    '  "reasoning": "brief explanation of your decision"\n'
    "}}\n"
    "Rules:\n"
    '- mode="call_tools": provide one or more tool_calls; final_answer must be null.\n'
    '- mode="finish": provide a non-empty final_answer; tool_calls must be null.\n'
    "Do not select skills."
)

SELECTION_INSTRUCTION = (
    "Select the best skill for this task. "
    'Use mode="select_skill" with selected_skill and a clear distilled_task, '
    'or mode="no_skill" with reason="unsupported" if nothing fits. '
    "Do not call tools or ask questions during selection."
)

# Exact pre-TASK-015 wording embedded in suspended Redis transcripts.
_LEGACY_SELECTION_INSTRUCTION = (
    "Select the best skill for this task. Set selected_skill to the skill name and "
    "distilled_task to a clear execution brief (as required by the system rules). "
    "If something critical is missing to choose or specify the task, call ask_user. "
    "If no skill fits, set final_answer with a brief explanation. "
    "Do not call skill-specific tools (only ask_user or update_profile here)."
)

EXECUTION_INSTRUCTION = (
    "Now execute the skill workflow. "
    'Each response must use mode="call_tools" or mode="finish".'
)

INFRA_TOOLS = frozenset({"ask_user", "update_profile"})

_CORRECTION_REASONS: dict[tuple[AgentPhase, ProtocolIssueCategory], str] = {
    (AgentPhase.SELECTION, ProtocolIssueCategory.MALFORMED_OUTPUT): (
        "response was not valid SelectionDecision JSON"
    ),
    (AgentPhase.SELECTION, ProtocolIssueCategory.INVALID_MODE): (
        "selection mode fields were inconsistent"
    ),
    (AgentPhase.SELECTION, ProtocolIssueCategory.UNKNOWN_SKILL): (
        "selected_skill is not in the current catalog"
    ),
    (AgentPhase.EXECUTION, ProtocolIssueCategory.MALFORMED_OUTPUT): (
        "response was not valid ExecutionDecision JSON"
    ),
    (AgentPhase.EXECUTION, ProtocolIssueCategory.INVALID_MODE): (
        "execution mode fields were inconsistent"
    ),
    (AgentPhase.EXECUTION, ProtocolIssueCategory.UNKNOWN_TOOL): (
        "a tool_name is not among the allowed tools"
    ),
}


class ReactLoop:
    """Core (sync): builds LLM context, validates phase decisions, manages state."""

    @staticmethod
    def build_system_message(profile: UserProfile) -> dict:
        """Legacy combined system prompt — prefer phase-specific builders."""
        content = "\n\n".join([
            EXECUTION_SYSTEM_PROMPT,
            _format_profile_context(profile),
        ])
        return {"role": "system", "content": content}

    @staticmethod
    def build_selection_system_message(profile: UserProfile) -> dict:
        content = "\n\n".join([
            SELECTION_SYSTEM_PROMPT,
            _format_profile_context(profile),
        ])
        return {"role": "system", "content": content}

    @staticmethod
    def build_execution_system_message(profile: UserProfile) -> dict:
        content = "\n\n".join([
            EXECUTION_SYSTEM_PROMPT,
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
            return ReactLoop._copy_context(
                context,
                catalog_summaries=catalog_summaries,
                messages=messages,
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
        legacy_suffixes = [
            f"\n\n{legacy_catalog}\n\n{_LEGACY_SELECTION_INSTRUCTION}",
            f"\n\n{legacy_catalog}\n\n{SELECTION_INSTRUCTION}",
        ]
        legacy_idxs: list[int] = []
        matched_suffix = ""
        for suffix in legacy_suffixes:
            idxs = [
                i for i, message in enumerate(messages)
                if message.get("role") == "user"
                and str(message.get("content", "")).endswith(suffix)
            ]
            if idxs:
                legacy_idxs = idxs
                matched_suffix = suffix
                break
        if len(legacy_idxs) != 1:
            raise ValueError(
                "Unrecognized selection transcript: no selection seed found"
            )

        legacy_idx = legacy_idxs[0]
        legacy_content = str(messages[legacy_idx]["content"])
        prefix = legacy_content[:-len(matched_suffix)]

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
        return ReactLoop._copy_context(
            context,
            catalog_summaries=catalog_summaries,
            messages=new_messages,
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
        """Fresh message list for execution: no selection noise."""
        system = ReactLoop.build_execution_system_message(profile)
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
        context: AgentContext,
        decision: SelectionDecision | ExecutionDecision,
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

        return ReactLoop._copy_context(
            context,
            messages=new_messages,
            iteration=context.iteration + 1,
            tools_used=new_tools_used,
        )

    @staticmethod
    def validate_selection_decision(
        decision: SelectionDecision,
        available_skills: set[str],
    ) -> ProtocolIssue | None:
        if decision.mode == "select_skill":
            skill = (decision.selected_skill or "").strip()
            task = (decision.distilled_task or "").strip()
            if decision.reason is not None:
                return ProtocolIssue(
                    stage=AgentPhase.SELECTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            if not skill or not task:
                return ProtocolIssue(
                    stage=AgentPhase.SELECTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            if skill not in available_skills:
                return ProtocolIssue(
                    stage=AgentPhase.SELECTION,
                    category=ProtocolIssueCategory.UNKNOWN_SKILL,
                )
            return None

        if decision.mode == "no_skill":
            if decision.reason != "unsupported":
                return ProtocolIssue(
                    stage=AgentPhase.SELECTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            if decision.selected_skill is not None or decision.distilled_task is not None:
                return ProtocolIssue(
                    stage=AgentPhase.SELECTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            return None

        return ProtocolIssue(
            stage=AgentPhase.SELECTION,
            category=ProtocolIssueCategory.INVALID_MODE,
        )

    @staticmethod
    def validate_execution_decision(
        decision: ExecutionDecision,
        available_tools: set[str],
    ) -> ProtocolIssue | None:
        if decision.mode == "call_tools":
            calls = decision.tool_calls or []
            if decision.final_answer is not None:
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            if len(calls) < 1:
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            for tc in calls:
                if tc.tool_name not in available_tools:
                    return ProtocolIssue(
                        stage=AgentPhase.EXECUTION,
                        category=ProtocolIssueCategory.UNKNOWN_TOOL,
                    )
            return None

        if decision.mode == "finish":
            answer = (decision.final_answer or "").strip()
            if not answer:
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            if decision.tool_calls:
                return ProtocolIssue(
                    stage=AgentPhase.EXECUTION,
                    category=ProtocolIssueCategory.INVALID_MODE,
                )
            return None

        return ProtocolIssue(
            stage=AgentPhase.EXECUTION,
            category=ProtocolIssueCategory.INVALID_MODE,
        )

    @staticmethod
    def append_correction(
        context: AgentContext,
        issue: ProtocolIssue,
    ) -> AgentContext:
        if issue.stage == AgentPhase.SELECTION:
            if context.selection_retry_used:
                return context
            selection_retry_used = True
            execution_retry_used = context.execution_retry_used
        else:
            if context.execution_retry_used:
                return context
            selection_retry_used = context.selection_retry_used
            execution_retry_used = True

        reason = _CORRECTION_REASONS.get(
            (issue.stage, issue.category),
            "response did not match the phase contract",
        )
        if issue.stage == AgentPhase.SELECTION:
            content = (
                f"The previous skill-selection response was invalid: {reason}. "
                "Return one corrected SelectionDecision JSON object only. "
                "Do not call tools, ask a question, answer the task, or include markdown."
            )
        else:
            content = (
                f"The previous execution response was invalid: {reason}. "
                "Return one corrected ExecutionDecision JSON object only. "
                "Use only the active skill and available tools. Do not claim "
                "success unless it is present in a tool result."
            )
        correction = {"role": "system", "content": content}
        return ReactLoop._copy_context(
            context,
            messages=list(context.messages) + [correction],
            selection_retry_used=selection_retry_used,
            execution_retry_used=execution_retry_used,
        )

    @staticmethod
    def upgrade_legacy_protocol(
        context: AgentContext,
        current_catalog: list[SkillSummary],
    ) -> AgentContext:
        if context.protocol_version >= 2:
            return context

        if context.active_skill is None:
            refreshed = ReactLoop.refresh_selection_messages(context, current_catalog)
            messages = list(refreshed.messages)
            if messages and _is_legacy_combined_system_message(messages[0]):
                messages[0] = ReactLoop.build_selection_system_message(context.profile)
            return ReactLoop._copy_context(
                refreshed,
                messages=messages,
                phase=AgentPhase.SELECTION,
                protocol_version=2,
            )

        messages = list(context.messages)
        execution_system = ReactLoop.build_execution_system_message(context.profile)
        if messages and _is_legacy_combined_system_message(messages[0]):
            messages[0] = execution_system
        return ReactLoop._copy_context(
            context,
            messages=messages,
            phase=AgentPhase.EXECUTION,
            protocol_version=2,
            catalog_summaries=current_catalog,
        )

    @staticmethod
    def is_done(context: AgentContext) -> bool:
        max_iter = (
            context.active_skill.max_iterations
            if context.active_skill
            else 5
        )
        return context.iteration >= max_iter

    @staticmethod
    def _copy_context(
        context: AgentContext,
        *,
        catalog_summaries: list[SkillSummary] | None = None,
        messages: list[dict] | None = None,
        iteration: int | None = None,
        tools_used: list[str] | None = None,
        phase: AgentPhase | None = None,
        selection_retry_used: bool | None = None,
        execution_retry_used: bool | None = None,
        protocol_version: int | None = None,
        active_skill: SkillSpec | None = None,
        task: str | None = None,
    ) -> AgentContext:
        return AgentContext(
            task=context.task if task is None else task,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=(
                context.catalog_summaries
                if catalog_summaries is None
                else catalog_summaries
            ),
            active_skill=(
                context.active_skill if active_skill is None else active_skill
            ),
            messages=context.messages if messages is None else messages,
            iteration=context.iteration if iteration is None else iteration,
            tools_used=(
                list(context.tools_used) if tools_used is None else tools_used
            ),
            phase=context.phase if phase is None else phase,
            selection_retry_used=(
                context.selection_retry_used
                if selection_retry_used is None
                else selection_retry_used
            ),
            execution_retry_used=(
                context.execution_retry_used
                if execution_retry_used is None
                else execution_retry_used
            ),
            protocol_version=(
                context.protocol_version
                if protocol_version is None
                else protocol_version
            ),
        )


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


def _is_legacy_combined_system_message(message: dict) -> bool:
    content = str(message.get("content", ""))
    return (
        message.get("role") == "system"
        and content.startswith(
            "You are an executor agent. Your job is to complete tasks using "
            "available tools."
        )
        and '"selected_skill"' in content
        and '"tool_calls"' in content
        and "Phase 1" in content
    )


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
