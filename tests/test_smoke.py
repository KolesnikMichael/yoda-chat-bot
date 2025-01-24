import pytest
import asyncio
import datetime as dtm
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Chat
from telegram.ext import Application, ContextTypes

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from yoda.yoda_chat_bot import message_handler, ai_client, model, conversation_history

@pytest.fixture
def mock_update():
    user = User(id=123, first_name="Test", is_bot=False)
    chat = Chat(id=123, type="private")
    message = Message(message_id=1, from_user=user, chat=chat, text="Hello, Yoda!", date=dtm.datetime.now())
    update = Update(update_id=1, message=message)
    return update

@pytest.fixture
def mock_context():
    return MagicMock(spec=ContextTypes.DEFAULT_TYPE)

@pytest.mark.asyncio
async def test_message_handler(mock_update, mock_context):
    # Mock the AI client response
    ai_client.chat.complete_async = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Yoda says: Hello!"))]))

    # Call the message handler
    await message_handler(mock_update, mock_context)

    # Verify the response
    mock_context.bot.send_message.assert_called_once_with(
        chat_id=mock_update.message.chat_id,
        text="Yoda says: Hello!"
    )

    # Verify the conversation history
    assert conversation_history[123] == [
        {"role": "user", "content": "Reply as Yoda from Star Wars"},
        {"role": "user", "content": "Hello, Yoda!"},
        {"role": "assistant", "content": "Yoda says: Hello!"}
    ]

if __name__ == "__main__":
    pytest.main()