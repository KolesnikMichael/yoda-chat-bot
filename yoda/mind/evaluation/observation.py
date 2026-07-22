"""Observation-capturing Mind/Agent Integrations for routing evaluation (TASK-021)."""

from __future__ import annotations

from pathlib import Path

from yoda.mind.agent.agent import Agent
from yoda.mind.agent.core.delivery_core import DeliveryCore
from yoda.mind.agent.data.agent_data import (
    AgentPhase,
    ExecutionDecision,
    ProtocolIssue,
    SelectionDecision,
    ToolCall,
)
from yoda.mind.agent.session_provider import AgentSessionProvider
from yoda.mind.agent.tools.tool_port import Tool
from yoda.mind.cognition import CognitionProvider
from yoda.mind.data.routing_context import RoutingContext
from yoda.mind.evaluation.data import (
    DeliveryObservation,
    DiagnosticOutcome,
    ExecutionObservation,
    IntentObservation,
    PlanningObservation,
    PromptIdentity,
    SelectionObservation,
    StageName,
    TurnObservation,
)
from yoda.mind.evaluation.prompt_identity_core import PromptIdentityCore
from yoda.mind.mind import Mind
from yoda.mind.perception.language import LanguageProvider


class ObservingCognitionProvider(CognitionProvider):
    def __init__(
        self,
        language_provider: LanguageProvider,
        *,
        prompt_sink: list[PromptIdentity] | None = None,
    ) -> None:
        super().__init__(language_provider)
        self.rejected = False
        self._prompt_sink = prompt_sink if prompt_sink is not None else []

    async def classify_intent(self, routing: RoutingContext) -> str:
        self.rejected = False
        try:
            return await super().classify_intent(routing)
        except Exception:
            self.rejected = True
            raise

    def _emit_intent_diagnostic(
        self,
        outcome: DiagnosticOutcome,
        *,
        detail: str | None = None,
    ) -> None:
        self._prompt_sink.append(PromptIdentityCore.intent_identity())
        super()._emit_intent_diagnostic(outcome, detail=detail)


class ObservingAgent(Agent):
    def __init__(
        self,
        *,
        language_provider: LanguageProvider,
        tools: list[Tool],
        skills_dir: Path,
        session_provider: AgentSessionProvider,
        turn_observation: TurnObservation,
        prompt_sink: list[PromptIdentity] | None = None,
    ) -> None:
        super().__init__(
            language_provider=language_provider,
            tools=tools,
            skills_dir=skills_dir,
            session_provider=session_provider,
        )
        self._turn_observation = turn_observation
        self._prompt_sink = prompt_sink if prompt_sink is not None else []

    def _emit_stage_diagnostic(
        self,
        stage: StageName,
        outcome: DiagnosticOutcome,
        *,
        prompts: tuple[PromptIdentity, ...] = (),
        detail: str | None = None,
    ) -> None:
        self._prompt_sink.extend(prompts)
        super()._emit_stage_diagnostic(
            stage,
            outcome,
            prompts=prompts,
            detail=detail,
        )

    async def _parse_selection(
        self,
        context,
    ) -> tuple[SelectionDecision | None, ProtocolIssue | None]:
        had_retry = context.selection_retry_used
        decision, issue = await super()._parse_selection(context)
        if decision is not None:
            mode = (
                "select_skill"
                if decision.mode == "select_skill"
                else "no_skill"
            )
            recovery = "corrected" if had_retry else "none"
            self._turn_observation.selection = SelectionObservation(
                mode=mode,
                decision=decision,
                recovery=recovery,
            )
        return decision, issue

    async def _parse_execution(
        self,
        context,
    ) -> tuple[ExecutionDecision | None, ProtocolIssue | None]:
        had_retry = context.execution_retry_used
        decision, issue = await super()._parse_execution(context)
        if decision is not None:
            planning = self._turn_observation.planning or PlanningObservation()
            planning.decisions.append(decision)
            planning.recovery = "corrected" if had_retry else planning.recovery
            self._turn_observation.planning = planning
        return decision, issue

    async def _execute_tool_calls(self, tool_calls: list[ToolCall]):
        planning = self._turn_observation.planning or PlanningObservation()
        planning.tool_calls.extend(tool_calls)
        self._turn_observation.planning = planning
        return await super()._execute_tool_calls(tool_calls)

    async def _handle_phase_issue(
        self,
        context,
        issue,
        *,
        prompts: tuple[PromptIdentity, ...] = (),
    ):
        result = await super()._handle_phase_issue(context, issue, prompts=prompts)
        if hasattr(result, "outcome") and getattr(result, "outcome", None) is not None:
            stage = issue.stage
            if stage is AgentPhase.SELECTION:
                self._turn_observation.selection = SelectionObservation(
                    mode="protocol_exhausted",
                    recovery="exhausted",
                )
            elif stage is AgentPhase.EXECUTION:
                planning = self._turn_observation.planning or PlanningObservation()
                planning.recovery = "exhausted"
                self._turn_observation.planning = planning
        return result

    async def run(self, **kwargs):
        result = await super().run(**kwargs)
        self._turn_observation.execution = ExecutionObservation(agent_result=result)
        return result

    async def run_with_skill(self, **kwargs):
        result = await super().run_with_skill(**kwargs)
        self._turn_observation.execution = ExecutionObservation(agent_result=result)
        return result

    async def resume(self, chat_id: int, user_answer: str):
        result = await super().resume(chat_id, user_answer)
        self._turn_observation.execution = ExecutionObservation(agent_result=result)
        return result


class ObservingMind(Mind):
    def __init__(
        self,
        *,
        turn_observation: TurnObservation,
        prompt_sink: list[PromptIdentity] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._turn_observation = turn_observation
        self._prompt_sink = prompt_sink if prompt_sink is not None else []

    def _emit_intent_diagnostic(
        self,
        outcome: DiagnosticOutcome,
        *,
        detail: str | None = None,
        include_prompt: bool = False,
    ) -> None:
        if include_prompt:
            self._prompt_sink.append(PromptIdentityCore.intent_identity())
        super()._emit_intent_diagnostic(
            outcome,
            detail=detail,
            include_prompt=include_prompt,
        )

    def _emit_delivery_diagnostic(
        self,
        outcome: DiagnosticOutcome,
        *,
        detail: str | None = None,
    ) -> None:
        self._prompt_sink.append(PromptIdentityCore.delivery_identity())
        super()._emit_delivery_diagnostic(outcome, detail=detail)

    async def _classify_intent(
        self,
        chat_id: int,
        routing: RoutingContext,
    ) -> str:
        intent = await super()._classify_intent(chat_id, routing)
        rejected = (
            isinstance(self.cognition_provider, ObservingCognitionProvider)
            and self.cognition_provider.rejected
        )
        route = "rejected_fallback_chat" if rejected else intent
        if route == "pass":
            route = "chat"
        self._turn_observation.intent = IntentObservation(route=route)
        return intent

    async def _deliver_via_core(self, **kwargs) -> None:
        payload = DeliveryCore.build_payload(kwargs["result"])
        self._turn_observation.delivery = DeliveryObservation(payload=payload)
        await super()._deliver_via_core(**kwargs)
