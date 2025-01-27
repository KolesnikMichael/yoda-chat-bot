import logging
import json
import os
import time
import base64
import asyncio
from telegram import ForceReply, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext
from mistralai import Mistral
from mistralai.models import UserMessage


with open('settings.json', 'r') as f:
    settings = json.load(f)
    
telegram_bot_api_key = settings["telegram_token"]
mistral_apikey = settings["mistral_token"]
mistral_model = settings["mistral_model"]
mistral_image_model = settings["mistral_image_model"]
ai_client = Mistral(api_key=mistral_apikey)
conversation_history = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Привет! Я бот, который может отвечать на ваши сообщения с помощью Mistral AI.")
    
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_message = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = [{"role": "user", "content": "Reply in Russian"}]

    conversation_history[user_id].append({"role": "user", "content": user_message})

    chat_response = await ai_client.chat.complete_async(
        model=mistral_model,
        messages=conversation_history[user_id],
    )

    chat_response = chat_response.choices[0].message.content

    conversation_history[user_id].append({"role": "assistant", "content": chat_response})

    for _ in range(3):
        time.sleep(1)
        await update.message.chat.send_chat_action("TYPING")       
    await update.message.reply_text(chat_response)

async def handle_photo(update: Update, context: CallbackContext) -> None:
    # Получаем последнее изображение
    photo = update.message.photo[-1]
    # Загружаем объект File
    file = await photo.get_file() 
    # Путь для сохранения изображения
    image_path = "image.jpg"

    # Сохраняем файл локально
    await file.download_to_drive(image_path)

    # Кодирование изображения в base64
    def encode_image(image_path):
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except FileNotFoundError:
            print(f"Error: The file {image_path} was not found.")
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    base64_image = encode_image(image_path)
    caption = update.message.caption or "Что изображено на картинке?"
    # Формируем запрос к Mistral AI
    if base64_image:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{caption}"
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base64_image}" 
                    }
                ]
            }
        ]

        # Запрашиваем у Mistral AI описание изображения
        chat_response = ai_client.chat.complete(
            model=mistral_image_model,
            messages=messages
        )

        # Извлекаем текст из ответа Mistral AI
        if hasattr(chat_response, "choices") and len(chat_response.choices) > 0:
            text_response = chat_response.choices[0].message.content
        else:
            text_response = "Не удалось получить описание изображения."

        # Имитация печати текста
        for _ in range(3):
            await asyncio.sleep(1)
            await update.message.chat.send_chat_action("TYPING")

        await update.message.reply_text(text_response)

    # Удаляем временный файл
    os.remove(image_path)


if __name__ == '__main__':
    application = ApplicationBuilder().token(telegram_bot_api_key).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling(allowed_updates=Update.ALL_TYPES)