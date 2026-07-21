from __future__ import annotations

import asyncio
import datetime as dtm
import logging
from pathlib import Path

from yoda.mind.agent.core.execution_context import ExecutionContextCore
from yoda.mind.agent.core.outcome_core import OutcomeCore
from yoda.mind.agent.core.react_loop import ReactLoop
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    AgentFailure,
    AgentPhase,
    AgentResult,
    ExecutionDecision,
    ProtocolIssue,
    ProtocolIssueCategory,
    RequestConstraints,
    SelectionDecision,
    ToolCall,
    ToolCallRequest,
    ToolResult,
)
from yoda.mind.agent.data.outcome_data import (
    ClarificationResult,
    SafeFailureCategory,
    UserOperation,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.skills.catalog import SkillCatalog
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.perception.language import LanguageProvider, StructuredOutputError

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        language_provider: LanguageProvider,
        tools: list[Tool],
        skills_dir: Path,
        session_provider: AgentSessionProvider,
    ):
        self._llm = language_provider
        self._tools = {t.name: t for t in tools}
        self._skills_dir = skills_dir
        self._sessions = session_provider
        self._catalog_summaries = SkillCatalog.load_catalog(skills_dir)
        self._tool_schemas = [t.describe() for t in tools]

        warnings = SkillCatalog.validate_tools(
            self._catalog_summaries,
            skills_dir,
            set(self._tools.keys()),
        )
        for w in warnings:
            logger.warning(w)

    async def has_pending_session(self, chat_id: int) -> bool:
        return await self._sessions.has_session(chat_id)

    async def run(
        self,
        task: str,
        profile: UserProfile,
        chat_id: int,
        user_id: int = 0,
        recent_messages: list[dict] | None = None,
    ) -> AgentResult:
        context = AgentContext(
            task=task,
            profile=profile,
            chat_id=chat_id,
            user_id=user_id,
            catalog_summaries=self._catalog_summaries,
            phase=AgentPhase.SELECTION,
        )
        system_msg = ReactLoop.build_selection_system_message(profile)
        control_msg = ReactLoop.build_selection_control_message(
            self._catalog_summaries,
        )
        input_msg = ReactLoop.build_selection_input_message(
            task,
            recent_messages=recent_messages,
        )
        context = context.with_messages([system_msg, control_msg, input_msg])

        selected = await self._run_selection(context)
        if isinstance(selected, AgentResult):
            return selected
        return await self._execute_loop(selected)

    async def run_with_skill(
        self,
        *,
        skill_name: str,
        task: str,
        profile: UserProfile,
        chat_id: int,
        user_id: int = 0,
        request_constraints: RequestConstraints | None = None,
    ) -> AgentResult:
        try:
            constraints = ExecutionContextCore.normalize_request_constraints(
                request_constraints or RequestConstraints(),
            )
        except ValueError:
            logger.warning(
                "stage=%s category=%s",
                AgentPhase.EXECUTION.value,
                ProtocolIssueCategory.INVALID_CONSTRAINT.value,
            )
            return self._failure_result(
                AgentFailure(
                    stage=AgentPhase.EXECUTION,
                    category="protocol_exhausted",
                    issue=ProtocolIssueCategory.INVALID_CONSTRAINT,
                ),
                skill_name=skill_name,
            )
        base = AgentContext(
            task=task,
            profile=profile,
            chat_id=chat_id,
            user_id=user_id,
            catalog_summaries=self._catalog_summaries,
            phase=AgentPhase.EXECUTION,
            request_constraints=constraints,
            protocol_version=4,
        )
        context = self._activate_skill(
            base,
            skill_name=skill_name,
            distilled_task=task,
        )
        return await self._execute_loop(context)

    async def resume(self, chat_id: int, user_answer: str) -> AgentResult:
        context = await self._sessions.load(chat_id)
        if context is None:
            return AgentResult(
                outcome=OutcomeCore.failure(
                    UserOperation.REQUESTED_WORK,
                    SafeFailureCategory.AMBIGUOUS,
                ),
            )

        if context.protocol_version < 4:
            context = self._upgrade_session_protocol(context)

        answer_msg = {"role": "user", "content": f"User answered: {user_answer}"}
        context = context.with_messages(context.messages + [answer_msg])

        if context.phase == AgentPhase.SELECTION or context.active_skill is None:
            selected = await self._run_selection(context)
            if isinstance(selected, AgentResult):
                return selected
            return await self._execute_loop(selected)

        return await self._execute_loop(context)

    async def _run_selection(
        self,
        context: AgentContext,
    ) -> AgentContext | AgentResult:
        while True:
            decision, issue = await self._parse_selection(context)
            if issue is not None:
                exhausted = await self._handle_phase_issue(context, issue)
                if isinstance(exhausted, AgentResult):
                    return exhausted
                context = exhausted
                continue

            assert decision is not None
            logger.info(f"Selection decision: mode={decision.mode}")
            logger.debug(f"Selection reasoning={decision.reasoning}")

            if decision.mode == "no_skill":
                await self._sessions.delete(context.chat_id)
                return self._failure_result(
                    AgentFailure(
                        stage=AgentPhase.SELECTION,
                        category="unsupported",
                    ),
                )

            assert decision.selected_skill is not None
            assert decision.distilled_task is not None
            try:
                constraints = ExecutionContextCore.normalize_request_constraints(
                    decision.request_constraints,
                )
            except ValueError:
                logger.warning(
                    "stage=%s category=%s",
                    AgentPhase.EXECUTION.value,
                    ProtocolIssueCategory.INVALID_CONSTRAINT.value,
                )
                await self._sessions.delete(context.chat_id)
                return self._failure_result(
                    AgentFailure(
                        stage=AgentPhase.EXECUTION,
                        category="protocol_exhausted",
                        issue=ProtocolIssueCategory.INVALID_CONSTRAINT,
                    ),
                    skill_name=decision.selected_skill.strip(),
                )
            context = ReactLoop._copy_context(
                context,
                request_constraints=constraints,
            )
            return self._activate_skill(
                context,
                skill_name=decision.selected_skill.strip(),
                distilled_task=decision.distilled_task.strip(),
            )

    async def _parse_selection(
        self,
        context: AgentContext,
    ) -> tuple[SelectionDecision | None, ProtocolIssue | None]:
        utc_now = f"{dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        messages = ReactLoop.build_context(context, utc_now)
        try:
            raw = await self._llm.parse_structured(messages, SelectionDecision)
        except StructuredOutputError:
            return None, ProtocolIssue(
                stage=AgentPhase.SELECTION,
                category=ProtocolIssueCategory.MALFORMED_OUTPUT,
            )
        assert isinstance(raw, SelectionDecision)
        issue = ReactLoop.validate_selection_decision(
            raw,
            available_skills={s.name for s in context.catalog_summaries},
        )
        return raw, issue

    async def _execute_loop(self, context: AgentContext) -> AgentResult:
        terminal_success = False
        finished_answer: str | None = None

        while not ReactLoop.is_done(context):
            decision, issue = await self._parse_execution(context)
            if issue is not None:
                exhausted = await self._handle_phase_issue(context, issue)
                if isinstance(exhausted, AgentResult):
                    return exhausted
                context = exhausted
                continue

            assert decision is not None
            logger.info(f"Execution iteration {context.iteration}: mode={decision.mode}")
            logger.debug(f"Execution reasoning={decision.reasoning}")
            context = ReactLoop.append_assistant(context, decision)

            if decision.mode == "finish":
                finished_answer = (decision.final_answer or "").strip()
                break

            if decision.mode == "fail":
                await self._sessions.delete(context.chat_id)
                return AgentResult(
                    outcome=OutcomeCore.failure(
                        self._operation_for_context(context),
                        SafeFailureCategory.UNSUPPORTED,
                    ),
                )

            assert decision.tool_calls is not None
            prepared, prep_issue = ExecutionContextCore.prepare_tool_requests(
                decision.tool_calls,
                context.request_constraints,
            )
            if prep_issue is not None:
                exhausted = await self._handle_phase_issue(context, prep_issue)
                if isinstance(exhausted, AgentResult):
                    return exhausted
                context = exhausted
                continue

            tool_calls = self._build_tool_calls(context, prepared)
            results = await self._execute_tool_calls(tool_calls)
            context = self._append_results_with_evidence(context, results)
            failed_terminal = any(
                not result.success
                and result.tool_name in self._tools
                and self._tools[result.tool_name].terminal
                for result in results
            )
            if failed_terminal:
                context = ReactLoop._copy_context(
                    context,
                    terminal_failure_pending=True,
                )

            suspended = next((r for r in results if r.suspend), None)
            if suspended:
                await self._sessions.save(context)
                return AgentResult(
                    clarification=ClarificationResult(question=suspended.output),
                )

            terminal_completed = any(
                r.success and self._tools[r.tool_name].terminal
                for r in results
                if r.tool_name in self._tools
            )
            if terminal_completed:
                logger.info("Terminal tool succeeded, finishing loop")
                terminal_success = True
                break

        await self._sessions.delete(context.chat_id)

        if terminal_success:
            return AgentResult(
                outcome=OutcomeCore.success_from_terminal(context.outcome_evidence),
            )

        if finished_answer is not None:
            if context.terminal_failure_pending:
                return AgentResult(
                    outcome=OutcomeCore.failure(
                        self._operation_for_context(context),
                        SafeFailureCategory.TRANSIENT,
                    ),
                )
            skill_name = (
                context.active_skill.name if context.active_skill is not None else ""
            )
            return AgentResult(
                outcome=OutcomeCore.success_from_finish(
                    skill_name,
                    finished_answer,
                    context.outcome_evidence,
                ),
            )

        logger.warning(
            "stage=%s category=%s",
            AgentPhase.EXECUTION.value,
            ProtocolIssueCategory.ITERATION_LIMIT.value,
        )
        return self._failure_result(
            AgentFailure(
                stage=AgentPhase.EXECUTION,
                category="protocol_exhausted",
                issue=ProtocolIssueCategory.ITERATION_LIMIT,
            ),
            context=context,
        )

    async def _parse_execution(
        self,
        context: AgentContext,
    ) -> tuple[ExecutionDecision | None, ProtocolIssue | None]:
        utc_now = f"{dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        messages = ReactLoop.build_context(context, utc_now)
        try:
            raw = await self._llm.parse_structured(messages, ExecutionDecision)
        except StructuredOutputError:
            return None, ProtocolIssue(
                stage=AgentPhase.EXECUTION,
                category=ProtocolIssueCategory.MALFORMED_OUTPUT,
            )
        assert isinstance(raw, ExecutionDecision)
        available = self._available_tools_for_validation(context)
        issue = ReactLoop.validate_execution_decision(raw, available)
        return raw, issue

    async def _handle_phase_issue(
        self,
        context: AgentContext,
        issue: ProtocolIssue,
    ) -> AgentContext | AgentResult:
        logger.warning(
            "stage=%s category=%s",
            issue.stage.value,
            issue.category.value,
        )
        retry_used = (
            context.selection_retry_used
            if issue.stage == AgentPhase.SELECTION
            else context.execution_retry_used
        )
        if not retry_used:
            return ReactLoop.append_correction(context, issue)

        await self._sessions.delete(context.chat_id)
        return self._failure_result(
            AgentFailure(
                stage=issue.stage,
                category="protocol_exhausted",
                issue=issue.category,
            ),
            context=context,
        )

    def _available_tools_for_validation(self, context: AgentContext) -> set[str]:
        if context.active_skill is None:
            return set(self._tools.keys())
        return (
            ReactLoop.allowed_tool_names_for_skill(context.active_skill)
            & set(self._tools.keys())
        )

    @staticmethod
    def _build_tool_calls(
        context: AgentContext,
        requests: list[ToolCallRequest],
    ) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for tc in requests:
            arguments = dict(tc.arguments)
            if tc.tool_name == "update_profile" and isinstance(
                arguments.get("fields"), dict,
            ):
                arguments["fields"] = (
                    ExecutionContextCore.canonicalize_profile_update_fields(
                        arguments["fields"],
                    )
                )
            calls.append(
                ToolCall(
                    tool_name=tc.tool_name,
                    arguments=arguments,
                    metadata={
                        "chat_id": context.chat_id,
                        "user_id": context.user_id,
                        "profile_timezone": context.profile.timezone,
                    },
                ),
            )
        return calls

    async def _execute_tool_calls(
        self, tool_calls: list[ToolCall],
    ) -> list[ToolResult]:
        if len(tool_calls) >= 2:
            return list(await asyncio.gather(*[
                self._execute_single_tool(tc) for tc in tool_calls
            ]))
        if len(tool_calls) == 1:
            return [await self._execute_single_tool(tool_calls[0])]
        return []

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        tool = self._tools.get(tool_call.tool_name)
        if tool is None:
            logger.warning(
                "Tool '%s' became unavailable at execution time",
                tool_call.tool_name,
            )
            return ToolResult(
                tool_name=tool_call.tool_name,
                output="Tool is unavailable.",
                success=False,
            )
        try:
            return await tool.execute(tool_call)
        except Exception as exc:
            logger.exception(
                "Tool '%s' crashed during execution",
                tool_call.tool_name,
            )
            return ToolResult(
                tool_name=tool_call.tool_name,
                output=f"Tool crashed with exception: {exc}",
                success=False,
            )

    def _upgrade_session_protocol(self, context: AgentContext) -> AgentContext:
        skill_preferences: list[str] = []
        activation_msg: dict | None = None
        if context.active_skill is not None:
            skill = SkillCatalog.load_skill(
                self._skills_dir, context.active_skill.name,
            )
            context = ReactLoop._copy_context(context, active_skill=skill)
            skill_preferences = ExecutionContextCore.effective_skill_preferences(
                context.profile, skill.name,
            )
            filtered_schemas = ReactLoop.filter_tool_schemas(
                self._tool_schemas, skill,
            )
            activation_msg = ReactLoop.build_activation_message(
                skill, filtered_schemas,
            )
        return ReactLoop.upgrade_legacy_protocol(
            context,
            self._catalog_summaries,
            skill_preferences=skill_preferences,
            activation_msg=activation_msg,
        )

    def _activate_skill(
        self,
        context: AgentContext,
        *,
        skill_name: str,
        distilled_task: str,
    ) -> AgentContext:
        skill = SkillCatalog.load_skill(self._skills_dir, skill_name)
        filtered_schemas = ReactLoop.filter_tool_schemas(
            self._tool_schemas, skill)
        activation_msg = ReactLoop.build_activation_message(
            skill, filtered_schemas)
        skill_preferences = ExecutionContextCore.effective_skill_preferences(
            context.profile, skill.name,
        )
        logger.debug(
            "Activating skill=%s preferences=%s constraints=%s",
            skill.name,
            skill_preferences,
            context.request_constraints.model_dump(),
        )
        messages = ReactLoop.build_compact_execution_messages(
            context.profile,
            distilled_task,
            skill,
            activation_msg,
            skill_preferences=skill_preferences,
            request_constraints=context.request_constraints,
        )
        return AgentContext(
            task=distilled_task,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=context.catalog_summaries,
            active_skill=skill,
            messages=messages,
            iteration=0,
            tools_used=[],
            phase=AgentPhase.EXECUTION,
            selection_retry_used=context.selection_retry_used,
            execution_retry_used=context.execution_retry_used,
            request_constraints=context.request_constraints,
            protocol_version=context.protocol_version,
            outcome_evidence=[],
            terminal_failure_pending=False,
        )

    @staticmethod
    def _append_results_with_evidence(
        context: AgentContext,
        results: list[ToolResult],
    ) -> AgentContext:
        skill_name = (
            context.active_skill.name if context.active_skill is not None else ""
        )
        added = OutcomeCore.evidence_from_results(skill_name, results)
        evidence = list(context.outcome_evidence) + added
        return ReactLoop.append_tool_results(
            context,
            list(results),
            outcome_evidence=evidence,
        )

    @staticmethod
    def _operation_for_context(context: AgentContext) -> UserOperation:
        if context.active_skill is None:
            return UserOperation.REQUESTED_WORK
        return OutcomeCore.operation_for_skill(context.active_skill.name)

    @staticmethod
    def _failure_result(
        failure: AgentFailure,
        *,
        context: AgentContext | None = None,
        skill_name: str | None = None,
    ) -> AgentResult:
        if context is not None:
            operation = Agent._operation_for_context(context)
        elif skill_name:
            operation = OutcomeCore.operation_for_skill(skill_name)
        else:
            operation = UserOperation.REQUESTED_WORK
        return AgentResult(
            outcome=OutcomeCore.failure_from_agent(failure, operation),
        )
