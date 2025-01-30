import asyncio
from datetime import datetime, timedelta
import os
from aiogram import Dispatcher, Bot, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
import logging
import handlers.shared_context
import random
from decimal import Decimal
import uuid
from handlers.payment_check import check_payment
from handlers.payment_check import start_payment_check as start_usdt_trc20_payment_check
from handlers.btc_checker import start_btc_payment_check
from handlers.usdt_bep20_checker import start_payment_check as start_usdt_bep20_payment_check
from handlers.eth_checker import start_payment_check as start_payment_check_eth

from database import (
    add_to_user_balance,
    get_user_balance,
    set_user_balance,
    get_user,
    update_referral_purchases_amount,
    get_wallet_address,
    add_order,
    move_paid_product_to_sold_products,
    get_product_category,
    get_product_price,
    get_paid_product_by_location,
    update_referral_purchases_count_column,
    get_location_info_from_paid_products
)
from .crypto_rates import CryptoRates
from keyboards import main_menu_keyboard
import aiohttp
import requests
from .otstuk import send_order_notification

logging.basicConfig(level=logging.INFO)

CHECK_INTERVAL = 30

payment_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="USDT TRC20"), KeyboardButton(text="USDT BEP20")],
        [KeyboardButton(text="ETH"), KeyboardButton(text="BITCOIN")],
        [KeyboardButton(text="БАЛАНС БОТА"),KeyboardButton(text="РУБЛИ")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True
)

async def payment_options_handler(message: Message, user_context: dict):
    user_id = message.from_user.id
    if user_id not in handlers.shared_context.user_context:
        handlers.shared_context.user_context[user_id] = {}
    handlers.shared_context.user_context[user_id]["step"] = "payment_pending"
    await message.answer(
        "Выберите способ оплаты: ⬇️\n\nEnglish: Choose a payment method: ⬇️",
        reply_markup=payment_keyboard
    )

