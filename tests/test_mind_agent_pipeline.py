import pytest

from yoda.mind.affect import AffectProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.data.pending_message import PendingMessage
from yoda.mind.agent.core.delivery_core import DELIVERY_INSTRUCTION_PREFIX
from yoda.mind.agent.core.outcome_core import OutcomeCore
from yoda.mind.agent.data.agent_data import AgentResult, RequestConstraints
from yoda.mind.agent.data.outcome_data import (
    ClarificationResult,
    OutcomeStatus,
    ResultKind,
    SafeFailureCategory,
    UserOperation,
)
from yoda.mind.perception.perception import Perception

from tests.fakes import (
    FakeAudioProvider,
    FakeCognitionProvider,
    FakeLanguageProvider,
    FakeMemoryProvider,
    FakeSender,
    FakeVisionProvider,
)


class FakeAgent:
    def __init__(self, result=None, has_session=False):
        self._result = result or AgentResult(
            outcome=ExecutionOutcome_success("Done!"),
        )
        self._has_session = has_session
        self.run_calls = []
        self.run_with_skill_calls = []
        self.resume_calls = []

    async def has_pending_session(self, chat_id):
        return self._has_session

    async def run(self, task, profile, chat_id, user_id=0, recent_messages=None):
        self.run_calls.append((task, profile, chat_id, user_id, recent_messages))
        return self._result

    async def run_with_skill(
        self, *, skill_name, task, profile, chat_id, user_id=0,
        request_constraints=None,
    ):
        self.run_with_skill_calls.append(
            (skill_name, task, profile, chat_id, user_id, request_constraints))
        return self._result

    async def resume(self, chat_id, user_answer):
        self.resume_calls.append((chat_id, user_answer))
        return self._result


def ExecutionOutcome_success(summary: str):
    from yoda.mind.agent.data.outcome_data import ExecutionOutcome

    return ExecutionOutcome(
        operation=UserOperation.RETRIEVE_INFORMATION,
        status=OutcomeStatus.SUCCESS,
        summary=summary,
        result_kind=ResultKind.INFORMATION,
    )


def _make_pending(text="Hello", user_id=1, message_id: int = 100) -> PendingMessage:
    return PendingMessage(
        user_id=user_id,
        message_id=message_id,
        user_info={"first_name": "Luke", "last_active": "now"},
        media_type="text",
        text=text,
        photo_file_paths=[],
        caption="",
        audio_file_path="",
        media_group_id=None,
        timestamp="2026-03-20 15:00:00+00:00",
    )


def _default_perception() -> Perception:
    return Perception(
        audio_provider=FakeAudioProvider(),
        vision_provider=FakeVisionProvider(),
    )


def _build_mind(intent="chat", agent_result=None, has_session=False):
    lang = FakeLanguageProvider()
    cognition = FakeCognitionProvider(intent=intent)
    agent = FakeAgent(result=agent_result, has_session=has_session)
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=cognition,
        agent=agent,
    )
    mind.bind_message_sender(sender)
    return mind, lang, agent, memory, sender


def _grounded_lines(conversation) -> list[str]:
    return [
        m.text for m in conversation.messages
        if m.role == "system" and m.text.startswith(DELIVERY_INSTRUCTION_PREFIX)
    ]


@pytest.mark.asyncio
async def test_chat_intent_goes_to_yoda():
    mind, lang, agent, memory, sender = _build_mind(intent="chat")

    await mind.process_message_batch(1, [_make_pending("hi there", user_id=1)])

    assert len(sender.calls) == 1
    assert len(agent.run_calls) == 0


@pytest.mark.asyncio
async def test_agent_task_stores_grounded_delivery_instruction():
    agent_result = AgentResult(
        outcome=ExecutionOutcome_success("Weather is sunny"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("what's the weather?", user_id=1)])

    conversation = memory.get_conversation(1)
    lines = _grounded_lines(conversation)
    assert len(lines) == 1
    assert "operation_completed" in lines[0]
    assert "Weather is sunny" in lines[0]
    assert "search_web" not in lines[0]
    assert "Tools used:" not in lines[0]


