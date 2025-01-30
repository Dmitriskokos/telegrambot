import logging
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InputMediaVideo, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from database import DatabaseManager, add_user, get_user, update_referred_by, delete_user, get_all_users, update_username_query, add_referral
import os
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from logging import StreamHandler
from dotenv import load_dotenv
from keyboards import main_menu_keyboard  # Импорт клавиатуры

load_dotenv()

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Создаем StreamHandler
stream_handler = StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))  # форматируем вывод
# Добавляем handler к root logger
logging.getLogger().addHandler(stream_handler)

# Создаем экземпляр DatabaseManager
db_manager = DatabaseManager()

# Функция для удаления сообщений с проверкой
async def delete_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        logging.info(f"Ignoring TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error deleting message: {e}")


# Токен вашего бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("BOT_TOKEN не найден в переменных окружения")
    exit()

# Путь к GIF
GIF_PATH = os.getenv("GIF_PATH", "data/images/ааа.mp4")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Функция для генерации реферального кода
def generate_referral_code():
    return str(uuid.uuid4())[:8].upper()


# Функция для генерации реферальной ссылки
def generate_referral_link(bot_username, referral_code):
    return f"http://t.me/{bot_username}?start={referral_code}"


async def start_command(message: Message):
    logging.info(f"main.py - start_command: Обработчик /start вызван для пользователя {message.from_user.id}")
    user_id = message.from_user.id
    username = message.from_user.username
    logging.info(f"main.py - start_command: User {user_id} started bot with text: {message.text}")

    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"start_command: Не удалось получить соединение")
        return
    try:
        user_data = get_user(user_id)
        if user_data is None:
            referral_code = generate_referral_code()
            add_user(user_id, referral_code, username=username)
            from handlers import shared_context
            shared_context.user_context[user_id] = {}
            logging.info(f"main.py - start_command: User {user_id} - New user. Added to database. Referal code {referral_code}")
        else:
            if username and user_data[5] != username:
                update_username_query(user_id, username)
                logging.info(f"main.py - start_command: User {user_id} - Updating username to {username}")
            from handlers import shared_context
            shared_context.user_context[user_id] = {}
            logging.info(f"main.py - start_command: User {user_id} - Existing user.")

        if message.text and message.text.startswith("/start "):
            try:
                referral_code = message.text.split(" ")[1]
                logging.info(f"main.py - start_command: User {user_id} - Referral code: {referral_code}")

                all_users = get_all_users()
                for ref_user_id, ref_user_code in all_users:
                    if ref_user_code == referral_code:
                        # Проверяем, является ли пользователь уже чьим-то рефералом
                        if user_data and user_data[2] is not None:
                            logging.info(f"main.py - start_command: User {user_id} already has a referrer.")
                            break  # Если уже есть реферер, пропускаем добавление
                        
                        # Добавляем реферальную связь если нет его в бд
                        if user_data is None:
                            update_referred_by(user_id, ref_user_id)
                            add_referral(ref_user_id, user_id, username)
                            
                            referrer_data = get_user(ref_user_id)
                            if referrer_data:
                                logging.info(f"main.py - start_command: User {user_id} referred by {ref_user_id}.  Referrer balance {referrer_data[3]}")
                                await bot.send_message(chat_id=ref_user_id,text="По вашей ссылке зареган новый пользователь! Вы будете получать 3% от суммы его покупок на баланс бота")
                            else:
                                logging.warning(f"main.py - start_command: User {user_id} referred by {ref_user_id} but referrer not found")

                        break  # выходим из цикла после нахождения реферера
            except IndexError:
                logging.warning(f"main.py - start_command: User {user_id} - no referral code found")
    except Exception as e:
         logging.error(f"start_command: Ошибка - {e}")
    finally:
       db_manager.release_connection(conn)
    logging.info(f"main.py - start_command: DEBUG: GIF path - {GIF_PATH}")


    welcome_message = (
    "🇷🇺<b>Добро пожаловать в магазин THAI.HUB</b>🖤🧡\n\n"
    "Будем рады предоставить Вам лучшее качество и сервис!\n"
    "Мы ценим каждого клиента.\n\n"
    "Бот автопродаж работает 24/7.\n"
    "Здесь Вы можете совершать покупки, зарабатывать на реферальной программе, и коммуницировать с поддержкой по всем вопросам.\n"
    "Наслаждайтесь💕🇹🇭\n"
    "_______________________________\n\n"
    "🇺🇸<b>Welcome to THAI.HUB store</b>🖤🧡\n\n"
    "We will be happy to provide you with the best quality and service!\n"
    "We value each and every customer.\n\n"
    "The automated sales bot operates 24/7.\n"
    "Here you can make purchases, earn on the referral program, and communicate with support on all issues.\n"
    "Enjoy💕🇹🇭"
)

    try:
        if os.path.exists(GIF_PATH):
            gif = FSInputFile(GIF_PATH)
            await message.answer_animation(animation=gif, caption=welcome_message, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)
        else:
            await message.answer(welcome_message, reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)
            logging.warning(f"main.py - start_command: GIF not found at path: {GIF_PATH}")
    except Exception as e:
        await message.answer(f"Ошибка при отправке GIF: {e}\n\n{welcome_message}", reply_markup=main_menu_keyboard(), parse_mode=ParseMode.HTML)
        logging.error(f"main.py - start_command: Error sending GIF: {e}")


