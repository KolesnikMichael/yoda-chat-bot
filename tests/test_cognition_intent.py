from yoda.mind.cognition import CognitionCore


def test_build_intent_messages_structure():
    messages = CognitionCore.build_intent_messages("remind me to call mom")

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "remind me to call mom"
    assert "agent_task" in messages[0]["content"]
    assert "chat" in messages[0]["content"]


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


def test_extract_user_text_takes_last_entry():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "first"',
         "timestamp": "2026-03-20"},
        {"role": "system", "text": 'On 2026-03-20 Luke sent text message: "second"',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == "second"


def test_extract_user_text_empty_for_photo_only():
    perceived = [
        {"role": "system", "text": 'On 2026-03-20 Luke sent 1 image(s):\n[Photo 1]: a cat',
         "timestamp": "2026-03-20"},
    ]

    text = CognitionCore.extract_user_text(perceived)

    assert text == ""


def test_extract_user_text_empty_for_no_entries():
    assert CognitionCore.extract_user_text([]) == ""