@pytest.mark.asyncio
async def test_agent_clarification_has_no_success_claims():
    agent_result = AgentResult(
        clarification=ClarificationResult(question="What timezone are you in?"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me later", user_id=1)])

    conversation = memory.get_conversation(1)
    lines = _grounded_lines(conversation)
    assert len(lines) == 1
    assert "status=clarification" in lines[0]
    assert "operation_completed" not in lines[0]
    assert "Tools used:" not in lines[0]


@pytest.mark.asyncio
async def test_deliver_scheduled_reminder_prohibits_live_recomputation():
    lang = FakeLanguageProvider()
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=None,
    )
    mind.bind_message_sender(sender)

    await mind.deliver_scheduled_reminder(42, 42, "call mom")

    conversation = memory.get_conversation(42)
    lines = _grounded_lines(conversation)
    assert len(lines) == 1
    assert "stored_text_delivered" in lines[0]
    assert "live_recomputation" in lines[0]
    assert "Tools used:" not in lines[0]
    assert "call mom" in lines[0]


@pytest.mark.asyncio
async def test_agent_task_delegates_to_agent():
    agent_result = AgentResult(
        outcome=ExecutionOutcome_success("Reminder set for 15:30"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me in 30 minutes", user_id=1)])

    assert len(agent.run_calls) == 1
    assert agent.run_calls[0][0] == "remind me in 30 minutes"
    recent = agent.run_calls[0][4]
    assert recent == []
    assert len(sender.calls) == 1
    assert "Reminder set for 15:30" in sender.calls[0][1]


@pytest.mark.asyncio
async def test_agent_resume_delegates_to_resume():
    agent_result = AgentResult(
        outcome=ExecutionOutcome_success("OK, Moscow time"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="chat",
        agent_result=agent_result,
        has_session=True,
    )

    await mind.process_message_batch(
        42, [_make_pending("Europe/Moscow", user_id=42)])

    assert len(agent.resume_calls) == 1
    assert agent.resume_calls[0] == (42, "Europe/Moscow")
    assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_agent_clarification_prompts_user():
    agent_result = AgentResult(
        clarification=ClarificationResult(question="What timezone are you in?"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me later", user_id=1)])

    assert len(sender.calls) == 1
    reply_text = sender.calls[0][1]
    assert "What timezone are you in?" in reply_text


@pytest.mark.asyncio
async def test_no_agent_defaults_to_chat():
    lang = FakeLanguageProvider()
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=None,
    )
    mind.bind_message_sender(sender)

    await mind.process_message_batch(1, [_make_pending("remind me", user_id=1)])

    assert len(sender.calls) == 1
    assert len(lang.reply_calls) == 1


@pytest.mark.asyncio
async def test_deliver_scheduled_reminder():
    lang = FakeLanguageProvider()
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=None,
    )
    mind.bind_message_sender(sender)

    await mind.deliver_scheduled_reminder(42, 42, "call mom")

    assert len(sender.calls) == 1
    assert "call mom" in sender.calls[0][1]
    conversation = memory.get_conversation(42)
    assert conversation is not None
    system_msgs = [m for m in conversation.messages if m.role == "system"]
    assert any("call mom" in m.text for m in system_msgs)
    assert "private Telegram chat" in conversation.messages[0].text


@pytest.mark.asyncio
async def test_deliver_scheduled_reminder_group_prompt():
    lang = FakeLanguageProvider()
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=None,
    )
    mind.bind_message_sender(sender)

    await mind.deliver_scheduled_reminder(1000, 42, "team sync")

    conversation = memory.get_conversation(1000)
    assert conversation is not None
    assert "Telegram group chat" in conversation.messages[0].text


@pytest.mark.asyncio
async def test_execute_scheduled_task_delegates_to_agent():
    agent_result = AgentResult(
        outcome=ExecutionOutcome_success("USD/RUB is 92.5"),
    )
    mind, lang, agent, memory, sender = _build_mind(
        agent_result=agent_result,
    )

    await mind.execute_scheduled_task(
        chat_id=1,
        user_id=7,
        skill_name="search_web",
        distilled_task="Find today's USD/RUB rate",
    )

    assert len(agent.run_with_skill_calls) == 1
    assert agent.run_with_skill_calls[0][0] == "search_web"
    assert agent.run_with_skill_calls[0][1] == "Find today's USD/RUB rate"
    assert agent.run_with_skill_calls[0][5] == RequestConstraints()
    assert len(sender.calls) == 1


@pytest.mark.asyncio
async def test_execute_scheduled_task_passes_constraints_not_merged_with_profile():
    agent_result = AgentResult(outcome=ExecutionOutcome_success("ok"))
    mind, lang, agent, memory, sender = _build_mind(
        agent_result=agent_result,
    )

    constraints = RequestConstraints(strict_source_domains=["strict.example"])
    await mind.execute_scheduled_task(
        chat_id=1,
        user_id=7,
        skill_name="search_web",
        distilled_task="Find weather only from strict.example",
        request_constraints=constraints,
    )

    call = agent.run_with_skill_calls[0]
    assert call[1] == "Find weather only from strict.example"
    assert call[5] == constraints
    assert call[2].timezone == "Europe/Moscow"


@pytest.mark.asyncio
async def test_agent_failure_maps_to_safe_instruction():
    agent_result = AgentResult(
        outcome=OutcomeCore.failure(
            UserOperation.REQUESTED_WORK,
            SafeFailureCategory.TRANSIENT,
        ),
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result,
    )

    await mind.process_message_batch(1, [_make_pending("do it", user_id=1)])

    conversation = memory.get_conversation(1)
    system_lines = [
        m.text for m in conversation.messages if m.role == "system"
    ]
    joined = "\n".join(system_lines)
    assert any(DELIVERY_INSTRUCTION_PREFIX in line for line in system_lines)
    assert "failure_category=transient" in joined or "try_later" in joined
    assert "protocol_exhausted" not in joined
    assert "malformed_output" not in joined
    assert "AgentPhase" not in joined
    assert "Unknown tool" not in joined
    assert "search_web" not in joined


@pytest.mark.asyncio
async def test_notify_scheduled_failure_is_category_only():
    lang = FakeLanguageProvider()
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=None,
    )
    mind.bind_message_sender(sender)

    await mind.notify_scheduled_failure(99)

    conversation = memory.get_conversation(99)
    lines = _grounded_lines(conversation)
    assert len(lines) == 1
    assert "try_later" in lines[0]
    assert "RuntimeError" not in lines[0]
    assert "exception" not in lines[0].lower()
