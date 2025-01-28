import logging
import json
import os
import time
import base64
import asyncio
import speech_recognition as sr
from pydub import AudioSegment
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
AudioSegment.converter="ffmpeg"
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
    
    #text = context.chat_data.get("last_voice_text", "Нет сохраненного текста.")
    
    if user_id not in conversation_history:
        conversation_history[user_id] = [{"role": "user", "content": "Reply in Russian"}]

    conversation_history[user_id].append({"role": "user", "content": user_message})

    chat_response = await ai_client.chat.complete_async(
        model=mistral_model,
        messages=conversation_history[user_id],
    )

    chat_response = chat_response.choices[0].message.content

    conversation_history[user_id].append({"role": "assistant", "content": chat_response})


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

        await update.message.chat.send_chat_action("TYPING")
        await update.message.reply_text(text_response)

    # Удаляем временный файл
    os.remove(image_path)


async def handle_voice_message(update: Update, context) -> None:
    # Получаем файл голосового сообщения
    voice = await update.message.voice.get_file()
    file_path = "voice_message.ogg"
    wav_path = "voice_message.wav"

    # Скачиваем файл асинхронно
    file_path = await voice.download_to_drive(custom_path=file_path)

    # Конвертация OGG в WAV
    audio = AudioSegment.from_file(file_path, format="ogg")
    audio.export(wav_path, format="wav")

    # Распознавание речи
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")
            await update.message.reply_text(f"Распознанный текст: {text}")
    except sr.UnknownValueError:
        await update.message.reply_text("Не удалось распознать речь.")
    except sr.RequestError as e:
        await update.message.reply_text(f"Ошибка сервиса распознавания: {str(e)}")
    finally:
        # Сохранение текста для последующего использования
        #context.chat_data["last_voice_text"] = text
        # Удаляем временные файлы
        os.remove(file_path)
        os.remove(wav_path)
    user_id = update.message.from_user.id
    user_message = text
    
    #text = context.chat_data.get("last_voice_text", "Нет сохраненного текста.")
    
    if user_id not in conversation_history:
        conversation_history[user_id] = [{"role": "user", "content": "Reply in Russian"}]

    conversation_history[user_id].append({"role": "user", "content": user_message})

    chat_response = await ai_client.chat.complete_async(
        model=mistral_model,
        messages=conversation_history[user_id],
    )

    chat_response = chat_response.choices[0].message.content

    conversation_history[user_id].append({"role": "assistant", "content": chat_response})


    await update.message.chat.send_chat_action("TYPING")       
    await update.message.reply_text(chat_response)

if __name__ == '__main__':
    application = ApplicationBuilder().token(telegram_bot_api_key).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    application.run_polling(allowed_updates=Update.ALL_TYPES)