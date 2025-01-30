import logging
import asyncio
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import time
import aiohttp
import os
from aiogram import Bot, types
from aiogram.types import Message, InputMediaPhoto, FSInputFile
from handlers import shared_context
from database import (
    get_user,
    set_user_balance,
    update_referral_purchases_amount,
    get_wallet_address,
    get_product_category,
    get_product_price,
    get_location_info_from_paid_products,
    move_paid_product_to_sold_products,
    add_to_user_balance,
    add_referral_reward,
    update_order_status,
    update_referral_purchases_count_column
)
from .otstuk import send_order_notification
import uuid
from keyboards import main_menu_keyboard
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log',
    filemode='a'
)

CHECK_INTERVAL = 30  # Интервал проверки в секундах
ETHERSCAN_API_KEY = 'U4B9RMNY7995MB6EMSPN8NTGCJUI3TF3JI'  # Замените на ваш настоящий Etherscan API ключ
ETHERSCAN_API_URL = 'https://api.etherscan.io/api'


def escape_markdown(text):
    if not text:
        return ""
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)

async def get_transactions(eth_wallet_address, limit=20, start_timestamp=None):
    """Получает транзакции для указанного адреса через Etherscan API."""
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': eth_wallet_address,
        'startblock': 0,
        'endblock': 99999999,
        'page': 1,
        'offset': limit,
        'sort': 'desc',
        'apikey': ETHERSCAN_API_KEY
    }
    if start_timestamp:
            start_block = await _get_block_number_by_timestamp(start_timestamp)
            if start_block is not None:
                params['startblock'] = start_block
    transactions = []
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(ETHERSCAN_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = await response.json()
            if data['status'] != '1':
                logging.error(f"eth_checker.py - get_transactions: Etherscan API Error: {data.get('message', 'Unknown error')}")
                return []

            transactions = data.get('result', [])
            while 'fingerprint' in data.get('meta', {}):
                 params['fingerprint'] = data['meta']['fingerprint']
                 response = await session.get(ETHERSCAN_API_URL, params=params, timeout=10)
                 response.raise_for_status()
                 data = await response.json()
                 transactions.extend(data.get('result', []))
                 if len(transactions) >= limit:
                    break

    except aiohttp.ClientError as e:
        logging.error(f"eth_checker.py - get_transactions: Ошибка при запросе к Etherscan API: {e}")
        return []
    except Exception as e:
        logging.error(f"eth_checker.py - get_transactions: Неизвестная ошибка при получении транзакций: {e}")
        return []

    # Фильтруем входящие транзакции
    incoming_tx = [
        tx for tx in transactions
        if tx.get('to', '').lower() == eth_wallet_address.lower() and tx.get('input', '').lower() == '0x'
    ]
    logging.info(
        f"eth_checker.py - get_transactions: "
        f"Получено {len(incoming_tx)} входящих транзакций с Etherscan API"
    )
    return incoming_tx


async def _get_block_number_by_timestamp(timestamp):
    """Получает номер блока по времени через запрос к Etherscan API."""
    url = 'https://api.etherscan.io/api'
    params = {
        'module': 'block',
        'action': 'getblocknobytime',
        'timestamp': int(timestamp.timestamp()),
        'closest': 'before',
        'apikey': ETHERSCAN_API_KEY
    }
    try:
       async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                data = await response.json()
                if data['status'] == '1':
                    return data['result']
                else:
                    logging.error(
                        f"eth_checker.py - get_block_number_by_timestamp: "
                        f"Etherscan API Error: {data.get('message')}"
                    )
                    return None
    except Exception as e:
        logging.error(
            f"eth_checker.py - get_block_number_by_timestamp: "
            f"Ошибка при запросе к API: {e}"
        )
        return None


async def check_payment(message: Message, bot: Bot, order: dict, last_hour: datetime):
    """Проверяет поступление оплаты и отправляет информацию о товаре."""
    payment_id = order.get("payment_id")
    amount_decimal = Decimal(str(order.get("crypto_amount"))) #  <----- Используем crypto_amount для проверки
    user_id = message.from_user.id
    order_id = order.get("id")
    
    logging.info(f"eth_checker.py - check_payment: Начало проверки платежа {payment_id} для пользователя {user_id}, Order: {order}")
    start_time = time.time()
    
    # Получаем адрес кошелька ETH из базы данных
    eth_wallet_address = get_wallet_address('ETH')
    if not eth_wallet_address:
        logging.error("eth_checker.py - check_payment: ETH wallet address not found in database")
        await bot.send_message(user_id, "Ошибка: Не удалось получить адрес кошелька для проверки оплаты. \n\n Error: Could not get wallet address for payment verification.")
        return
    
    try:
        while time.time() - start_time < 1800:
            try:
                transactions = await get_transactions(eth_wallet_address, limit=20, start_timestamp=last_hour)
                logging.info(f"eth_checker.py - check_payment: Получено транзакций: {len(transactions)}")
                if not transactions:
                    logging.info(f"eth_checker.py - check_payment: Нет транзакций для проверки")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                for tr in transactions:
                    if await _process_transaction(tr, message, bot, order, amount_decimal, eth_wallet_address):
                         return

                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logging.error(
                    f"eth_checker.py - check_payment: Неизвестная ошибка в цикле проверки платежа: {e}"
                )
                await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
         logging.info(f"eth_checker.py - check_payment: Проверка платежа {payment_id} была отменена.")

async def _get_product_data(product_name, order, user_id, bot):
    """
    Получает данные о продукте из базы данных.
    """
    logging.info(
        f"eth_checker.py - _get_product_data: "
        f"Начинаем поиск категории и цены для продукта: {product_name}"
        )
    product_name_for_category = product_name.split(' ')[0]
    category_name = get_product_category(product_name_for_category)
    product_price = get_product_price(order.get("product_id"))
    if not category_name or product_price is None:
        logging.warning(
            f"eth_checker.py - _get_product_data: "
            f"Категория или цена товара не найдены для product: {product_name}"
        )
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ Оплата подтверждена! Заказ №{order.get('id')}\n\n"
                f"Товар: {product_name}\n\n"
                f"Инструкция: Не удалось получить данные о товаре. "
                f"Свяжитесь с администратором."
                f"\n\nEnglish: ✅ Payment confirmed! Order №{order.get('id')}\n\n"
                f"Product: {product_name}\n\n"
                f"Instruction: Could not get product data. Contact admin."
            ),
        )
        return None
    logging.info(
            f"eth_checker.py - _get_product_data: "
            f"Категория '{category_name}', цена  '{product_price}' для товара: {product_name}"
        )
    return category_name, product_price


