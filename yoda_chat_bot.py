import time
import json
import logging
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from mistralai import Mistral
from mistralai.models import UserMessage

# Read bot settings from a JSON file
with open('settings.json', 'r') as f:
    settings = json.load(f)

bot_token = settings["telegram"]["bot_token"]
api_key = settings["mistral"]["api_key"]
model = settings["mistral"]["model"]
ai_client = Mistral(api_key=api_key)
conversation_history = {}

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    for _ in range(3):
        time.sleep(1)
        await update.message.chat.send_chat_action("TYPING")        
    await update.message.reply_text(update.message.text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_message = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = [{"role": "user", "content": "Reply as Yoda from Star Wars"}]

    conversation_history[user_id].append({"role": "user", "content": user_message})

    chat_response = await ai_client.chat.complete_async(
        model=model,
        messages=conversation_history[user_id],
    )

    chat_response = chat_response.choices[0].message.content

    conversation_history[user_id].append({"role": "assistant", "content": chat_response})

    for _ in range(3):
        time.sleep(1)
        await update.message.chat.send_chat_action("TYPING")       
    await update.message.reply_text(chat_response)

def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(bot_token).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()