async def cities_from_main_menu_handler(message: Message, bot: Bot, state: FSMContext):
    user_id = message.from_user.id
    logging.info(f"main.py - cities_from_main_menu_handler: User {user_id} pressed 'Сделать заказ'")
    from handlers import shared_context
    if user_id not in shared_context.user_context:
        shared_context.user_context[user_id] = {}
    shared_context.user_context[user_id]["step"] = "cities_list"
    from handlers.cities import cities_handler
    await cities_handler(message, bot, state)

async def our_chat_handler(message: Message, bot: Bot):
    chat_link = "https://t.me/thaihub_chat"
    logging.info(f"main.py - our_chat_handler: User {message.from_user.id} pressed 'Наш чат / Our Chat'")
    
    # Добавляем текст на русском и английском
    message_text = (
        "Нажмите на кнопку ниже, чтобы перейти в чат:\n\n"
        "Click the button below to join our chat:"
    )
    
    # Добавляем текст на русском и английском в кнопку
    button_text = "Перейти в чат / Join our Chat"
    
    inline_keyboard = InlineKeyboardMarkup(
         inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=chat_link)]
         ]
    )
    await message.answer(message_text, reply_markup=inline_keyboard)


async def delete_user_handler(message: Message):
    conn = db_manager.get_connection()
    if not conn:
      logging.error(f"delete_user_handler: Не удалось получить соединение")
      return
    try:
      if message.text.startswith("/delete_user "):
        try:
           user_id_to_delete = int(message.text.split(" ")[1])
           delete_user(user_id_to_delete)
           logging.info(f"main.py - delete_user_handler: User {user_id_to_delete} deleted from db by {message.from_user.id}")
           await message.answer(f"Пользователь с ID {user_id_to_delete} удален.")
        except (IndexError, ValueError) as e:
            logging.warning(f"main.py - delete_user_handler: Invalid user_id or command: {e}")
            await message.answer("Неверный формат команды. Используйте /delete_user <user_id>.")
      else:
            logging.warning(f"main.py - delete_user_handler: Invalid command format")
            await message.answer("Неверный формат команды. Используйте /delete_user <user_id>.")
    except Exception as e:
         logging.error(f"delete_user_handler: Ошибка - {e}")
    finally:
      db_manager.release_connection(conn)


# Импорт обработчиков
from handlers.balance import register_balance_handler
from handlers.cities import register_city_handlers
from handlers.categories import register_category_handlers
from handlers.earn import register_earn_handler
from handlers.payment_handler import register_payment_handler
from handlers.profile import register_profile_handler
from handlers.reviews import register_reviews_handler
from handlers.support import register_support_handler
from handlers.job import register_job_handler
from handlers.topupbot import register_topup_handler


# Регистрация всех обработчиков
def register_handlers():
    dp.message.register(start_command, F.text.startswith("/start"))
    dp.message.register(delete_user_handler, F.text.startswith("/delete_user"))
    register_balance_handler(dp, bot)
    register_city_handlers(dp, bot)
    register_earn_handler(dp)
    register_payment_handler(dp)
    register_profile_handler(dp, bot)
    register_reviews_handler(dp)
    register_support_handler(dp, bot)
    register_job_handler(dp)
    register_category_handlers(dp, bot)
    register_topup_handler(dp, bot)
    dp.message.register(cities_from_main_menu_handler, F.text == "Заказать / Order")
    dp.message.register(our_chat_handler, F.text == "Наш чат / Our Chat")


async def main():
    # Инициализация базы данных до запуска бота
    # database.initialize_db() # <--- УДАЛЯЕМ
    register_handlers()
    logging.info("Бот запущен и готов к работе.")

    try:
        await dp.start_polling(bot)
    finally:
        # Гарантированное закрытие соединения с БД при остановке бота
        # database.close_db() # <--- УДАЛЯЕМ
       pass


if __name__ == "__main__":
    asyncio.run(main())