def register_payment_handler(dp: Dispatcher):
    dp.message.register(payment_options_handler, lambda message: message.text == "Купить")

    @dp.message(lambda message: message.text == "Купить")
    async def buy_handler(message: Message, bot: Bot):
        await payment_options_handler(message, bot)

    async def _process_payment(message: Message, bot: Bot, payment_method: str, crypto_type: str = None):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        logging.info(f"{log_id} - payment_handler.py - _process_payment: User {user_id}")

        if handlers.shared_context.user_context and user_id in handlers.shared_context.user_context and handlers.shared_context.user_context[user_id].get("payment_status") == "pending":
            logging.info(f"{log_id} - payment_handler.py - _process_payment: payment_status is pending - игнорируем новый заказ")
            await bot.send_message(message.chat.id, "У вас уже есть незавершенный заказ. \n\n You already have an incomplete order")
            return

        user_context = handlers.shared_context.user_context.get(user_id, {})
        product_id = user_context.get("selected_product_id")
        product_price = Decimal(str(user_context.get("selected_product_price")))
        random_cents = Decimal(str(round(random.uniform(0.01, 0.99), 2)))
        payment_amount = (product_price + random_cents).quantize(Decimal("0.00"))

        handlers.shared_context.user_context[user_id]["payment_method"] = payment_method
        handlers.shared_context.user_context[user_id]["amount"] = payment_amount
        handlers.shared_context.user_context[user_id]["product_name"] = user_context.get("product_name")
        handlers.shared_context.user_context[user_id]["category_name"] = user_context.get("selected_category")
        handlers.shared_context.user_context[user_id]["selected_product"] = {
            "name": user_context.get("product_name"),
            "category": user_context.get("selected_category"),
            "id": product_id
        }
        handlers.shared_context.user_context[user_id]["selected_product_price"] = product_price
        handlers.shared_context.user_context[user_id]["payment_id"] = f"crypto_payment_{uuid.uuid4()}"
        handlers.shared_context.user_context[user_id]["amount_with_cents"] = payment_amount
        handlers.shared_context.user_context[user_id]["paid_products_table"] = user_context.get("selected_table")
        handlers.shared_context.user_context[user_id]["crypto_amount"] = None

        wallet_address = get_wallet_address(payment_method)
        if not wallet_address:
            logging.error(
                f"{log_id} - payment_handler.py - _process_payment: не удалось получить {payment_method} адрес кошелька")
            await message.answer("Ошибка: Не удалось получить адрес кошелька. Попробуйте позже \n\n Error: Could not get wallet address. Please try again later")
            return

        payment_message = ""
        if crypto_type:
            crypto_data = await CryptoRates.convert_usd_to_crypto(payment_amount, crypto_type)
            if not crypto_data:
                logging.error(
                    f"{log_id} - payment_handler.py - _process_payment: User {user_id}, Failed to convert USD to {crypto_type}.")
                await message.answer(f"Ошибка: Не удалось конвертировать USD в {crypto_type}. Попробуйте позже. \n\n Error: Failed to convert USD to {crypto_type}. Please try again later.")
                return
            crypto_amount = crypto_data.get('crypto_amount')
            handlers.shared_context.user_context[user_id][f"{crypto_type.lower()}_amount"] = crypto_amount
            handlers.shared_context.user_context[user_id]["crypto_amount"] = crypto_amount
            payment_message = f"😎 Вы выбрали оплату в {payment_method}\n\n" \
                              f"💵 Адрес для пополнения: <code>{wallet_address}</code> (Копируется нажатием)\n\n" \
                              f"✍️ Сумма к оплате: <code>{crypto_amount:.8f}</code>  {crypto_type.upper()} (Копируется нажатием)\n" \
                              f"Пожалуйста, отправьте <b>ТОЧНО</b> указанную сумму в {crypto_type.upper()}.\n\n" \
                              f"☝️ Потом нажмите кнопку <b>ОПЛАТИЛ</b>, чтобы бот автоматически выдал вам ваш заказ после проверки платежа"
            payment_message += f"\n\nEnglish: 😎 You have chosen to pay with {payment_method}\n\n" \
                              f"💵 Deposit address: <code>{wallet_address}</code> (Copied by pressing)\n\n" \
                              f"✍️ Amount to pay: <code>{crypto_amount:.8f}</code> {crypto_type.upper()} (Copied by pressing)\n" \
                              f"Please send the <b>EXACT</b> amount in {crypto_type.upper()}.\n\n" \
                              f"☝️ After that press the <b>PAID</b> button so the bot will send your order after verification."
        else:
            payment_message = f"😎 Вы выбрали {payment_method}\n\n" \
                              f"💵 Адрес для пополнения: <code>{wallet_address}</code> (Копируется нажатием) \n\n" \
                              f"✍️ Сумма к оплате: {payment_amount} USD\n" \
                              f"Пожалуйста, отправьте <b>ТОЧНО</b> указанную сумму на указанный выше адрес.\n\n" \
                              f"☝️ Потом нажмите кнопку <b>ОПЛАТИЛ</b>, чтобы бот автоматически выдал вам ваш заказ после проверки платежа"
            payment_message += f"\n\nEnglish: 😎 You have chosen {payment_method}\n\n" \
                              f"💵 Deposit address: <code>{wallet_address}</code> (Copied by pressing)\n\n" \
                              f"✍️ Amount to pay: {payment_amount} USD\n" \
                              f"Please send the <b>EXACT</b> amount to the address above.\n\n" \
                              f"☝️ After that press the <b>PAID</b> button so the bot will send your order after verification."

        support_chat_link = "https://t.me/thai_hub_supp"

        payment_confirmation_keyboard = ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="Оплатил / Paid")],
                [KeyboardButton(text="Отказаться / Cancel")],
                 [KeyboardButton(text="САППОРТ / SUPPORT", url=support_chat_link)],
            ]
        )

        await message.answer(payment_message, reply_markup=payment_confirmation_keyboard, parse_mode='HTML')

    @dp.message(lambda message: message.text == "USDT TRC20")
    async def usdt_trc20_payment_handler(message: Message, bot: Bot):
        await _process_payment(message, bot, "USDT_TRC20")

    @dp.message(lambda message: message.text == "USDT BEP20")
    async def usdt_bep20_payment_handler(message: Message, bot: Bot):
        await _process_payment(message, bot, "USDT_BEP20")

    @dp.message(lambda message: message.text == "ETH")
    async def eth_payment_handler(message: Message, bot: Bot):
        await _process_payment(message, bot, "ETH", "eth")

    @dp.message(lambda message: message.text == "BITCOIN")
    async def bitcoin_payment_handler(message: Message, bot: Bot):
        await _process_payment(message, bot, "BITCOIN", "btc")

    @dp.message(lambda message: message.text == "БАЛАНС БОТА")
    async def bot_balance_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        logging.info(f"{log_id} - payment_handler.py - bot_balance_handler: User {user_id}")

        user_context = handlers.shared_context.user_context.get(user_id, {})
        product_id = user_context.get("selected_product_id")
        product_price = Decimal(str(user_context.get("selected_product_price")))
        random_cents = Decimal(str(round(random.uniform(0.01, 0.99), 2)))
        payment_amount = (product_price + random_cents).quantize(Decimal("0.00"))
        logging.info(
            f"{log_id} - payment_handler.py - bot_balance_handler: User {user_id}, Product ID: {product_id}, Price: {product_price}")
        handlers.shared_context.user_context[user_id]["payment_method"] = "BALANCE"
        handlers.shared_context.user_context[user_id]["amount"] = payment_amount
        handlers.shared_context.user_context[user_id]["product_name"] = user_context.get("product_name")
        handlers.shared_context.user_context[user_id]["category_name"] = user_context.get("selected_category")
        handlers.shared_context.user_context[user_id]["selected_product"] = {
            "name": user_context.get("product_name"),
            "category": user_context.get("selected_category"),
            "id": product_id
        }
        handlers.shared_context.user_context[user_id]["selected_product_price"] = product_price
        handlers.shared_context.user_context[user_id]["payment_id"] = f"bot_balance_{uuid.uuid4()}"
        handlers.shared_context.user_context[user_id]["images"] = user_context.get("selected_images")
        handlers.shared_context.user_context[user_id]["amount_with_cents"] = payment_amount
        handlers.shared_context.user_context[user_id]["paid_products_table"] = user_context.get("selected_table")

        user_balance = get_user_balance(user_id)
        if user_balance is None:
            logging.warning(
                f"{log_id} - payment_handler.py - bot_balance_handler: User {user_id} - Баланс не найден.")
            await message.answer("Ошибка: Не удалось получить ваш баланс. \n\n Error: Could not get your balance.")
            return
        user_balance = Decimal(str(user_balance))

        balance_confirmation_keyboard = ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="Оплатить / Pay")],
                [KeyboardButton(text="Отказаться / Cancel")],
                [KeyboardButton(text="САППОРТ / SUPPORT", url="https://t.me/thai_hub_supp")],
            ]
        )

        await message.answer(
            f"😎 Вы выбрали оплату с баланса бота.\n\n"
            f"💰 Баланс вашего бота: {user_balance}\n"
            f"✍️ Сумма к оплате: {payment_amount} USD\n"
             f"\n\nEnglish: 😎 You have chosen to pay with your bot balance.\n\n"
            f"💰 Your bot balance: {user_balance}\n"
            f"✍️ Amount to pay: {payment_amount} USD\n",
            reply_markup=balance_confirmation_keyboard
        )

    @dp.message(lambda message: message.text == "РУБЛИ")
    async def rub_payment_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        logging.info(f"{log_id} - payment_handler.py - rub_payment_handler: User {user_id}")

        user_context = handlers.shared_context.user_context.get(user_id, {})
        product_price = Decimal(str(user_context.get("selected_product_price")))
        random_cents = Decimal(str(round(random.uniform(0.01, 0.99), 2)))
        payment_amount_usd = (product_price + random_cents).quantize(Decimal("0.00"))

        handlers.shared_context.user_context[user_id]["payment_method"] = "RUB"
        handlers.shared_context.user_context[user_id]["amount"] = payment_amount_usd
        handlers.shared_context.user_context[user_id]["payment_id"] = f"rub_payment_{uuid.uuid4()}"
        handlers.shared_context.user_context[user_id]["amount_with_cents"] = payment_amount_usd

        crypto_data = await CryptoRates.convert_usd_to_crypto(payment_amount_usd, "btc")
        if not crypto_data:
            logging.error(
                f"{log_id} - payment_handler.py - rub_payment_handler: User {user_id}, Failed to convert USD to BTC.")
            await message.answer(f"Ошибка: Не удалось конвертировать USD в BTC. Попробуйте позже. \n\n Error: Failed to convert USD to BTC. Please try again later.")
            return
        btc_amount = crypto_data.get('crypto_amount')
        handlers.shared_context.user_context[user_id]["crypto_amount"] = btc_amount
        btc_wallet_address = get_wallet_address("BITCOIN")

        if not btc_wallet_address:
             logging.error(
                f"{log_id} - payment_handler.py - rub_payment_handler: не удалось получить адрес кошелька BITCOIN")
             await message.answer("Ошибка: Не удалось получить адрес кошелька. Попробуйте позже \n\n Error: Could not get wallet address. Please try again later")
             return


        payment_message = (
    "😎 <b>Инструкция по оплате рублями</b>\n"
    "<tg-emoji emoji-id=\"5368786339707134225\">💸</tg-emoji> Которая не отнимет у вас больше <b>5-ти минут</b>\n\n"
    "<tg-emoji emoji-id=\"5442219117703293993\">🤝</tg-emoji> <b>Обратитесь к надежному обменнику</b> <a href='http://t.me/HUSTLE_BTC_BOT?start=7644052379'>@HUSTLE_BTC_BOT</a>\n\n"
    "Нажмите кнопку <b>Запустить</b>\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">➡️</tg-emoji> Далее нажмите - <b>Купить</b>\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">➡️</tg-emoji> Далее выберете - <b>BTC</b>\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">➡️</tg-emoji> Далее выберете - <b>Перевод на карту или СПБ</b>\n\n"
    f"<tg-emoji emoji-id=\"5368786339707658093\">💰</tg-emoji> <b>Необходимая сумма:</b> <code>{btc_amount:.8f}</code> (Копируется нажатием)\n\n"
    f"<tg-emoji emoji-id=\"5368786339708972509\">✉️</tg-emoji> <b>Отправьте наш BTC кошелёк</b> и <b>ТОЧНУЮ</b> сумму в обменник:\n"
    f"<code>{btc_wallet_address}</code>\n (Копируется нажатием)\n\n"
    "<tg-emoji emoji-id=\"5194812979794551452\">💳</tg-emoji> <b>Вам выдадут карту</b>, куда перевести рубли.\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">💸</tg-emoji> <b>Переводите</b>\n\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">✅</tg-emoji> <b>После того как обменник подтвердит перевод</b>,\n"
    "<tg-emoji emoji-id=\"5368786339708972509\">✅</tg-emoji> нажмите кнопку - <b>ОПЛАТИЛ</b>"
)

        support_chat_link = "https://t.me/thai_hub_supp"

        payment_confirmation_keyboard = ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[
                [KeyboardButton(text="Оплатил / Paid")],
                [KeyboardButton(text="Отказаться / Cancel")],
                [KeyboardButton(text="САППОРТ / SUPPORT", url=support_chat_link)],
            ]
        )

        await message.answer(payment_message, reply_markup=payment_confirmation_keyboard, parse_mode='HTML', disable_web_page_preview=True)


    async def _create_and_process_order(message: Message, bot: Bot, payment_method: str):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        payment_uuid = handlers.shared_context.user_context[user_id].get("payment_id")
        amount = handlers.shared_context.user_context[user_id].get("amount", "unknown")
        product_name = handlers.shared_context.user_context[user_id].get("product_name", "unknown")
        category_name = handlers.shared_context.user_context[user_id].get("selected_category", "unknown")
        product_id = handlers.shared_context.user_context[user_id].get("selected_product_id")

        amount_with_cents = handlers.shared_context.user_context[user_id].get("amount_with_cents", "unknown")
        crypto_amount = handlers.shared_context.user_context[user_id].get("crypto_amount")

        user_obj = await bot.get_chat(user_id)
        username = user_obj.username if user_obj.username else 'нет юзернейма'

        logging.info(
            f"{log_id} - payment_handler.py - _create_and_process_order: Создаем новый ордер")
        new_order = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "product_name": product_name,
            "category": category_name,
            "amount": float(amount) if amount != "unknown" else None,
            "payment_id": payment_uuid,
            "status": "Ожидание подтверждения" if payment_method != "BALANCE" else "Выполнен",
            "city": handlers.shared_context.user_context[user_id].get("selected_city"),
            "district": handlers.shared_context.user_context[user_id].get("selected_district"),
            "crypto_amount": crypto_amount,
            "product_id": int(product_id) if product_id else None,
        }

        if payment_method == "BALANCE":
            new_order["paid_products_table"] = handlers.shared_context.user_context[user_id].get("paid_products_table")

        add_order(new_order)
        logging.info(
            f"{log_id} - payment_handler.py - {'paid_handler' if payment_method != 'BALANCE' else 'paid_balance_handler'}: Создаем новый ордер {new_order} для оплаты")

        if payment_method != "BALANCE":
            text = (
                f"✅ Спасибо за заказ!\n\n\nСумма к оплате: {amount} \n\n"
                f"Как только мы получим от вас оплату, вам АВТОМАТИЧЕСКИ, будет выдан заказанный товар."
                f"\n\nEnglish: ✅ Thank you for your order!\n\n\nAmount to pay: {amount} \n\n"
                f"As soon as we receive your payment, your order will be issued AUTOMATICALLY."
            )

            await message.answer(
                text,
                reply_markup = main_menu_keyboard()
            )

            user_obj = await bot.get_chat(user_id)
            username = user_obj.username if user_obj.username else 'нет юзернейма'
            try:
                 await send_order_notification(
                    bot=bot,
                    user_id=user_id,
                    log_id=log_id,
                    username=username,
                    product_name=product_name,
                    category_name=category_name,
                    amount=amount,
                    order_id=new_order.get("id"),
                    status="Ожидание подтверждения",
                    payment_method=payment_method,
                    wallet_address="неизвестен",
                    order_text=text,
                    order_media=None
                )
            except Exception as e:
                  logging.error(f"payment_handler.py - _create_and_process_order: Ошибка при отправке уведомления об оплате: {e}")

        if payment_method == "USDT_TRC20":
            start_usdt_trc20_payment_check(message, bot, new_order)
        elif payment_method == "USDT_BEP20":
            start_usdt_bep20_payment_check(message, bot, new_order)
        elif payment_method == "BITCOIN":
            start_btc_payment_check(message, bot, new_order)
        elif payment_method == "ETH":
            start_payment_check_eth(message, bot, new_order)
        elif payment_method == "BALANCE":
             await process_bot_balance_purchase(message, bot, new_order)
        elif payment_method == "RUB":
             start_btc_payment_check(message, bot, new_order)

    @dp.message(lambda message: message.text == "Оплатил / Paid")
    async def paid_handler(message: Message, bot: Bot):
       user_id = message.from_user.id
       payment_method = handlers.shared_context.user_context[user_id].get("payment_method")

       if handlers.shared_context.user_context and user_id in handlers.shared_context.user_context and handlers.shared_context.user_context[user_id].get("payment_status") == "pending":
            logging.info(f"payment_handler.py - paid_handler: payment_status is pending - игнорируем нажатие ОПЛАТИЛ")
            await bot.send_message(message.chat.id, "У вас уже есть незавершенный заказ. \n\n You already have an incomplete order")
            return
       await _create_and_process_order(message, bot, payment_method)

    @dp.message(lambda message: message.text == "Оплатить / Pay")
    async def paid_balance_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        amount = handlers.shared_context.user_context[user_id].get("amount")
        user_balance = Decimal(str(get_user_balance(user_id)))

        if user_balance is None or user_balance < Decimal(str(amount)):
            logging.warning(
                f"{log_id} - payment_handler.py - paid_balance_handler: User {user_id} - Недостаточно средств на балансе.")
            await message.answer("Ошибка: Недостаточно средств на балансе. \n\n Error: Insufficient funds on your balance.")
            return

        new_balance = user_balance - Decimal(str(amount))
        set_user_balance(user_id, float(new_balance))
        logging.info(
            f"{log_id} - payment_handler.py - paid_balance_handler: User {user_id} - Баланс обновлен, новый баланс: {new_balance}."
        )

        await _create_and_process_order(message, bot, "BALANCE")

    @dp.message(lambda message: message.text == "Отказаться / Cancel")
    async def cancel_payment_handler(message: Message):
        user_id = message.from_user.id
        if handlers.shared_context.user_context and user_id in handlers.shared_context.user_context:
            task = handlers.shared_context.user_context[user_id].get("payment_task")
            if task:
                task.cancel()
                logging.info(f"payment_handler.py - cancel_payment_handler: Асинхронная задача для платежа отменена.")
            handlers.shared_context.user_context[user_id] = {}
            logging.info(f"payment_handler.py - cancel_payment_handler: Контекст пользователя {user_id} очищен.")

        await message.answer("Вы вернулись в главное меню. \n\n You have returned to the main menu.", reply_markup=ReplyKeyboardRemove())
        await message.answer("Добро пожаловать! Выберите действие из меню: \n\n Welcome! Select an action from the menu:", reply_markup=main_menu_keyboard())

    @dp.message(lambda message: message.text == "САППОРТ / SUPPORT")
    async def open_support_chat_handler(message: Message, bot: Bot):
        support_chat_link = "https://t.me/thai_hub_supp"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Перейти в чат / Go to chat", url=support_chat_link)]
        ])

        await message.answer("Для связи с поддержкой нажмите кнопку ниже: \n\n To contact support, click the button below:", reply_markup=keyboard)

    async def show_product_with_location_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        log_id = uuid.uuid4()
        logging.info(f"{log_id} - payment_handler.py - show_product_with_location_handler: User {user_id}")

        user_context = handlers.shared_context.user_context.get(user_id, {})
        selected_product_id = user_context.get("selected_product_id")
        selected_city = user_context.get("selected_city")
        selected_district = user_context.get("selected_district")
        product_name = user_context.get("product_name")
        logging.info(
            f"{log_id} - payment_handler.py - show_product_with_location_handler: product_name: {product_name}, city: {selected_city}, district: {selected_district}")

        paid_products_table_names = [
            "gr_1_paid_products",
            "gr_2_paid_products",
            "gr_5_paid_products",
            "gr_10_paid_products",
            "item_1_paid_products",
            "item_2_paid_products",
            "item_5_paid_products",
            "item_10_paid_products",
            "item_20_paid_products",
            "item_50_paid_products",
        ]
        for table_name in paid_products_table_names:
            location_info = get_paid_product_by_location(product_name, selected_city, selected_district, table_name)
            if location_info:
                logging.info(
                    f"{log_id} - payment_handler.py - show_product_with_location_handler: Найдено в таблице {table_name},  {location_info}"
                )

                handlers.shared_context.user_context[user_id]["selected_table"] = table_name
                handlers.shared_context.user_context[user_id]["selected_instruction"] = location_info.get("instruction")
                handlers.shared_context.user_context[user_id]["selected_images"] = location_info.get("images")

                await bot.send_message(
                    user_id,
                    f"Инструкция: <code>{location_info.get('instruction')}</code>",
                    reply_markup=payment_keyboard,
                    parse_mode='HTML'
                )
                return

        await message.answer(
            "Извините, не удалось найти товар в указанном районе. \n\n Sorry, could not find the product in the specified area.",
            reply_markup=main_menu_keyboard()
        )

