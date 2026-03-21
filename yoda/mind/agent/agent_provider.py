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
    ) -> AgentResult:
        context = AgentContext(
            task=task,
            profile=profile,
            chat_id=chat_id,
            user_id=user_id,
            catalog_summaries=self._catalog_summaries,
        )

        decision = await self._llm_decide(context)
        logger.info(f"Phase 1 decision: skill={decision.selected_skill}, "
                     f"final={decision.final_answer}, reasoning={decision.reasoning}")
        decision = ReactLoop.validate_decision(
            decision, context, set(self._tools.keys()))

        if decision.final_answer:
            return AgentResult(answer=decision.final_answer)

        if decision.selected_skill:
            skill = SkillCatalog.load_skill(
                self._skills_dir, decision.selected_skill)
            context = context.with_active_skill(skill)

        return await self._execute_loop(context)

    async def resume(self, chat_id: int, user_answer: str) -> AgentResult:
        context = await self._sessions.load(chat_id)
        if context is None:
            return AgentResult(answer="No pending session found.")

        answer_result = ToolResult(
            tool_name="ask_user", output=user_answer, success=True)
        context = ReactLoop.observe(context, [answer_result])
        return await self._execute_loop(context)

    async def _execute_loop(self, context: AgentContext) -> AgentResult:
        nudge_used = False
        last_success_output: str | None = None

        while not ReactLoop.is_done(context):
            decision = await self._llm_decide(context)
            logger.info(
                f"Loop iteration {context.iteration}: "
                f"tools={[tc.tool_name for tc in decision.effective_tool_calls]}, "
                f"final={decision.final_answer}, reasoning={decision.reasoning}")
            decision = ReactLoop.validate_decision(
                decision, context, set(self._tools.keys()))

            if decision.final_answer:
                break

            if not decision.effective_tool_calls:
                if not nudge_used:
                    logger.warning("LLM returned no tool_calls and no final_answer, nudging")
                    nudge = ToolResult(
                        tool_name="system",
                        output="You must call a tool via tool_calls or set final_answer. "
                               "Do not just describe your plan — act now.",
                        success=True,
                    )
                    context = ReactLoop.observe(context, [nudge])
                    nudge_used = True
                    continue
                logger.warning("LLM still returned no tool_calls after nudge, stopping loop")
                break

            tool_calls = [
                ToolCall(
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                    metadata={"chat_id": context.chat_id, "user_id": context.user_id},
                )
                for tc in decision.effective_tool_calls
            ]

            results = await asyncio.gather(*[
                self._tools[tc.tool_name].execute(tc)
                for tc in tool_calls
            ])

            suspended = next((r for r in results if r.suspend), None)
            if suspended:
                context = ReactLoop.observe(context, list(results))
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
                context = ReactLoop.observe(context, list(results))
                break

            context = ReactLoop.observe(context, list(results))

        await self._sessions.delete(context.chat_id)

        final = decision.final_answer or last_success_output or "Task completed."
        return AgentResult(answer=final, tools_used=context.tools_used)

    async def _llm_decide(self, context: AgentContext) -> Decision:
        utc_now = f"{dtm.datetime.now(dtm.UTC):%Y-%m-%d %H:%M UTC}"
        messages = ReactLoop.build_context(
            context, self._tool_schemas, utc_now)
        return await self._llm.parse_structured(messages, Decision)
