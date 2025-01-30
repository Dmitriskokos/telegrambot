import logging
import uuid
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.exceptions import TelegramBadRequest

# Функция, которая добавляет токен к строке BOT_TOKEN=... в .env
# (подставьте свою версию, если храните по-другому)
from main import append_token_to_bot_line  # или append_token_to_env


async def connect_bot_handler(message: types.Message):
    """
    Обработчик команды /bot <token>.
    1) Проверяем формат,
    2) Проверяем токен на валидность (get_me()),
    3) Добавляем в .env,
    4) Высылаем ссылку на личного бота пользователю.
    """
    user_id = message.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - connect_bot_handler: User {user_id} message: {message.text}")

    # Разбираем команду
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "/bot <токен>\n\n"
            "Пример:\n"
            "/bot 1234567890:ABCDefgh_iJKLmnopQRS"
        )
        return

    bot_token = parts[1].strip()
    if ":" not in bot_token:
        await message.answer(
            "Неверный формат токена. Пример:\n"
            "/bot 1234567890:ABCDefgh_iJKLmnopQRS"
        )
        return

    # Проверяем, что этот токен валиден (получаем username)
    try:
        personal_bot = Bot(token=bot_token)
        bot_info = await personal_bot.get_me()
    except TelegramBadRequest as e:
        logging.warning(f"connect_bot_handler: Invalid token from {user_id}, {e}")
        await message.answer("Похоже, этот токен недействителен. Проверьте токен и повторите попытку.")
        return
    except Exception as e:
        logging.error(f"connect_bot_handler: Unexpected error {e}")
        await message.answer("Произошла ошибка при проверке токена. Повторите попытку позже.")
        return

    if not bot_info or not bot_info.username:
        await message.answer(
            "Невозможно получить username вашего бота. Убедитесь, что токен корректен."
        )
        return

    # Запоминаем username личного бота
    personal_bot_username = bot_info.username
    personal_bot_link = f"https://t.me/{personal_bot_username}"

    # Сохраняем токен в .env (вместе с user_id, разделяем запятыми и т.д.)
    # Если у вас другая логика хранения – замените вызов.
    append_token_to_bot_line(user_id, bot_token)

    # Уведомляем пользователя
    text = (
        f"✅ Ваш личный бот <b>{personal_bot_username}</b> успешно подключён!\n\n"
        f"Ссылка: {personal_bot_link}\n\n"
        "Теперь вы можете использовать этого бота так же, как основного.\n"
        "Все данные будут общие, если вы не подняли отдельный экземпляр."
    )
    await message.answer(text, parse_mode="HTML")


def register_connect_bot_handler(dp: Dispatcher):
    """
    Регистрируем обработчик команды /bot <token>.
    """
    dp.message.register(connect_bot_handler, F.text.startswith("/bot "))
