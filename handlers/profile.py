import logging
import os
import random
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from database import get_user_balance, get_user_sold_products, get_wallet_address
from handlers.shared_context import user_context
from handlers.topupbot import register_topup_handler

# Настройка логирования для отслеживания работы бота
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Функция для генерации случайных центов
def generate_random_cents():
    return random.randint(1, 99)

IMAGE_DIR = "data/images/"

async def _send_profile_info(message: types.Message, bot: Bot, user_id: int):
    """Отправляет сообщение с информацией о профиле."""
    log_id = uuid.uuid4()
    balance = get_user_balance(user_id)
    logging.info(f"{log_id} - profile.py - _send_profile_info: INFO: Пользователь {user_id} - Баланс: {balance} из БД")  # User {user_id} - Balance: {balance} from DB

    user_orders = get_user_sold_products(user_id)
    total_purchases_amount = 0.0

    for order in user_orders:
            total_purchases_amount += order.get("price", 0)

    num_orders = len(user_orders)
    average_check = total_purchases_amount / num_orders if num_orders > 0 else 0

    logging.info(f"{log_id} - profile.py - _send_profile_info: INFO: Пользователь {user_id} - Заказов: {num_orders}, Всего: {total_purchases_amount}, Средний чек: {average_check}")  # User {user_id} - Orders: {num_orders}, Total: {total_purchases_amount}, Average check: {average_check}

    user_group = "Начальный"

    text = (
        "🇷🇺<b>Личный кабинет</b>\n\n"
        f"Наш сервис: <a href='https://thaihub.cc'>https://thaihub.cc</a>\n"
        f"Ваш ID: <code>{user_id}</code>\n"
        f"Средства на счету: {balance:.2f} USD\n"
        f"Количество покупок: {num_orders}\n"
        f"Общая сумма покупок: {total_purchases_amount:.2f} USD\n"
        f"Средняя стоимость покупок: {average_check:.2f} USD\n"
        f"Уровень лояльности: {user_group}\n\n"
        "_______________________________\n\n"
        "🇺🇸<b>Personal account</b>\n\n"
        f"Our service: <a href='https://thaihub.cc'>https://thaihub.cc</a>\n"
        f"Your ID: <code>{user_id}</code>\n"
        f"Funds on account: {balance:.2f} USD\n"
        f"Number of purchases: {num_orders}\n"
        f"Total amount of purchases: {total_purchases_amount:.2f} USD\n"
        f"Average cost of purchases: {average_check:.2f} USD\n"
        f"Loyalty level: {user_group}"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(types.InlineKeyboardButton(text="Пополнить счет / Top up account", callback_data="request_funds"))
    keyboard.row(types.InlineKeyboardButton(text="Покупки / My Orders", callback_data="my_orders_inline"))
    keyboard.row(types.InlineKeyboardButton(text="Рефералка / Ref", callback_data="referral_inline"))

    image_path = os.path.join(IMAGE_DIR, "111.jpg")
    try:
       if os.path.exists(image_path):
           image = FSInputFile(image_path)
           await message.answer_photo(photo=image, caption=text, parse_mode="HTML", reply_markup=keyboard.as_markup(), disable_web_page_preview=True)
       else:
           await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup(), disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"{log_id} - profile.py - _send_profile_info: ERROR: Error sending image: {e}", exc_info=True)  # Error sending image: {e}
        await message.answer(f"Ошибка при отправке изображения: {e}\n\n{text}",parse_mode="HTML", reply_markup=keyboard.as_markup(), disable_web_page_preview=True)


