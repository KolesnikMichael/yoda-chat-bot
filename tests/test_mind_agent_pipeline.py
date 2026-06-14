import pytest

from yoda.mind.affect import AffectProvider
from yoda.mind.mind import Mind
from yoda.mind.memory.data.pending_message import PendingMessage
from yoda.mind.agent.data.agent_data import AgentResult
from yoda.mind.perception.perception import Perception

from tests.fakes import (
    FakeAudioProvider,
    FakeCognitionProvider,
    FakeLanguageProvider,
    FakeMemoryProvider,
    FakeSender,
    FakeVisionProvider,
)


class FakeAgentProvider:
    def __init__(self, result=None, has_session=False):
        self._result = result or AgentResult(answer="Done!")
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
    ):
        self.run_with_skill_calls.append(
            (skill_name, task, profile, chat_id, user_id))
        return self._result

    async def resume(self, chat_id, user_answer):
        self.resume_calls.append((chat_id, user_answer))
        return self._result


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
    agent = FakeAgentProvider(result=agent_result, has_session=has_session)
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        perception=_default_perception(),
        memory_provider=memory,
        affect_provider=AffectProvider(),
        cognition_provider=cognition,
        agent_provider=agent,
    )
    mind.bind_message_sender(sender)
    return mind, lang, agent, memory, sender


@pytest.mark.asyncio
async def test_chat_intent_goes_to_yoda():
    mind, lang, agent, memory, sender = _build_mind(intent="chat")

    await mind.process_message_batch(1, [_make_pending("hi there", user_id=1)])

    assert len(sender.calls) == 1
    assert len(agent.run_calls) == 0


def _system_task_lines(conversation) -> list[str]:
    return [
        m.text for m in conversation.messages
        if m.role == "system" and "Agent completed a task" in m.text
    ]


@pytest.mark.asyncio
async def test_agent_task_stores_tools_used_single():
    agent_result = AgentResult(
        answer="Weather is sunny", tools_used=["search_web"],
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("what's the weather?", user_id=1)])

    conversation = memory.get_conversation(1)
    lines = _system_task_lines(conversation)
    assert len(lines) == 1
    assert "Tools used: search_web" in lines[0]
    assert "Result: Weather is sunny" in lines[0]


@pytest.mark.asyncio
async def test_agent_task_stores_tools_used_none_when_empty():
    agent_result = AgentResult(answer="Done!", tools_used=[])
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(1, [_make_pending("do it", user_id=1)])

    conversation = memory.get_conversation(1)
    lines = _system_task_lines(conversation)
    assert len(lines) == 1
    assert "Tools used: none" in lines[0]


@pytest.mark.asyncio
async def test_agent_task_stores_tools_used_order():
    agent_result = AgentResult(
        answer="Done", tools_used=["search_web", "update_profile"],
    )
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(1, [_make_pending("task", user_id=1)])

    conversation = memory.get_conversation(1)
    lines = _system_task_lines(conversation)
    assert "Tools used: search_web, update_profile" in lines[0]


@pytest.mark.asyncio
async def test_agent_clarification_has_no_tools_used():
    agent_result = AgentResult(clarification="What timezone are you in?")
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me later", user_id=1)])

    conversation = memory.get_conversation(1)
    for m in conversation.messages:
        if m.role == "system":
            assert "Tools used:" not in m.text


@pytest.mark.asyncio
async def test_deliver_scheduled_reminder_has_no_tools_used():
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
    for m in conversation.messages:
        assert "Tools used:" not in m.text


@pytest.mark.asyncio
async def test_agent_task_delegates_to_agent():
    agent_result = AgentResult(answer="Reminder set for 15:30")
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me in 30 minutes", user_id=1)])

    assert len(agent.run_calls) == 1
    assert agent.run_calls[0][0] == "remind me in 30 minutes"
    recent = agent.run_calls[0][4]
    assert len(recent) == 1
    assert "User profile snapshot" in recent[0]["content"]
    assert "Europe/Moscow" in recent[0]["content"]
    assert len(sender.calls) == 1
    assert "Reminder set for 15:30" in sender.calls[0][1]


@pytest.mark.asyncio
async def test_agent_resume_delegates_to_resume():
    agent_result = AgentResult(answer="OK, Moscow time")
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
    agent_result = AgentResult(clarification="What timezone are you in?")
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me later", user_id=1)])

    assert len(sender.calls) == 1
    reply_text = sender.calls[0][1]
    assert "What timezone are you in?" in reply_text


@pytest.mark.asyncio
async def test_no_agent_provider_defaults_to_chat():
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
    agent_result = AgentResult(answer="USD/RUB is 92.5")
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
    assert len(sender.calls) == 1
