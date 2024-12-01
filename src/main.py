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

def get_user_history(user_id):
    user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
    if user:
        # Разбиваем историю на отдельные сообщения
        messages = []
        if user.history:
            for line in user.history.split('\n'):
                if line.startswith('Пользователь: '):
                    messages.append({
                        "role": "user",
                        "content": line.replace('Пользователь: ', '')
                    })
                elif line.startswith('Бот: '):
                    messages.append({
                        "role": "assistant",
                        "content": line.replace('Бот: ', '')
                    })
        return messages
    return []

def update_user_history(user_id, new_message):
    user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
    if user:
        user.history += f"\n{new_message}"
    else:
        user = UserHistory(user_id=user_id, history=new_message)
        db_session.add(user)
    db_session.commit()

def clear_user_history(user_id):
    """Очищает историю сообщений пользователя"""
    try:
        user = db_session.query(UserHistory).filter(UserHistory.user_id == user_id).first()
        if user:
            db_session.delete(user)
            db_session.commit()
        return True
    except Exception as e:
        print(f"Ошибка при очистке истории: {e}")
        return False



async def stream_request_to_api(history, user_message, user_id):
    """
    Асинхронно отправляет стриминговый HTTP POST-запрос к API с историей сообщений.
    """
    api_url = "http://37.194.195.213:35420/query"
    
    # Получаем предыдущую историю
    messages = history
    
    # Добавляем текущее сообщение пользователя
    messages.append({
        "role": "user",
        "content": user_message
    })
    
    payload = {
        "messages": messages,
        "max_tokens": 300,
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
                            if json_str:
                                yield json_str
                        except (json.JSONDecodeError, KeyError) as e:
                            print(f"Ошибка парсинга: {e}")

    except Exception as e:
        print(f"Ошибка при стриминговом запросе к API: {e}")
        yield f"Произошла ошибка: {str(e)}"


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

async def clear_history(update: Update, context: CallbackContext):
    """Обработчик команды /clear для очистки истории диалога"""
    user_id = update.effective_user.id
    if clear_user_history(user_id):
        await update.message.reply_text("История диалога успешно очищена! ✨")
    else:
        await update.message.reply_text("Произошла ошибка при очистке истории.")

async def handle_message(update: Update, context: CallbackContext):
    """
    Обработчик сообщений от пользователя с потоковой передачей ответа.
    """
    user_id = update.effective_user.id
    user_message = update.message.text

    # Обработка выбора языка
    if user_message in ['Русский \U0001F1F7\U0001F1FA', 'English \U0001F1EC\U0001F1E7', '中文 \U0001F1E8\U0001F1F3']:
        if user_message == 'Русский \U0001F1F7\U0001F1FA':
            response = (
    "Привет! 👋 Я – твой помощник 'Мой Санкт-Петербург'!\n\n"
    "Я здесь, чтобы сделать твою жизнь проще и комфортнее. Вот что я умею:\n"
    "🌦 **Погода** – расскажу, нужно ли брать зонт или готовиться к солнечному дню.\n"
    "📍 **Улицы города** – помогу с информацией об улицах, маршрутах и названиях.\n"
    "📞 **Контакты** – найду номер нужного специалиста: врача, сантехника, электрика или другого.\n\n"
    "Просто задай мне вопрос, и я постараюсь помочь! 🚀\n"
    "Например, спроси:\n"
    "- 'Какая погода в Петербурге сегодня?'\n"
    "- 'Где находится улица Рубинштейна?'\n"
    "- 'Нужен номер телефона стоматолога.'\n\n"
    "Давай начнём! Чем могу помочь? 😊"
)
        elif user_message == 'English \U0001F1EC\U0001F1E7':
            response = (
    "Hello! 👋 I’m your assistant 'My Saint Petersburg'!\n\n"
    "I’m here to make your life easier and more convenient. Here's what I can do:\n"
    "🌦 **Weather** – I'll let you know if you need an umbrella or if it's a sunny day ahead.\n"
    "📍 **City Streets** – I can provide information about streets, routes, and locations.\n"
    "📞 **Contacts** – I can find the number of specialists: a doctor, a plumber, an electrician, or others.\n\n"
    "Just ask me a question, and I'll do my best to assist! 🚀\n"
    "For example, you can ask:\n"
    "- 'What's the weather like in Saint Petersburg today?'\n"
    "- 'Where is Rubinstein Street located?'\n"
    "- 'I need a dentist's phone number.'\n\n"
    "Let's get started! How can I help you? 😊"
)
        else:
            response = (
    "你好！👋 我是你的助手“我的圣彼得堡”！\n\n"
    "我在这里让你的生活更轻松、更方便。以下是我能为你做的事情：\n"
    "🌦 **天气** – 我会告诉你是否需要带伞，还是准备享受晴天。\n"
    "📍 **城市街道** – 我可以提供关于街道、路线和位置的信息。\n"
    "📞 **联系方式** – 我可以帮你找到所需专业人士的电话号码，例如医生、水管工、电工等。\n\n"
    "只需向我提问，我会尽力为你提供帮助！🚀\n"
    "例如，你可以问：\n"
    "- '今天圣彼得堡的天气怎么样？'\n"
    "- '鲁宾斯坦街在哪里？'\n"
    "- '我需要一位牙医的电话号码。'\n\n"
    "让我们开始吧！我能为你做什么？😊"
)
        await update.message.reply_text(response, reply_markup=ReplyKeyboardRemove())
        return

    # Получаем историю сообщений
    history = get_user_history(user_id)
    
    # Сохраняем новое сообщение пользователя
    update_user_history(user_id, f"Пользователь: {user_message}")

    # Отправляем сообщение о начале ответа
    sent_message = await update.message.reply_text("...")

    # Стриминговый ответ с периодическим обновлением
    full_response = ""
    displayed_response = ""
    last_update_time = asyncio.get_event_loop().time()

    async def periodic_update():
        nonlocal full_response, displayed_response, last_update_time
        try:
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
        async for chunk in stream_request_to_api(history, user_message, user_id):
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

        # Сохраняем ответ бота в историю
        update_user_history(user_id, f"Бот: {full_response}")

    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, 
            message_id=sent_message.message_id, 
            text=f"Ошибка: {str(e)}"
        )

# --- Запуск приложения ---
if __name__ == "__main__":
    # Создание бота и регистрация обработчиков
    application = ApplicationBuilder().token("7583980596:AAELwT6OEXJwHCjPQFqNTwJ4X2RpvMrbAM4").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен.")
    application.run_polling()