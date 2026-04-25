from yoda.mind.cognition import CognitionCore
from yoda.mind.memory.data.conversation import Conversation
from yoda.mind.memory.data.message import Message


def test_build_intent_messages_structure():
    messages = CognitionCore.build_intent_messages("remind me to call mom")

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "remind me to call mom"
    assert "agent_task" in messages[0]["content"]
    assert "chat" in messages[0]["content"]
    assert "Recent conversation" in messages[0]["content"]


def test_build_intent_context_messages_none():
    assert CognitionCore.build_intent_context_messages(None) == []


def test_build_intent_context_messages_empty_conversation():
    conv = Conversation(chat_id=1, messages=[])
    assert CognitionCore.build_intent_context_messages(conv) == []


def test_build_intent_context_messages_only_bootstrap_system():
    conv = Conversation(
        chat_id=1, messages=[Message(role="system", text="bootstrap")])
    assert CognitionCore.build_intent_context_messages(conv) == []


def test_build_intent_context_messages_excludes_bootstrap_tail():
    conv = Conversation(
        chat_id=1,
        messages=[
            Message(role="system", text="bootstrap"),
            Message(role="user", text="u1"),
            Message(role="assistant", text="a1"),
            Message(role="system", text="Agent completed: ok"),
        ],
    )
    out = CognitionCore.build_intent_context_messages(conv)
    assert out == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "system", "content": "Agent completed: ok"},
    ]


def test_build_intent_context_messages_limit_four():
    tail = [Message(role="user", text=f"m{i}") for i in range(6)]
    conv = Conversation(
        chat_id=1,
        messages=[Message(role="system", text="b"), *tail],
    )
    out = CognitionCore.build_intent_context_messages(conv)
    assert len(out) == 4
    assert [m["content"] for m in out] == ["m2", "m3", "m4", "m5"]


def test_build_routing_context():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "hello"',
         "timestamp": "2026-03-20"},
    ]
    conv = Conversation(
        chat_id=1,
        messages=[
            Message(role="system", text="bootstrap"),
            Message(role="user", text="prior"),
            Message(
                role="system",
                text='On 2026-03-20 Luke sent text message: "hello"',
            ),
        ],
    )
    rc = CognitionCore.build_routing_context(perceived, conv)
    assert rc.current_user_text == "hello"
    assert rc.recent_messages == [{"role": "user", "content": "prior"}]


def test_build_intent_context_messages_exclude_trailing():
    conv = Conversation(
        chat_id=1,
        messages=[
            Message(role="system", text="bootstrap"),
            Message(role="user", text="old"),
            Message(role="system", text="current turn line"),
        ],
    )
    assert CognitionCore.build_intent_context_messages(
        conv, exclude_trailing=1) == [{"role": "user", "content": "old"}]
    assert CognitionCore.build_intent_context_messages(
        conv, exclude_trailing=2) == []


def test_build_intent_messages_with_recent_messages():
    recent = [
        {"role": "assistant", "content": "Done."},
        {"role": "user", "content": 'On 2026-03-20 Luke sent text message: "remind at 5"'},
    ]
    messages = CognitionCore.build_intent_messages(
        "make it 6pm", recent_messages=recent)

    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    body = messages[1]["content"]
    assert body.startswith("Recent conversation (newest last):\n")
    assert "[assistant] Done." in body
    assert "[user]" in body
    assert "remind at 5" in body
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "make it 6pm"


def test_extract_user_text_from_text_message():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "remind me in 30 min"',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "remind me in 30 min"


def test_extract_user_text_from_voice_message():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent voice message: "call mom later"',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "call mom later"


def test_extract_user_text_joins_multiple_text_messages():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "first"',
         "timestamp": "2026-03-20"},
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "second"',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "first\nsecond"


def test_extract_user_text_empty_for_photo_only():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent 1 image(s):\n[Photo 1]: a cat',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == ""


def test_extract_user_text_includes_photo_caption():
    perceived = [
        {
            "role": "system",
            "text": (
                'On 2026-03-20 Luke sent 1 image(s) with caption "remind me at 5" :\n'
                "[Photo 1]: a cat"
            ),
            "timestamp": "2026-03-20",
        },
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "remind me at 5"


def test_extract_user_text_mixed_text_photo_caption_voice():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "please"',
         "timestamp": "2026-03-20"},
        {
            "role": "system",
            "text": (
                'On 2026-03-20 Luke sent 1 image(s) with caption "see this" :\n'
                "[Photo 1]: desc"
            ),
            "timestamp": "2026-03-20",
        },
        {
            "role": "system",
            "text": 'On 2026-03-20 Luke sent voice message: "schedule it for 6pm"',
            "timestamp": "2026-03-20",
        },
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "please\nsee this\nschedule it for 6pm"


def test_extract_user_text_empty_for_no_entries():
    assert CognitionCore.extract_user_text([]) == ""
