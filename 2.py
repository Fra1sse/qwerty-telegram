
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
    api_url = "http://37.194.195.213:35420/query"
    payload = {
        
        "messages": [
            { "role": 'user', "content": user_message }
          ],
          "max_tokens" : 300,
        
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
                            json_str = decoded_line[6:]
                            if json_str == '[DONE]':
                                break
                            #chunk = json.loads(json_str)
                            #delta = chunk['choices'][0]['delta'].get('content', '')
                            print(json_str)
                            if json_str:
                                yield json_str
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



async def start(update: Update, context: CallbackContext):
    """
    Приветственное сообщение для команды /start с кнопками выбора языка.
    """
    keyboard = [
        ['Русский \U0001F1F7\U0001F1FA',
        'English \U0001F1EC\U0001F1E7'],
        ['中文 \U0001F1E8\U0001F1F3']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Выберите язык / Choose language / 请选择语言:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: CallbackContext):
    """
    Обработчик сообщений от пользователя с потоковой передачей ответа.
    """
    user_id = update.effective_user.id
    user_message = update.message.text

    # Обработка выбора языка
    if user_message in ['Русский \U0001F1F7\U0001F1FA', 'English \U0001F1EC\U0001F1E7', '中文 \U0001F1E8\U0001F1F3']:
        if user_message == 'Русский \U0001F1F7\U0001F1FA':
            response = "Вы выбрали русский язык \U0001F1F7\U0001F1FA. Как я могу вам помочь?"
        elif user_message == 'English 🇬🇧':
            response = "You have selected English \U0001F1EC\U0001F1E7. How can I help you?"
        else:
            response = "您选择了中文 \U0001F1E8\U0001F1F3。我能为您做什么？"
        await update.message.reply_text(response, reply_markup=ReplyKeyboardRemove())
        return

    # Остальной код обработки сообщений
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


# --- Запуск приложения ---
if __name__ == "__main__":
    # Создание бота и регистрация обработчиков
    application = ApplicationBuilder().token("7583980596:AAELwT6OEXJwHCjPQFqNTwJ4X2RpvMrbAM4").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    application.run_polling()
