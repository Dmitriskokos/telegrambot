import logging
import sqlite3
import uuid
from aiogram import Dispatcher, types, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
from database import db_manager, get_user, get_referral_count, get_referral_purchases_amount, get_referral_purchases_count, get_all_users, get_user_balance, execute_query
from handlers import shared_context
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Функция для генерации реферального кода
def generate_referral_code():
    return str(uuid.uuid4())[:8].upper()

# Функция для генерации реферальной ссылки
def generate_referral_link(bot_username, referral_code):
    return f"http://t.me/{bot_username}?start={referral_code}"

# Функция для удаления сообщений с проверкой
async def delete_message(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        logging.info(f"Ignoring TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error deleting message: {e}")

async def job_handler(message: types.Message | types.CallbackQuery, bot: Bot, edit: bool = False):
    """Обработчик команды /referral (или нажатия кнопки 'Рефералка')."""
    if isinstance(message, types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        msg_id = message.message_id
    elif isinstance(message, types.CallbackQuery):
        user_id = message.from_user.id
        chat_id = message.message.chat.id
        msg_id = message.message.message_id
        message = message.message  # Получаем оригинальное сообщение
    else:
        logging.warning(f"job.py - job_handler: Unknown message type")
        return

    logging.info(f"job.py - job_handler: User {user_id} pressed 'Рефералка'")
    conn = db_manager.get_connection()
    if not conn:
       logging.error(f"job_handler: Не удалось получить соединение")
       return
    try:
      user_data = get_user(user_id)

      keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Назад / Back", callback_data="back_to_profile_from_ref")]
                 ]
           )

      if user_data is None:
          logging.warning(f"job.py - job_handler: User {user_id} - User not found in db.")
          if isinstance(message, types.CallbackQuery):
            await bot.edit_message_text("Произошла ошибка. Попробуйте перезапустить бота\n\nEnglish:\nAn error has occurred. Please try restarting the bot", chat_id=chat_id, message_id=msg_id, reply_markup=keyboard)
          elif isinstance(message, types.Message):
             await bot.delete_message(chat_id=chat_id, message_id=msg_id)
             await bot.send_message(chat_id=chat_id, text="Произошла ошибка. Попробуйте перезапустить бота\n\nEnglish:\nAn error has occurred. Please try restarting the bot", reply_markup=keyboard)
          return
      referral_code = user_data[1]
      logging.info(f"job.py - job_handler: User {user_id} - Existing referral code: {referral_code}")

      bot_username = (await bot.get_me()).username
      referral_link = generate_referral_link(bot_username, referral_code)
      logging.info(f"job.py - job_handler: User {user_id} - Referral link: {referral_link}")

      keyboard = InlineKeyboardBuilder()
      keyboard.button(text="Подробнее / Details", callback_data="referral_details")
      keyboard.row(InlineKeyboardButton(text="Назад / Back", callback_data="back_to_profile_from_ref"))

      text = (
          f"🇷🇺<b>Ваш реферальный код:</b> <code>{referral_code}</code>\n\n"
          f"<b>Реферальная ссылка:</b> <code>{referral_link}</code>\n\n"
          "Распространяйте вашу реферальную ссылку. Когда новый покупатель зарегистрируется с вашим кодом, если он сделает покупку, вы получите вознаграждение на баланс.\n\n"
          "<b>Реферальная программа:</b>\n"
          "Вы можете заработать приглашая новых покупателей в наш магазин.\n"
          "С каждой покупки приглашенного вами покупателя вам полагается награда в размере <b>3.0%</b> от суммы его покупки\n\n"
          "____________________________________________\n\n"
          f"🇺🇸<b>Your referral code:</b> <code>{referral_code}</code>\n\n"
          f"<b>Referral link:</b> <code>{referral_link}</code>\n\n"
          "Share your referral link. When a new buyer registers with your code, if they make a purchase, you will receive a reward to your balance.\n\n"
          "<b>Referral program:</b>\n"
          "You can earn by inviting new buyers to our store.\n"
          "For each purchase made by a buyer you invite, you will receive a reward of <b>3.0%</b> of the amount of their purchase\n"
      )

      image_path = os.path.join(os.path.dirname(__file__), "..", "data", "images", "ketamin.png")
      logging.info(f"job.py - job_handler: Referral image path - {image_path}")

      try:
          if os.path.exists(image_path):
              photo = FSInputFile(image_path)
              if isinstance(message, types.CallbackQuery) and edit:
                  sent_message = await bot.edit_message_media(media=types.InputMediaPhoto(media=photo, caption=text, parse_mode="HTML"), chat_id=chat_id, message_id=msg_id, reply_markup=keyboard.as_markup())
              elif isinstance(message, types.CallbackQuery) and not edit:
                  if user_id in shared_context.user_context and "referral_msg_ids" in shared_context.user_context[user_id]:
                      for mid in shared_context.user_context[user_id]["referral_msg_ids"]:
                          try:
                              await bot.delete_message(chat_id=chat_id, message_id=mid)
                          except Exception as e:
                              logging.error(f"job.py - job_handler: error deleting message {mid} : {e}")
                      shared_context.user_context.pop("referral_msg_ids", None)
                  sent_message = await bot.send_photo(photo=photo, caption=text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
              elif isinstance(message, types.Message):
                  await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                  sent_message = await bot.send_photo(photo=photo, caption=text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
          else:
              if isinstance(message, types.CallbackQuery) and edit:
                  sent_message = await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
              elif isinstance(message, types.CallbackQuery) and not edit:
                  if user_id in shared_context.user_context and "referral_msg_ids" in shared_context.user_context[user_id]:
                      for mid in shared_context.user_context[user_id]["referral_msg_ids"]:
                          try:
                              await bot.delete_message(chat_id=chat_id, message_id=mid)
                          except Exception as e:
                              logging.error(f"job.py - job_handler: error deleting message {mid} : {e}")
                      shared_context.user_context.pop("referral_msg_ids", None)
                  sent_message = await bot.send_message(text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
              elif isinstance(message, types.Message):
                  await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                  sent_message = await bot.send_message(text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")

          # Сохраняем message_id отправленного сообщения "Рефералка"
          if isinstance(message, types.CallbackQuery) and not edit or isinstance(message, types.Message):
              if user_id not in shared_context.user_context:
                  shared_context.user_context[user_id] = {}
              shared_context.user_context[user_id]["referral_main_msg_id"] = sent_message.message_id

      except Exception as e:
          logging.error(f"job.py - job_handler: Error sending referral info with image: {e}")
          if isinstance(message, types.CallbackQuery) and edit:
              await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
          elif isinstance(message, types.CallbackQuery) and not edit:
              if isinstance(message, types.CallbackQuery):
                  await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
              elif isinstance(message, types.Message):
                  await bot.send_message(text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")
          elif isinstance(message, types.Message):
              await bot.send_message(text, chat_id=chat_id, reply_markup=keyboard.as_markup(), parse_mode="HTML")

    except Exception as e:
         logging.error(f"job_handler: Ошибка - {e}")
    finally:
       db_manager.release_connection(conn)

async def referral_details_callback(callback_query: types.CallbackQuery, bot: Bot):
    """Обработчик нажатия на кнопку 'Подробнее'."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    msg_id = callback_query.message.message_id
    logging.info(f"job.py - referral_details_callback: User {user_id} pressed 'Подробнее'")
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"referral_details_callback: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        num_referrals = get_referral_count(user_id)
        referral_purchases = get_referral_purchases_count(user_id)
        total_purchases_amount = get_referral_purchases_amount(user_id)
        user_balance = get_user_balance(user_id)
        user_earnings = total_purchases_amount * 0.03 if total_purchases_amount else 0

        referral_logins = []

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT referral_id, username FROM referrals WHERE referrer_id=?", (user_id,))
            referrals = cursor.fetchall()
            for referral_id, username in referrals:
                if username:
                    referral_logins.append(f"@{username}")
                else:
                    referral_logins.append(f"ID: {referral_id}")

            logging.info(f"job.py - referral_details_callback: User {user_id} - Earnings: {user_earnings}")

        except sqlite3.Error as e:
            logging.error(f"database.py - get_referral_usernames: Ошибка при получении логинов рефералов: {e}")

        text = (
            "🇷🇺<b>Статистика рефералов:</b>\n\n"
            f"<b>Кол-во ваших рефералов:</b> {num_referrals}\n"
            f"<b>Покупки рефералов:</b> {referral_purchases}\n"
            f"<b>Сумма покупок рефералов:</b> {total_purchases_amount:.2f} USD\n"
            f"<b>Ваш заработок:</b> {user_earnings:.2f} USD\n\n"
        )
        if referral_logins:
            text += "<b>Ваши рефералы:</b>\n"
            for login in referral_logins:
                text += f"• {login}\n"
        else:
            text += "<b>Ваши рефералы:</b>\nНет рефералов."

        text += (
            "\n\n____________________________________________\n\n"
            "🇺🇸<b>Referral statistics:</b>\n\n"
            f"<b>Number of your referrals:</b> {num_referrals}\n"
            f"<b>Referral purchases:</b> {referral_purchases}\n"
            f"<b>Total amount of referral purchases:</b> {total_purchases_amount:.2f} USD\n"
            f"<b>Your earnings:</b> {user_earnings:.2f} USD\n\n"
        )

        if referral_logins:
            text += "<b>Your referrals:</b>\n"
            for login in referral_logins:
                text += f"• {login}\n"
        else:
            text += "<b>Your referrals:</b>\nNo referrals."

        image_path = os.path.join(os.path.dirname(__file__), "..", "data", "images", "ketamin.jpg")
        logging.info(f"job.py - referral_details_callback: Referral image path - {image_path}")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Назад / Back", callback_data="back_to_referral")]
            ]
        )

        try:
            if os.path.exists(image_path):
                photo = FSInputFile(image_path)
                await bot.send_photo(chat_id=chat_id, photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as e:
            logging.error(f"job.py - referral_details_callback: Error sending referral details with image: {e}")
            await callback_query.message.answer(text, parse_mode="HTML")

        await callback_query.answer()
    except Exception as e:
         logging.error(f"referral_details_callback: Ошибка - {e}")
    finally:
        if cursor:
           db_manager.release_connection(conn)

async def back_to_profile_handler(callback: types.CallbackQuery, bot: Bot):
    """Обработчик нажатия на кнопку "Назад", возвращает в меню профиля, удаляя сообщение"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    log_id = uuid.uuid4()
    logging.info(f"job.py - back_to_profile_handler: INFO: User {user_id} pressed 'Назад' from ref")

    if user_id in shared_context.user_context and "referral_main_msg_id" in shared_context.user_context[user_id]:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=shared_context.user_context[user_id]["referral_main_msg_id"])
        except Exception as e:
            logging.error(f"job.py - back_to_profile_handler: error deleting message : {e}")
        shared_context.user_context.pop("referral_main_msg_id", None)

    from handlers.profile import _send_profile_info
    await _send_profile_info(callback.message, bot, user_id)

    await callback.answer()

async def back_to_referral_handler(callback: types.CallbackQuery, bot: Bot):
    """Обработчик нажатия на кнопку "Назад", возвращает к рефералке удаляя сообщение с деталями"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    log_id = uuid.uuid4()
    logging.info(f"job.py - back_to_referral_handler: INFO: User {user_id} pressed 'Назад' from details")

    try:
        # Удаляем сообщение "Подробнее"
        await bot.delete_message(chat_id=chat_id, message_id=callback.message.message_id)
    except Exception as e:
        logging.error(f"job.py - back_to_referral_handler: error deleting message {callback.message.message_id} : {e}")

    # Получаем message_id основного сообщения "Рефералка"
    if user_id in shared_context.user_context and "referral_main_msg_id" in shared_context.user_context[user_id]:
        referral_main_msg_id = shared_context.user_context[user_id]["referral_main_msg_id"]
        # Вызываем job_handler для редактирования существующего сообщения
        # Создаем фиктивный объект message с нужными параметрами
        class FakeMessage:
            def __init__(self, chat_id, message_id):
                self.chat = types.Chat(id=chat_id, type="private")  # Добавлено поле type
                self.message_id = message_id

        fake_message = FakeMessage(chat_id, referral_main_msg_id)
        await job_handler(fake_message, bot, edit=True)
    else:
        # Если message_id не найден, отправляем новое сообщение (как запасной вариант)
        await job_handler(callback, bot)

    await callback.answer()

def register_job_handler(dp: Dispatcher):
    """Регистрирует обработчики в диспетчере."""
    dp.message.register(job_handler, F.text == "Рефералка / Ref")
    dp.callback_query.register(job_handler, lambda callback: callback.data == "referral_inline")
    dp.callback_query.register(referral_details_callback, F.data == "referral_details")
    dp.callback_query.register(back_to_profile_handler, lambda callback: callback.data == "back_to_profile_from_ref")
    dp.callback_query.register(back_to_referral_handler, lambda callback: callback.data == "back_to_referral")