async def _process_transaction(tr, message: Message, bot: Bot, order: dict, amount_decimal: Decimal, eth_wallet_address: str) -> bool:
    """Обрабатывает транзакцию, отправляет информацию о товаре и уведомление."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    order_id = order.get("id")
    product_name = order.get("product_name")
    log_id = uuid.uuid4()
    logging.info(
        f"{log_id} - eth_checker.py - _process_transaction: "
        f"Начинаем обработку транзакции {payment_id} для пользователя {user_id}. Hash: {tr.get('hash')}"
    )

    value = tr.get('value')
    if value is None:
         logging.warning(f"{log_id} - eth_checker.py - _process_transaction: Пропущена транзакция {tr}. Не хватает данных: value")
         return False
    try:
         amount_received = Decimal(value) / Decimal(10 ** 18)
    except (ValueError, TypeError) as e:
         logging.error(f"{log_id} - eth_checker.py - _process_transaction: Ошибка при конвертации value: {e}, transaction: {tr}")
         return False

    logging.info(f"{log_id} - eth_checker.py - _process_transaction: Проверка платежа {payment_id}: Сумма к оплате = {amount_decimal}, Получено {amount_received}")
    to_address = tr.get('to').lower()

    if amount_received == amount_decimal and to_address == eth_wallet_address.lower():
         logging.info(f"{log_id} - eth_checker.py - _process_transaction: Платеж на сумму {amount_received} ETH подтвержден.")
         
         order["status"] = "Выполнен"
            
         if shared_context.user_context and user_id in shared_context.user_context:
            shared_context.user_context[user_id]["payment_status"] = "completed"
         else:
            logging.warning(f"{log_id} - eth_checker.py - _process_transaction: user_context not found for user_id: {user_id}")
         
        # Получаем данные товара
         product_data = await _get_product_data(product_name, order, user_id, bot)
         if not product_data:
                return True
         category_name, product_price = product_data
         user_city = order.get("city")
         user_district = order.get("district")

         if not user_city or not user_district:
               user_error_text = (
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"📦 Товар: {product_name}\n\n"
                        f"⚠️ Инструкция: Не удалось получить локацию. Свяжитесь с администратором."
                           f"\n\nEnglish: ✅ Payment confirmed! Order №{order_id}\n\n"
                        f"📦 Product: {product_name}\n\n"
                         f"⚠️ Instruction: Could not get location. Contact admin."
                    )
               await bot.send_message(
                    chat_id=user_id,
                    text=user_error_text,
                    parse_mode="HTML",
                )
               logging.info(
                    f"{log_id} - eth_checker.py - _process_transaction: Город или район не найден для товара '{product_name}'. Сообщение об ошибке отправлено"
                )
               return True

         # Ищем товар в paid_products
         paid_products = get_location_info_from_paid_products(product_name, user_city, user_district)
         if not paid_products:
                 user_error_text = (
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"📦 Товар: {product_name}\n\n"
                        f"⚠️ Инструкция: Товар не найден в базе. Свяжитесь с администратором."
                        f"\n\nEnglish: ✅ Payment confirmed! Order №{order_id}\n\n"
                        f"📦 Product: {product_name}\n\n"
                         f"⚠️ Instruction: Product not found in database. Contact admin."
                    )
                 await bot.send_message(
                    chat_id=user_id,
                    text=user_error_text,
                    parse_mode="HTML",
                 )
                 logging.info(
                    f"{log_id} - eth_checker.py - check_payment: Товар '{product_name}' не найден в paid_products"
                 )
                 return True

             # Выбираем любой товар из списка
         paid_product_data = paid_products[0]

            # Получаем id и имя таблицы
         paid_product_id = paid_product_data.get('id')
         table_name = paid_product_data.get('table_name')
         if not paid_product_id:
                logging.error(
                     f"{log_id} - eth_checker.py - _process_transaction: id товара не найден, хотя должен быть, проверьте структуру paid_products"
                )
                user_error_text = (
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"📦 Товар: {product_name}\n\n"
                        f"⚠️ Инструкция: id товара не найден, свяжитесь с админом."
                        f"\n\nEnglish: ✅ Payment confirmed! Order №{order_id}\n\n"
                        f"📦 Product: {product_name}\n\n"
                         f"⚠️ Instruction: Product id not found, contact admin."
                    )
                await bot.send_message(
                    chat_id=user_id,
                     text=user_error_text,
                     parse_mode="HTML"
                )
                return True
           
            # Формируем сообщения для пользователя
         instruction_text = paid_product_data.get('instruction') if paid_product_data.get("instruction") else "Нет инструкции / No instruction"
         escaped_instruction_text = re.sub(r'([`*_])', r'\\\1', instruction_text)
         user_text = (
                f"🎉 Спасибо за покупку!\n"
                f"💰 Оплаченная сумма: {amount_decimal} ETH\n"
                f"✅ Ваш заказ успешно оплачен криптовалютой (ETH)\n\n"
                f"📍 Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                f"🗺️ Инструкции: <code>{escaped_instruction_text}</code>"
                f"\n\nEnglish: 🎉 Thank you for your purchase!\n"
                f"💰 Paid amount: {amount_decimal} ETH\n"
                f"✅ Your order has been successfully paid with cryptocurrency (ETH)\n\n"
                f"📍 Location: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                 f"🗺️ Instructions: <code>{escaped_instruction_text}</code>"
            )
             # Формируем сообщение для отстука
         user_obj = await bot.get_chat(user_id)
         username = user_obj.username if user_obj.username else 'нет юзернейма'
         otstuk_text = (
                f"💰 Успешная оплата!\n"
                f"👤 Покупатель: @{username} (ID: {user_id})\n"
                f"📦 Товар: {product_name}\n"
                f"💵 Сумма: {order.get('amount')} USD\n" # <--- отпрвляем amount в долларах
                 f"🔗 Адрес: {eth_wallet_address}\n\n"
                f"📍 Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                 f"🗺️ Инструкции: <code>{escaped_instruction_text}</code>"
           )

         media_group = []
         if paid_product_data.get('images') and isinstance(paid_product_data.get('images'), str):
            images = paid_product_data.get('images').replace('[', '').replace(']', '').replace('"', '').split(', ')
            for image_path in images:
                if image_path:
                    full_image_path = os.path.join(
                        os.path.dirname(__file__),
                        "..",
                        image_path.lstrip("\\/"),
                    )
                    if os.path.exists(full_image_path):
                        media_group.append(InputMediaPhoto(media=FSInputFile(full_image_path)))
                    else:
                        logging.warning(f"{log_id} - eth_checker.py - _process_transaction: Файл {full_image_path} не найден")

         if media_group:
            try:
                logging.info(f"{log_id} - eth_checker.py - _process_transaction: Отправка сообщения с медиа и текстом: {media_group}")
                await bot.send_media_group(chat_id=user_id, media=media_group)
                await bot.send_message(chat_id=user_id, text=user_text, parse_mode="HTML")
                logging.info(f"{log_id} - eth_checker.py - _process_transaction: Сообщение с медиа и текстом отправлено успешно")
            except Exception as e:
                logging.error(f"{log_id} - eth_checker.py - _process_transaction: Ошибка отправки медиа: {e}")
                await bot.send_message(
                    chat_id=user_id,
                    text=user_text, parse_mode="HTML"
                )
                logging.info(f"{log_id} - eth_checker.py - _process_transaction: Сообщение об ошибке отправлено")
         else:
                await bot.send_message(
                    chat_id=user_id,
                    text=user_text, parse_mode="HTML"
                )
                logging.info(f"{log_id} - eth_checker.py - _process_transaction: Сообщение без медиа отправлено успешно")
            # Перемещаем товар в sold_products и удаляем из paid_products
         try:
                move_paid_product_to_sold_products(product_name, user_city, user_district, user_id, paid_product_id, table_name)
                logging.info(
                    f"{log_id} - eth_checker.py - _process_transaction: Товар '{product_name}' перемещен в sold_products"
                )
         except Exception as e:
                logging.error(
                    f"{log_id} - eth_checker.py - _process_transaction: Ошибка при перемещении товара в sold_products: {e}"
                )

            # Обновляем статус заказа на 'Выполнен'
         if update_order_status(order_id, "Выполнен"):
                logging.info(f"{log_id} - eth_checker.py - _process_transaction: Статус заказа {order_id} обновлен на 'Выполнен'")
         else:
                logging.error(f"{log_id} - eth_checker.py - _process_transaction: Ошибка при обновлении статуса заказа {order_id}")

            # Отправляем уведомление об успешной оплате
         try:
                await send_order_notification(
                    bot=bot,
                    user_id=user_id,
                    log_id=log_id,
                    username=username,
                    product_name=product_name,
                    category_name=category_name,
                    amount=order.get('amount'), # <----- отпрвляем amount в долларах
                    order_id=order_id,
                    status="Выполнен",
                    payment_method="ETH",
                     wallet_address=eth_wallet_address,
                     order_text=otstuk_text,
                    order_media=media_group
                )
         except Exception as e:
                logging.error(f"{log_id} - eth_checker.py - _process_transaction: Ошибка при отправке уведомления об оплате: {e}")
         

            # Начисляем реферальный бонус РЕФЕРЕРУ (если есть реферал)
         user_data = get_user(user_id)
         if user_data and user_data[2] is not None: # Проверяем, есть ли у пользователя реферер
                referrer_id = user_data[2]  # ID реферера
                bonus_amount = Decimal(str(product_price)) * Decimal("0.03")
                bonus_amount = bonus_amount.quantize(Decimal("0.01"))
                add_referral_reward(referrer_id, bonus_amount) # Начисляем бонус рефереру

                referrer_data = get_user(referrer_id)
                if referrer_data:
                   new_referrer_balance = Decimal(str(referrer_data[3])) + bonus_amount
                   new_referrer_balance = new_referrer_balance.quantize(Decimal("0.01"))
                   update_referral_purchases_amount(referrer_id, float(product_price))
                   # Добавляем запись в базу данных
                   update_referral_purchases_count_column(referrer_id, user_id)
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
                   except Exception as e:
                       logging.error(
                           f"{log_id} - eth_checker.py - _process_transaction: Ошибка при отправке уведомления рефереру {referrer_id}: {e}"
                       )
                else:
                   logging.warning(
                        f"{log_id} - eth_checker.py - _process_transaction: Реферер с ID {referrer_id} не найден"
                   )
         return True
    return False


def _payment_timeout_handler(message: Message, bot: Bot, order: dict):
    """Обрабатывает ситуацию, когда время ожидания оплаты истекло."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    logging.info(f"eth_checker.py - _payment_timeout_handler: Платеж {payment_id} не был получен в течение 30 минут.")
    # ИСПРАВЛЕНИЕ: Проверяем статус платежа перед обработкой таймаута.
    if shared_context.user_context and user_id in shared_context.user_context and shared_context.user_context[user_id].get("payment_status") == "completed":
       logging.info(f"eth_checker.py - _payment_timeout_handler: Пропускаем обработку таймаута для платежа {payment_id} - так как он уже оплачен")
       return
    order["status"] = "Отменен"
    
    if shared_context.user_context and user_id in shared_context.user_context:
        task = shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(
                f"eth_checker.py - _payment_timeout_handler: Асинхронная задача для платежа {payment_id} отменена."
            )
        shared_context.user_context[user_id]["payment_status"] = "failed"
        shared_context.user_context[user_id] = {}
        logging.info(
            f"eth_checker.py - _payment_timeout_handler: Оплата не прошла. Контекст пользователя {user_id} очищен."
        )
    else:
        logging.warning(
            f"eth_checker.py - _payment_timeout_handler: user_context not found for user_id: {user_id}"
        )
    asyncio.create_task(bot.send_message(
        chat_id=user_id,
        text="Время ожидания оплаты истекло. Ваш заказ отменён. \n\n English: Payment timeout. Your order has been canceled."
    ))

