import asyncio
import aiohttp
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackContext, filters

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

# --- Асинхронный запрос к API ---
async def send_request_to_api_async(user_message, user_id):
    """
    Асинхронно отправляет HTTP POST-запрос к API с сообщением пользователя и его идентификатором.
    """
    api_url = "http://37.194.195.213:35411/v1/chat/completions"  # Замените на ваш API URL
    payload = {
        "model": "saiga",
        "messages": [
            {
                "role": "user",
                "content": user_message
            }
        ],
        "stream": False,
        "max_tokens": 200,
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
                if response.status == 200:
                    print(user_message)
                    print((await (response.json()))["choices"][0]["message"]["content"])
                    return (await (response.json()))["choices"][0]["message"]["content"] # Читаем JSON-ответ
                else:
                    print(f"Ошибка API: {response.status}")
                    return {"error": f"Ошибка API с кодом {response.status}"}
    except Exception as e:
        print(f"Ошибка при асинхронном запросе к API: {e}")
        return {"error": "Произошла ошибка при обращении к API."}

# --- Вспомогательные функции для работы с БД ---
def get_user_history(user_id):
    """
    Получает историю сообщений пользователя из базы данных.
    """
    user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
    if user:
        return user.history
    return "Первое сообщение бота: Привет! Чем могу помочь?"

def update_user_history(user_id, new_message):
    """
    Обновляет историю сообщений пользователя в базе данных.
    """
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
    Обработчик сообщений от пользователя.
    """
    user_id = update.effective_user.id
    user_message = update.message.text

    # Получаем историю пользователя
    history = get_user_history(user_id)

    # Добавляем сообщение пользователя в историю
    history += f"\nПользователь: {user_message}"
    update_user_history(user_id, f"Пользователь: {user_message}")

    # Отправляем историю в API
    api_response = await send_request_to_api_async(history, user_id)

    # Потоковая обработка ответа
    if "error" in api_response:
        bot_response = api_response["error"]
    else:
        bot_response = api_response

    # Сохраняем ответ бота в историю
    update_user_history(user_id, f"Бот: {bot_response[:20]}...")  # Добавляем заголовок для истории

    # Отправляем сообщение и редактируем его с интервалом
    sent_message = await update.message.reply_text("Начинаю ответ...")
    otvet = ""
    for chunk in stream_response(bot_response):
        otvet = otvet + chunk
        await asyncio.sleep(2)  # Задержка для эмуляции потока
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, 
                                            message_id=sent_message.message_id, 
                                            text=otvet)

def stream_response(full_response):
    """
    Разделяет полный ответ на части для отправки по частям.
    """
    words = full_response.split()
    chunk = ""
    for word in words:
        chunk += word + " "
        if len(chunk) > 20:  # Разделяем на части по 20 символов (пример)
            yield chunk
            chunk = ""
    if chunk:
        yield chunk

async def start(update: Update, context: CallbackContext):
    """
    Приветственное сообщение для команды /start.
    """
    await update.message.reply_text("Привет, я помощник и т.д. и т.п.")

# --- Запуск приложения ---
if __name__ == "__main__":
    # Создание бота и регистрация обработчиков
    application = ApplicationBuilder().token("7583980596:AAELwT6OEXJwHCjPQFqNTwJ4X2RpvMrbAM4").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    application.run_polling()