# Обработчик команды "Личный кабинет", отображает информацию о пользователе
async def user_profile_handler(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - profile.py - user_profile_handler: INFO: Пользователь {user_id} запросил информацию о профиле") # User {user_id} requested profile information
    try:
        await _send_profile_info(message, bot, user_id)
    except Exception as e:
        logging.error(f"{log_id} - profile.py - user_profile_handler: ERROR:  {e}", exc_info=True)  # {e}


# Обработчик нажатия на кнопку "Пополнить счет", выводит меню выбора суммы пополнения
async def funds_request_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - profile.py - funds_request_handler: INFO: Пользователь {user_id} нажал 'Пополнить баланс'") # User {user_id} pressed 'Top up balance'

    # Удаляем сообщение с профилем
    await callback.message.delete()

    # Создание инлайн кнопок с суммами пополнения
    keyboard = InlineKeyboardBuilder()
    amounts = [100, 150, 200, 250, 300, 350, 400, 450]

    for i in range(0, len(amounts), 2):
        row_buttons = []
        row_buttons.append(types.InlineKeyboardButton(
            text=f"{amounts[i]} USDT",
            callback_data=f"select_amount_{i}"  # Используем индекс вместо ID
        ))
        if i + 1 < len(amounts):
            row_buttons.append(types.InlineKeyboardButton(
                text=f"{amounts[i+1]} USDT",
                callback_data=f"select_amount_{i+1}"  # Используем индекс вместо ID
            ))
        keyboard.row(*row_buttons)

    keyboard.row(types.InlineKeyboardButton(text="Отменить запрос / Cancel request", callback_data="cancel_funds"))

    # Формирование текста сообщения с информацией о пополнении баланса
    text = (
        f"<b>Пополнение баланса</b>\n\n"
        f"Выберите сумму пополнения (в USD) \n\n"
        f"<b>Крипто кошелек</b>\n\n"
        f"Это Ваш личный кошелек для пополнения баланса. При поступлении средств на этот адрес система автоматически пополнит Ваш счет.\n\n"
        f"Перед переводом, нажмите на сумму которую хотите пополнить (возможно пополнение только на указанные ниже суммы)\n\n"
        f"<b>Актуальный курс:</b>\n"
        f"1 USDT = 1 USD\n\n"
        "English:\n"
         f"<b>Top up balance</b>\n\n"
        f"Select the top-up amount (in USD)\n\n"
        f"<b>Crypto wallet</b>\n\n"
        f"This is your personal wallet for topping up your balance. When funds are received at this address, the system will automatically top up your account.\n\n"
        f"Before transferring, click on the amount you want to top up (it is possible to top up only the amounts below)\n\n"
        f"<b>Current rate:</b>\n"
        f"1 USDT = 1 USD"
    )

    await callback.message.answer(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")

    # Ответ на callback для предотвращения предупреждения от Telegram
    await callback.answer()

# Обработчик нажатия на кнопку "Отменить запрос", возвращает в меню профиля
async def cancel_funds_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - profile.py - cancel_funds_handler: INFO: User {user_id} нажал 'Отменить запрос'")  # User {user_id} pressed 'Cancel request'

    # Удаляем сообщение с меню пополнения
    await callback.message.delete()

    await _send_profile_info(callback.message, bot, user_id)

    await callback.answer()

# Обработчик нажатия на кнопку выбора суммы пополнения
async def select_amount_handler(callback: types.CallbackQuery, bot:Bot):
  user_id = callback.from_user.id
  log_id = uuid.uuid4()
  amount_index = int(callback.data.split("_")[-1])

  logging.info(f"{log_id} - profile.py - select_amount_handler: INFO: Пользователь {user_id} выбрал сумму пополнения, индекс: {amount_index}")  # User {user_id} selected the top-up amount, index: {amount_index}

  amounts = [100, 150, 200, 250, 300, 350, 400, 450]

  if amount_index < 0 or amount_index >= len(amounts):
        logging.warning(f"{log_id} - profile.py - select_amount_handler: WARNING: Пользователь {user_id} выбрал несуществующий индекс: {amount_index}")  # User {user_id} selected a non-existent index: {amount_index}
        await callback.answer("Ошибка: Неверная сумма пополнения. / Error: Invalid top-up amount.")
        return

  selected_amount = amounts[amount_index]

  # Получаем адрес кошелька USDT_TRC20 из базы данных
  tron_wallet_address = get_wallet_address("USDT_TRC20")

  if not tron_wallet_address:
    logging.error(f"{log_id} - profile.py - select_amount_handler: ERROR: USDT_TRC20 wallet address not found in database")  # USDT_TRC20 wallet address not found in database
    await callback.answer("Ошибка: Не удалось получить адрес кошелька для пополнения. / Error: Could not get the wallet address for top up.")
    return

  cents = generate_random_cents()
  total_amount = f"{selected_amount}.{cents:02}"

  # Сохраняем информацию о пополнении, включая адрес кошелька
  if user_id not in user_context:
        user_context[user_id] = {}
  user_context[user_id]["pending_topup"] = {
       "amount_with_cents": total_amount,
        "amount_without_cents": selected_amount,
        "wallet_address": tron_wallet_address
  }


  keyboard = InlineKeyboardBuilder()
  keyboard.row(
      types.InlineKeyboardButton(
          text="USDT TRC 20",
          callback_data=f"topup_confirm_{amount_index}"
      )
  )
  keyboard.row(types.InlineKeyboardButton(text="Отменить запрос / Cancel request", callback_data="cancel_funds"))

  text = "Выберите способ оплаты: \n\n Select payment method:"
  await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
  await callback.answer()

# Обработчик выбора способа оплаты USDT TRC20
async def process_topup_confirmation(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    amount_index = int(callback.data.split("_")[-1])

    amounts = [100, 150, 200, 250, 300, 350, 400, 450]

    if amount_index < 0 or amount_index >= len(amounts):
        logging.warning(f"{log_id} - profile.py - process_topup_confirmation: WARNING: Пользователь {user_id} выбрал несуществующий индекс: {amount_index}")  # User {user_id} selected a non-existent index: {amount_index}
        await callback.answer("Ошибка: Неверная сумма пополнения. / Error: Invalid top-up amount.")
        return

    selected_amount = amounts[amount_index]

    # Retrieve total_amount from user_context
    topup_info = user_context.get(user_id, {}).get("pending_topup", {})
    total_amount_str = topup_info.get("amount_with_cents")
    if not total_amount_str:
        logging.error(f"{log_id} - profile.py - process_topup_confirmation: ERROR: amount_with_cents not found in user_context for user {user_id}")
        await callback.answer("Ошибка: Сумма пополнения не найдена, попробуйте еще раз \n\n Error: Top up amount not found, please try again.", show_alert=True)
        return
    total_amount = total_amount_str # Use the retrieved total_amount

    logging.info(f"{log_id} - profile.py - process_topup_confirmation: INFO: Пользователь {user_id} выбрал USDT TRC20, сумма: {total_amount}")  # User {user_id} selected USDT TRC20, amount: {total_amount}

    # Извлекаем адрес кошелька из контекста пользователя
    tron_wallet_address = user_context.get(user_id, {}).get("pending_topup", {}).get("wallet_address")
    if not tron_wallet_address:
         logging.error(f"{log_id} - profile.py - process_topup_confirmation: ERROR: Wallet address not found in context for user {user_id}")  # Wallet address not found in context for user {user_id}
         await callback.answer("Ошибка: Не удалось получить адрес кошелька для пополнения. / Error: Could not get the wallet address for top up.")
         return

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        types.InlineKeyboardButton(
            text="Оплатил / Paid",
            callback_data="payment_made"
        )
    )
    keyboard.row(types.InlineKeyboardButton(text="Отменить запрос / Cancel request", callback_data="cancel_funds"))

    text = (
        f"😎 Вы выбрали USDT TRC 20\n\n"
        f"💵 Кошелек для оплаты: <code>{tron_wallet_address}</code>\n\n"
        f"✍️ Сумма к оплате: {total_amount} USDT\n\n"
        f"Пожалуйста, отправьте точно указанную сумму на указанный выше адрес.\n\n"
        "English:\n"
        f"😎 You have selected USDT TRC 20\n\n"
        f"💵 Wallet for payment: <code>{tron_wallet_address}</code>\n\n"
        f"✍️ Amount to pay: {total_amount} USDT\n\n"
        f"Please send the exact amount to the address indicated above."
    )

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode="HTML")
    await callback.answer()

async def back_to_profile_handler(callback: types.CallbackQuery, bot: Bot):
    """Обработчик нажатия на кнопку "Назад", возвращает в меню профиля, редактируя сообщение"""
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - profile.py - back_to_profile_handler: INFO: User {user_id} pressed 'Назад'") # User {user_id} pressed 'Back'

    await callback.message.delete() # удаляем сообщение перед тем как отправить профиль
    await _send_profile_info(callback.message, bot, user_id)

    await callback.answer()

# Регистрация всех обработчиков
def register_profile_handler(dp: Dispatcher, bot: Bot):
    dp.message.register(user_profile_handler, lambda message: message.text == "Профиль / Account")
    dp.callback_query.register(funds_request_handler, lambda callback: callback.data == "request_funds",)
    dp.callback_query.register(cancel_funds_handler, lambda callback: callback.data == "cancel_funds")
    dp.callback_query.register(select_amount_handler, lambda callback: callback.data.startswith("select_amount_"), )
    dp.callback_query.register(process_topup_confirmation, lambda callback: callback.data.startswith("topup_confirm_"))
    dp.callback_query.register(back_to_profile_handler, lambda callback: callback.data == "back_to_profile")
    register_topup_handler(dp, bot)