def start_payment_check(message: Message, bot: Bot, order: dict):
    """Запускает процесс проверки платежа."""
    payment_id = order.get("payment_id")
    amount = Decimal(str(order.get("crypto_amount"))) # Decimal
    user_id = message.from_user.id
    logging.info(f"eth_checker.py - start_payment_check: User {user_id}, Payment ID: {payment_id}, Amount: {amount}")
    
    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_status"] = "pending"
    else:
        logging.warning(f"eth_checker.py - start_payment_check: user_context not found for user_id: {user_id}")
    
    now = datetime.now(timezone.utc)
    last_hour = now - timedelta(hours=1)
    task = asyncio.create_task(_check_payment_task(message, bot, order, last_hour))
    
    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_task"] = task
    
    # Immediate return to the main menu
    asyncio.create_task(bot.send_message(message.chat.id, "Ожидаю подтверждения оплаты... \n\n English: Waiting for payment confirmation...", reply_markup=main_menu_keyboard()))
        
async def _check_payment_task(message: Message, bot: Bot, order: dict, last_hour: datetime):
    """Обертка для проверки платежа с отменой таска."""
    try:
        await check_payment(message, bot, order, last_hour)
    except asyncio.CancelledError:
        logging.info(f"eth_checker.py - _check_payment_task: Проверка платежа {order.get('payment_id')} отменена.")
    except Exception as e:
         logging.error(
                    f"eth_checker.py - _check_payment_task: Неизвестная ошибка в _check_payment_task: {e}"
                )
    finally:
        if shared_context.user_context and message.from_user.id in shared_context.user_context:
          task = shared_context.user_context[message.from_user.id].get("payment_task")
          if task:
            task.cancel()
            logging.info(
              f"eth_checker.py - _check_payment_task: Асинхронная задача для платежа {order.get('payment_id')} отменена."
          )
          shared_context.user_context[message.from_user.id].pop("payment_task", None) # удаляем таск из контекста
          logging.info(
            f"eth_checker.py - _check_payment_task: payment_task удалена из контекста пользователя {message.from_user.id}."
        )