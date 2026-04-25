import asyncio
import datetime as dtm
import logging
from pathlib import Path

from yoda.mind.agent.core.react_loop import ReactLoop
from yoda.mind.agent.data.agent_data import (
    AgentContext,
    AgentResult,
    Decision,
    ToolCall,
    ToolResult,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.skills.catalog import SkillCatalog
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.perception.language import LanguageProvider

logger = logging.getLogger(__name__)

_MAX_PHASE1_ROUNDS = 5


class AgentProvider:
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
        )

        system_msg = ReactLoop.build_system_message(profile)
        selection_msg = ReactLoop.build_selection_message(
            task,
            self._catalog_summaries,
            recent_messages=recent_messages,
        )
        context = context.with_messages([system_msg, selection_msg])

        context, decision, early = await self._run_until_skill_or_answer(context)
        if early is not None:
            if early.answer is not None:
                await self._sessions.delete(context.chat_id)
            return early
        assert decision is not None
        context = self._activate_skill_context(context, decision)
        return await self._execute_loop(context)

    async def resume(self, chat_id: int, user_answer: str) -> AgentResult:
        context = await self._sessions.load(chat_id)
        if context is None:
            return AgentResult(answer="No pending session found.")

        answer_msg = {"role": "user", "content": f"User answered: {user_answer}"}
        context = context.with_messages(context.messages + [answer_msg])

        if context.active_skill is None:
            context, decision, early = await self._run_until_skill_or_answer(context)
            if early is not None:
                if early.answer is not None:
                    await self._sessions.delete(context.chat_id)
                return early
            assert decision is not None
            context = self._activate_skill_context(context, decision)

        return await self._execute_loop(context)

    async def _execute_loop(self, context: AgentContext) -> AgentResult:
        nudge_used = False
        last_success_output: str | None = None
        decision: Decision | None = None

        while not ReactLoop.is_done(context):
            decision = await self._llm_decide(context)
            logger.info(
                f"Loop iteration {context.iteration}: "
                f"tools={[tc.tool_name for tc in decision.effective_tool_calls]}, "
                f"final={decision.final_answer}, reasoning={decision.reasoning}")
            decision = ReactLoop.validate_decision(
                decision, context, self._available_tools_for_validation(context))
            context = ReactLoop.append_assistant(context, decision)

            if decision.final_answer:
                break

            if not decision.effective_tool_calls:
                if not nudge_used:
                    logger.warning("LLM returned no tool_calls and no final_answer, nudging")
                    nudge_msg = {
                        "role": "user",
                        "content": (
                            "You must call a tool via tool_calls or set final_answer. "
                            "Do not just describe your plan — act now."
                        ),
                    }
                    context = context.with_messages(
                        context.messages + [nudge_msg])
                    nudge_used = True
                    continue
                logger.warning("LLM still returned no tool_calls after nudge, stopping loop")
                break

            tool_calls = self._build_tool_calls(context, decision)
            results = await self._execute_tool_calls(tool_calls)

            suspended = next((r for r in results if r.suspend), None)
            if suspended:
                context = ReactLoop.append_tool_results(
                    context, list(results))
                await self._sessions.save(context)
                return AgentResult(clarification=suspended.output)

            for r in results:
                if r.success:
                    last_success_output = r.output

            terminal_completed = any(
                r.success and self._tools[r.tool_name].terminal
                for r in results
                if r.tool_name in self._tools
            )
            if terminal_completed:
                logger.info("Terminal tool succeeded, finishing loop")
                context = ReactLoop.append_tool_results(
                    context, list(results))
                break

            context = ReactLoop.append_tool_results(context, list(results))

        await self._sessions.delete(context.chat_id)

        final_answer = (
            (decision.final_answer if decision else None)
            or last_success_output
            or "Task completed."
        )
        return AgentResult(answer=final_answer, tools_used=context.tools_used)

    def _available_tools_for_validation(self, context: AgentContext) -> set[str]:
        if context.active_skill is None:
            return set(self._tools.keys())
        return (
            ReactLoop.allowed_tool_names_for_skill(context.active_skill)
            & set(self._tools.keys())
        )

    @staticmethod
    def _build_tool_calls(context: AgentContext, decision: Decision) -> list[ToolCall]:
        return [
            ToolCall(
                tool_name=tc.tool_name,
                arguments=tc.arguments,
                metadata={
                    "chat_id": context.chat_id,
                    "user_id": context.user_id,
                    "profile_timezone": context.profile.timezone,
                },
            )
            for tc in decision.effective_tool_calls
        ]

    async def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        return await asyncio.gather(*[
            self._execute_single_tool(tc) for tc in tool_calls
        ])

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

    async def _llm_decide(self, context: AgentContext) -> Decision:
        utc_now = f"{dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        messages = ReactLoop.build_context(context, utc_now)
        return await self._llm.parse_structured(messages, Decision)

    async def _run_until_skill_or_answer(
        self,
        context: AgentContext,
    ) -> tuple[AgentContext, Decision | None, AgentResult | None]:
        """Phase 1 loop: skill selection, decline, or infra tool calls (e.g. ask_user)."""
        available = self._available_tools_for_validation(context)
        for _ in range(_MAX_PHASE1_ROUNDS):
            decision = await self._llm_decide(context)
            logger.info(
                "Phase 1 decision: skill=%s, final=%s, reasoning=%s",
                decision.selected_skill,
                decision.final_answer,
                decision.reasoning,
            )
            decision = ReactLoop.validate_decision(
                decision, context, available)
            context = ReactLoop.append_assistant(context, decision)

            if decision.final_answer:
                return context, None, AgentResult(answer=decision.final_answer)

            if decision.selected_skill:
                return context, decision, None

            if decision.effective_tool_calls:
                tool_calls = self._build_tool_calls(context, decision)
                results = await self._execute_tool_calls(tool_calls)
                suspended = next((r for r in results if r.suspend), None)
                if suspended:
                    context = ReactLoop.append_tool_results(
                        context, list(results))
                    await self._sessions.save(context)
                    return context, None, AgentResult(
                        clarification=suspended.output)

                context = ReactLoop.append_tool_results(
                    context, list(results))
                continue

            return context, None, AgentResult(
                answer="Invalid Phase 1: expected tool_calls.")

        return context, None, AgentResult(
            answer="Selection phase exceeded iteration limit.")

    def _activate_skill_context(
        self,
        context: AgentContext,
        decision: Decision,
    ) -> AgentContext:
        assert decision.selected_skill
        skill = SkillCatalog.load_skill(
            self._skills_dir, decision.selected_skill)
        raw_distill = (decision.distilled_task or "").strip()
        distilled = raw_distill or context.task
        if not raw_distill:
            logger.warning(
                "Phase 1 returned empty distilled_task; using prior task text")
        filtered_schemas = ReactLoop.filter_tool_schemas(
            self._tool_schemas, skill)
        activation_msg = ReactLoop.build_activation_message(
            skill, filtered_schemas)
        messages = ReactLoop.build_compact_execution_messages(
            context.profile, distilled, skill, activation_msg)
        return AgentContext(
            task=distilled,
            profile=context.profile,
            chat_id=context.chat_id,
            user_id=context.user_id,
            catalog_summaries=context.catalog_summaries,
            active_skill=skill,
            messages=messages,
            iteration=0,
            tools_used=[],
        )
