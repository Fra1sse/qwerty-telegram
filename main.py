
import asyncio
import aiohttp
import json
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters
from telegram.error import BadRequest, RetryAfter

# --- Настройка базы данных ---
Base = declarative_base()

class UserHistory(Base):
    __tablename__ = "user_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    history = Column(Text, nullable=False)

# Создание SQLite базы данных
engine = create_engine("sqlite:///chatbot.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db_session = Session()

# --- Асинхронный стриминговый запрос к API ---
async def stream_request_to_api(user_message, user_id):
    """
    Асинхронно отправляет стриминговый HTTP POST-запрос к API с сообщением пользователя.
    """
    api_url = "http://37.194.195.213:35411/v1/chat/completions"
    payload = {
        "model": "saiga",
        "messages": [
            {
                "role": "user",
                "content": user_message
            }
        ],
        "stream": True,
        "max_tokens": 500,
        "temperature": 0.3,
        "top_p": 1,
        "typical_p": 1,
        "typical": 1,
        "min_p": 0.07,
        "repetition_penalty": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "top_k": 0,
        "skew": 0,
        "min_length": 0,
        "min_tokens": 0,
        "num_beams": 1,
        "length_penalty": 1,
        "early_stopping": False,
        "add_bos_token": True,
        "smoothing_factor": 0,
        "smoothing_curve": 1,
        "dry_allowed_length": 2,
        "dry_multiplier": 0,
        "dry_base": 1.75,
        "dry_sequence_breakers": ["\n", ":", "\"", "*"],
        "dry_penalty_last_n": 0,
        "top_a": 0,
        "tfs": 1,
        "epsilon_cutoff": 0,
        "eta_cutoff": 0,
        "mirostat_mode": 0,
        "mirostat_tau": 5,
        "mirostat_eta": 0.1,
        "xtc_threshold": 0.1,
        "xtc_probability": 0,
        "rep_pen": 1,
        "rep_pen_range": 0,
        "repetition_penalty_range": 0,
        "encoder_repetition_penalty": 1,
        "no_repeat_ngram_size": 0,
        "num_predict": 500,
        "num_ctx": 4096
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                if response.status != 200:
                    yield f"Ошибка API: {response.status}"
                    return

                async for line in response.content:
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line.startswith('data: '):
                        try:
                            json_str = decoded_line[6:].strip()
                            if json_str == '[DONE]':
                                break
                            print(json_str)
                            chunk = json.loads(json_str)
                            delta = chunk['choices'][0]['delta'].get('content', '')
                            print(delta)
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError) as e:
                            print(f"Ошибка парсинга: {e}")

    except Exception as e:
        print(f"Ошибка при стриминговом запросе к API: {e}")
        yield f"Произошла ошибка: {str(e)}"

# --- Вспомогательные функции для работы с БД ---
def get_user_history(user_id):
    user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
    if user:
        return user.history
    return "Первое сообщение бота: Привет! Чем могу помочь?"

def update_user_history(user_id, new_message):
    user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
    if user:
        user.history += f"\n{new_message}"
    else:
        user = UserHistory(user_id=user_id, history=new_message)
        db_session.add(user)
    db_session.commit()

# --- Обработчики Telegram-бота ---
async def handle_message(update: Update, context: CallbackContext):
    """
    Обработчик сообщений от пользователя с потоковой передачей ответа.
    """
    user_id = update.effective_user.id
    user_message = update.message.text

    # Получаем историю пользователя
    history = get_user_history(user_id)
    history += f"\nПользователь: {user_message}"
    update_user_history(user_id, f"Пользователь: {user_message}")

    # Отправляем сообщение о начале ответа
    sent_message = await update.message.reply_text("Начинаю ответ...")

    # Стриминговый ответ с периодическим обновлением
    full_response = ""
    displayed_response = ""
    last_update_time = asyncio.get_event_loop().time()


    async def periodic_update():
        nonlocal full_response, displayed_response, last_update_time
        try:
            # Используем только новую часть ответа
            new_part = full_response[len(displayed_response):]
            if new_part:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id, 
                    message_id=sent_message.message_id, 
                    text=full_response
                )
                displayed_response = full_response
                last_update_time = asyncio.get_event_loop().time()
        except RetryAfter as e:
            print(f"Flood control: waiting {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                print(f"Error updating message: {e}")

    try:
        async for chunk in stream_request_to_api(history, user_id):
            full_response += chunk

            # Проверяем время с последнего обновления
            current_time = asyncio.get_event_loop().time()
            if current_time - last_update_time >= 1.5:
                await periodic_update()

            # Небольшая задержка для предотвращения перегрузки
            await asyncio.sleep(0.1)

        # Финальное обновление
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, 
            message_id=sent_message.message_id, 
            text=full_response
        )

    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, 
            message_id=sent_message.message_id, 
            text=f"Ошибка: {str(e)}"
        )

    # Сохраняем ответ бота в историю
    update_user_history(user_id, f"Бот: {full_response[:20]}...")

async def start(update: Update, context: CallbackContext):
    """
    Приветственное сообщение для команды /start.
    """
    
    await update.message.reply_text("Привет, я ваш персональный помощник!")


# --- Запуск приложения ---
if __name__ == "__main__":
    # Создание бота и регистрация обработчиков
    application = ApplicationBuilder().token("7583980596:AAELwT6OEXJwHCjPQFqNTwJ4X2RpvMrbAM4").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    application.run_polling()