async def process_bot_balance_purchase(message: types.Message, bot: Bot, order: dict):
    user_id = message.from_user.id
    log_id = uuid.uuid4()
    product_name = order.get("product_name")
    order_id = order.get("id")
    category_name = order.get("category")
    product_price = Decimal(str(order.get("amount")))

    logging.info(
        f"{log_id} - payment_handler.py - process_bot_balance_purchase: User {user_id} оплатил с баланса бота, заказ: {order_id}"
    )

    user_city = order.get("city")
    user_district = order.get("district")
    user_obj = await bot.get_chat(user_id)
    username = user_obj.username if user_obj.username else 'нет юзернейма'

    location_infos = get_location_info_from_paid_products(product_name, user_city, user_district)
    if not location_infos:
        logging.warning(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Товар '{product_name}' не найден ни в одной таблице paid_products."
        )
        text = (
            f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
            f"Товар: {product_name}\n\n"
            f"Инструкция: свяжитесь с администратором."
            f"\n\nEnglish: ✅ Payment confirmed! Order №{order_id}\n\n"
            f"Product: {product_name}\n\n"
            f"Instruction: Contact admin."
        )
        sent_message = await bot.send_message(chat_id=user_id, text=text)

        await send_order_notification(
            bot=bot,
            user_id=user_id,
            log_id=log_id,
            username=username,
            product_name=product_name,
            category_name=category_name,
            amount=product_price,
            order_id=order_id,
            status="Выполнен",
            payment_method="BALANCE",
            wallet_address="Баланс бота",
            order_text=sent_message.text if sent_message else text,
            order_media=None
        )

        return

    location_info = location_infos[0]
    logging.info(
        f"{log_id} - payment_handler.py - process_bot_balance_purchase: Локация найдена: {location_info}"
    )
    instruction_text = location_info.get('instruction') if location_info.get("instruction") else "Нет инструкции / No instruction"

    text = (
        f"🎉 Спасибо за покупку!\n"
        f"💰 Оплаченная сумма: {product_price}\n"
        f"✅ Ваш заказ успешно оплачен с баланса бота.\n\n"
        f"📍 Локация: {user_city}, {user_district}\n"
        f"🗺️ Инструкции: <code>{instruction_text}</code>"
        f"\n\nEnglish: 🎉 Thank you for your purchase!\n"
        f"💰 Paid amount: {product_price}\n"
        f"✅ Your order has been successfully paid with your bot balance.\n\n"
        f"📍 Location: {user_city}, {user_district}\n"
        f"🗺️ Instructions: <code>{instruction_text}</code>"
    )

    order_text = (
            f"💰 Успешная оплата!\n"
            f"👤 Покупатель: @{username} (ID: {user_id})\n"
            f"📦 Товар: {product_name}\n"
            f"💵 Сумма: {product_price} USD\n"
            f"🔗 Адрес: Баланс бота\n\n"
            f"📍 Локация: {user_city}, {user_district}\n"
            f"🗺️ Инструкции: {instruction_text}"
        )

    media_group = []
    if (
        location_info.get("images")
        and isinstance(location_info.get("images"), str)
    ):
        images = location_info.get("images").replace("[", "").replace("]", "").replace('"', "").split(", ")
        for image_path in images:
            if image_path:
                full_image_path = os.path.join(os.path.dirname(__file__), "..", image_path.lstrip("\\/"))
                if os.path.exists(full_image_path):
                    media_group.append(types.InputMediaPhoto(media=types.FSInputFile(full_image_path)))
                else:
                    logging.warning(
                        f"{log_id} - payment_handler.py - process_bot_balance_purchase: Файл {full_image_path} не найден"
                    )

    try:
        if media_group:
         await bot.send_media_group(chat_id=user_id, media=media_group)
        await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")

    except Exception as e:
        logging.error(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Ошибка при отправке сообщения пользователю: {e}"
        )

    try:
        move_paid_product_to_sold_products(product_name, user_city, user_district, user_id, location_info.get('id'), location_info.get('table_name'))
        logging.info(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Товар '{product_name}' перемещен в sold_products"
        )
    except Exception as e:
        logging.error(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Ошибка при перемещении товара в sold_products: {e}"
        )

        logging.info(
        f"{log_id} - payment_handler.py - process_bot_balance_purchase: Добавлена запись в таблицу sold_products: {product_name} - {user_city}, {user_district}"
    )

    try:
        user_data = get_user(user_id)
        if user_data and user_data[2] is not None:
            referrer_id = user_data[2]
            bonus_amount = (product_price * Decimal("0.03")).quantize(Decimal("0.00"))
            referrer_data = get_user(referrer_id)
            if referrer_data:
                new_referrer_balance = Decimal(str(referrer_data[3])) + bonus_amount
                add_to_user_balance(referrer_id, float(new_referrer_balance))
                update_referral_purchases_amount(
                    referrer_id, float(product_price)
                )
                update_referral_purchases_count_column(referrer_id, user_id)

                logging.info(
                    f"{log_id} - payment_handler.py - process_bot_balance_purchase: Пользователю {referrer_id} начислен бонус {bonus_amount}. Новый баланс {new_referrer_balance}"
                )

                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=(
                            f"🎉 Ваш реферал совершил покупку!\n\n"
                            f"💰 Вы получили бонус в размере {bonus_amount:.2f} USD.\n"
                            f"💰 Ваш текущий баланс: {new_referrer_balance:.2f} USD."
                            f"\n\nEnglish: 🎉 Your referral has made a purchase!\n\n"
                            f"💰 You received a bonus of {bonus_amount:.2f} USD.\n"
                            f"💰 Your current balance: {new_referrer_balance:.2f} USD."
                        ),
                    )
                    logging.info(
                        f"{log_id} - payment_handler.py - process_bot_balance_purchase: Уведомление о реферальном бонусе отправлено пользователю {referrer_id}."
                    )
                except Exception as e:
                    logging.error(
                        f"{log_id} - payment_handler.py - process_bot_balance_purchase: Ошибка при отправке уведомления рефереру {referrer_id}: {e}"
                    )
            else:
                logging.warning(
                    f"{log_id} - payment_handler.py - process_bot_balance_purchase: Реферер с ID {referrer_id} не найден")
    except Exception as e:
        logging.error(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Ошибка при начислении реферального бонуса или отправке уведомления: {e}"
        )

    try:
        await send_order_notification(
            bot=bot,
            user_id=user_id,
            log_id=log_id,
            username=username,
            product_name=product_name,
            category_name=category_name,
            amount=product_price,
            order_id=order_id,
            status="Выполнен",
            payment_method="BALANCE",
            wallet_address="Баланс бота",
            order_text=order_text,
            order_media=media_group
        )
    except Exception as e:
        logging.error(f"{log_id} - payment_handler.py - process_bot_balance_purchase: Ошибка при отправке уведомления об оплате: {e}")

    if handlers.shared_context.user_context and user_id in handlers.shared_context.user_context:
        task = handlers.shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(
                f"{log_id} - payment_handler.py - process_bot_balance_purchase: Асинхронная задача для платежа {order.get('payment_id')} отменена."
            )
        handlers.shared_context.user_context[user_id] = {}
        logging.info(
            f"{log_id} - payment_handler.py - process_bot_balance_purchase: Контекст пользователя {user_id} очищен."
        )

    await bot.send_message(chat_id=user_id, text="Вы вернулись в главное меню. \n\n You have returned to the main menu.", reply_markup=main_menu_keyboard())

def register_payment_handlers(dp: Dispatcher):
    register_payment_handler(dp)