import pytest

from yoda.mind.affect import AffectProvider
from yoda.mind.memory.memory import MemoryCore
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.pending_message import PendingMessage
from yoda.mind.memory.data.user_profile import UserProfile
from yoda.mind.mind import Mind
from yoda.mind.agent.data.agent_data import AgentResult
from yoda.mind.cognition import IntentClassification


class FakeMemoryProvider:
    def __init__(self):
        self.sender_updates = []
        self.chat_updates = []
        self._conversations: dict[str, Conversation] = {}

    async def update_sender_info(self, user_id, chat_id, user_info):
        self.sender_updates.append((user_id, chat_id, user_info))

    async def update_chat_info(self, chat_id, chat_type, last_active):
        self.chat_updates.append((chat_id, chat_type, last_active))

    def get_conversation(self, chat_id):
        key = MemoryCore.conversation_key(chat_id)
        return self._conversations.get(key)

    def save_conversation(self, conversation):
        key = MemoryCore.conversation_key(conversation.chat_id)
        self._conversations[key] = conversation

    async def get_user_profile(self, user_id, chat_id):
        return UserProfile(timezone="Europe/Moscow")


class FakeLanguageProvider:
    def __init__(self, intent="chat"):
        self._intent = intent
        self.reply_calls = []

    async def reply_in_conversation(self, conversation):
        self.reply_calls.append(conversation)
        return f"reply:{conversation[-1]['content']}"

    async def parse_structured(self, messages, response_format):
        return IntentClassification(intent=self._intent)


class FakeAgentProvider:
    def __init__(self, result=None, has_session=False):
        self._result = result or AgentResult(answer="Done!")
        self._has_session = has_session
        self.run_calls = []
        self.resume_calls = []

    async def has_pending_session(self, chat_id):
        return self._has_session

    async def run(self, task, profile, chat_id, user_id=0):
        self.run_calls.append((task, profile, chat_id, user_id))
        return self._result

    async def resume(self, chat_id, user_answer):
        self.resume_calls.append((chat_id, user_answer))
        return self._result


class FakeSender:
    def __init__(self):
        self.calls = []

    async def __call__(self, chat_id, message):
        self.calls.append((chat_id, message))


def _make_pending(text="Hello", user_id=1) -> PendingMessage:
    return PendingMessage(
        user_id=user_id,
        user_info={"first_name": "Luke", "last_active": "now"},
        media_type="text",
        text=text,
        photo_file_paths=[],
        caption="",
        audio_file_path="",
        media_group_id=None,
        timestamp="2026-03-20 15:00:00+00:00",
    )


def _build_mind(intent="chat", agent_result=None, has_session=False):
    lang = FakeLanguageProvider(intent=intent)
    agent = FakeAgentProvider(result=agent_result, has_session=has_session)
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        vision_provider=None,
        audio_provider=None,
        memory_provider=memory,
        affect_provider=AffectProvider(),
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


@pytest.mark.asyncio
async def test_agent_task_delegates_to_agent():
    agent_result = AgentResult(answer="Reminder set for 15:30")
    mind, lang, agent, memory, sender = _build_mind(
        intent="agent_task", agent_result=agent_result)

    await mind.process_message_batch(
        1, [_make_pending("remind me in 30 minutes", user_id=1)])

    assert len(agent.run_calls) == 1
    assert agent.run_calls[0][0] == "remind me in 30 minutes"
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
    lang = FakeLanguageProvider(intent="agent_task")
    memory = FakeMemoryProvider()
    sender = FakeSender()
    mind = Mind(
        language_provider=lang,
        vision_provider=None,
        audio_provider=None,
        memory_provider=memory,
        affect_provider=AffectProvider(),
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
        vision_provider=None,
        audio_provider=None,
        memory_provider=memory,
        affect_provider=AffectProvider(),
    )
    mind.bind_message_sender(sender)

    await mind.deliver_scheduled_reminder(42, "call mom")

    assert len(sender.calls) == 1
    assert "call mom" in sender.calls[0][1]
    conversation = memory.get_conversation(42)
    assert conversation is not None
    system_msgs = [m for m in conversation.messages if m.role == "system"]
    assert any("call mom" in m.text for m in system_msgs)
