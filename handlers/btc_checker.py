import logging
import asyncio
from decimal import Decimal
import os
import time
from aiogram import Bot, types
from aiogram.types import Message, InputMediaPhoto, FSInputFile
from handlers import shared_context
from datetime import datetime, timedelta
import aiohttp
import json
from database import (
    get_user,
    set_user_balance,
    update_referral_purchases_amount,
    get_wallet_address,
    get_product_category,
    get_product_price,
    get_location_info_from_paid_products,
    move_paid_product_to_sold_products,
    add_referral_reward,
    update_order_status,
    get_order_status, # <----- Добавлено: Импорт get_order_status
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


async def get_transactions(btc_wallet_address, limit=20, start_timestamp=None):
    """Получает транзакции для указанного адреса через Blockstream API."""
    blockstream_url = f"https://blockstream.info/api/address/{btc_wallet_address}/txs"
    headers = {"accept": "application/json"}
    params = {}

    logging.info(
        f"btc_checker.py - get_transactions: Запрос транзакций через Blockstream API для адреса: {btc_wallet_address}, start_timestamp: {start_timestamp}"
    )
    transactions = []
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(blockstream_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            response_json = await response.json()

            if isinstance(response_json, list):
                transactions = response_json
                logging.info(f"btc_checker.py - get_transactions: Получено транзакций с Blockstream API: {len(transactions)}")

            elif isinstance(response_json, dict):
                transactions = response_json.get('txs', [])
                logging.info(f"btc_checker.py - get_transactions: Получено транзакций с Blockstream API: {len(transactions)}")

                while 'fingerprint' in response_json.get('meta', {}):
                    params_next = {'fingerprint': response_json['meta']['fingerprint']}

                    response = await session.get(blockstream_url, params = params_next, headers=headers, timeout=10)
                    response.raise_for_status()
                    response_json = await response.json()

                    if isinstance(response_json, list):
                         transactions.extend(response_json)
                         logging.info(
                            f"btc_checker.py - get_transactions: Получено транзакций с Blockstream API (дополнительная страница): {len(response_json)}"
                          )
                         if len(transactions) >= limit:
                            break
                    elif isinstance(response_json, dict):
                         transactions.extend(response_json.get('txs', []))
                         logging.info(
                            f"btc_checker.py - get_transactions: Получено транзакций с Blockstream API (дополнительная страница): {len(response_json.get('txs', []))}"
                         )
                         if len(transactions) >= limit:
                             break
                    else:
                         logging.warning(
                            "btc_checker.py - get_transactions: Неизвестный тип данных получен от API."
                          )
                         break


    except aiohttp.ClientError as e:
        logging.error(
            f"btc_checker.py - get_transactions: Ошибка при запросе к Blockstream API: {e}"
        )
        return []
    except Exception as e:
        logging.error(
            f"btc_checker.py - get_transactions: Неизвестная ошибка при запросе к Blockstream API: {e}"
        )
        return []
    return transactions


async def _get_block_number_by_timestamp(timestamp):
    """Получает номер блока по времени через запрос к Blockstream API."""
    url = f'https://blockstream.info/api/blocks'
    try:
       async with aiohttp.ClientSession() as session:
           async with session.get(url, timeout=10) as response:
              response.raise_for_status()
              data = await response.json()
              if not data:
                    return None
              for block in data:
                    block_time = block.get('timestamp')
                    if block_time is None:
                        continue
                    block_datetime = datetime.fromtimestamp(block_time)

                    if block_datetime <= timestamp:
                       return block.get('height')
    except Exception as e:
        logging.error(
            f"eth_checker.py - get_block_number_by_timestamp: "
            f"Ошибка при запросе к API: {e}"
        )
        return None

async def check_payment(message: Message, bot: Bot, order: dict, last_hour: datetime):
    """Проверяет поступление оплаты и отправляет информацию о товаре."""
    payment_id = order.get("payment_id")
    amount_decimal = Decimal(str(order.get("crypto_amount"))) #  <------ Используем crypto_amount для проверки
    user_id = message.from_user.id
    order_id = order.get("id")

    logging.info(
        f"btc_checker.py - check_payment: "
        f"Начало проверки платежа {payment_id} для пользователя {user_id}, Order: {order}"
    )
    start_time = time.time()

    # Получаем адрес кошелька BTC из базы
    btc_wallet_address = get_wallet_address('BITCOIN')
    if not btc_wallet_address:
        logging.error(
            "btc_checker.py - check_payment: "
            "BITCOIN wallet address not found in database"
        )
        await bot.send_message(user_id, "Ошибка: Не удалось получить адрес кошелька для проверки оплаты. \n\n Error: Could not get wallet address for payment verification.")
        return

    try:
        while time.time() - start_time < 1800:
            try:
                # Проверка статуса платежа перед проверкой транзакций
                if shared_context.user_context and user_id in shared_context.user_context and shared_context.user_context[user_id].get("payment_status") == "completed":
                    logging.info(f"btc_checker.py - check_payment: Платеж {payment_id} уже обработан - выходим из цикла проверки")
                    return  # <---- Early return if payment already completed

                transactions = await get_transactions(
                    btc_wallet_address,
                    limit = 20,
                    start_timestamp=last_hour
                )
                logging.info(
                    f"btc_checker.py - check_payment: "
                    f"Получено транзакций: {len(transactions)}"
                )

                if not transactions:
                    logging.info(
                        "btc_checker.py - check_payment: Нет транзакций для проверки"
                    )
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                for tr in transactions:
                    # Фильтрация транзакций по времени
                    if tr.get('status') and tr['status'].get('block_time'):
                        block_time_str = tr['status'].get('block_time')
                        block_time = datetime.fromtimestamp(block_time_str)
                        if block_time > last_hour:
                            if await _process_transaction(
                                    tr, message, bot, order, amount_decimal, btc_wallet_address
                                ):
                                logging.info(f"btc_checker.py - check_payment: _process_transaction вернул True, выходим из check_payment") # <----- Логирование
                                return  # <---- Return from check_payment after successful processing

                    elif tr.get('status') is None:
                        if await _process_transaction(
                                    tr, message, bot, order, amount_decimal, btc_wallet_address
                                ):
                                logging.info(f"btc_checker.py - check_payment: _process_transaction вернул True, выходим из check_payment") # <----- Логирование
                                return # <---- Return from check_payment after successful processing

                await asyncio.sleep(CHECK_INTERVAL)

            except Exception as e:
                logging.error(
                    f"btc_checker.py - check_payment: "
                    f"Неизвестная ошибка в цикле проверки платежа: {e}"
                )
                await asyncio.sleep(CHECK_INTERVAL)

    except asyncio.CancelledError:
        logging.info(
            f"btc_checker.py - check_payment: "
            f"Проверка платежа {payment_id} была отменена."
        )


async def _get_product_data(product_name, order, user_id, bot):
    """
    Получает данные о продукте из базы данных.
    """
    log_id = uuid.uuid4() # <----- Логирование ID
    logging.info(
        f"{log_id} - btc_checker.py - _get_product_data: "
        f"Начинаем поиск категории и цены для продукта: {product_name}"
        )
    product_name_for_category = product_name.split(' ')[0]
    category_name = get_product_category(product_name_for_category)
    product_price = get_product_price(order.get("product_id"))
    if not category_name or product_price is None:
        logging.warning(
            f"{log_id} - btc_checker.py - _get_product_data: "
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
            f"{log_id} - btc_checker.py - _get_product_data: "
            f"Категория '{category_name}', цена  '{product_price}' для товара: {product_name}"
        )
    return category_name, product_price


async def _process_transaction(tr, message: Message, bot: Bot, order: dict, amount_decimal: Decimal, btc_wallet_address: str) -> bool:
    """Обрабатывает транзакцию, отправляет информацию о товаре и уведомление."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    order_id = order.get("id")
    product_name = order.get("product_name")
    log_id = uuid.uuid4() # <----- Логирование ID
    logging.info(
        f"{log_id} - btc_checker.py - _process_transaction: "
        f"Начинаем обработку транзакции {payment_id} для пользователя {user_id}. Hash: {tr.get('txid')}"
    )

    # Проверка статуса заказа перед обработкой, чтобы исключить повторную выдачу
    current_order_status = get_order_status(order_id) # <----- Получаем текущий статус заказа
    if current_order_status == "Выполнен": # <----- Проверяем статус
        logging.warning(f"{log_id} - btc_checker.py - _process_transaction: Заказ {order_id} уже выполнен, прерываем обработку.")
        return True # <----- Важно: Возвращаем True, чтобы остановить чекер, даже если заказ уже выполнен.

    tx_id = tr.get("txid")
    vout_list = tr.get("vout", [])
    if not vout_list:
        return False

    for vout in vout_list:
        value_satoshi = vout.get("value")
        scriptpubkey_address = vout.get("scriptpubkey_address")
        if value_satoshi is None or not scriptpubkey_address:
            continue

        try:
           amount_received_btc = Decimal(value_satoshi) / Decimal(100_000_000) # Convert satoshi to BTC
        except (ValueError, TypeError):
            continue
        if scriptpubkey_address == btc_wallet_address.lower():
          logging.info(f"{log_id} - btc_checker.py - _process_transaction: Проверка платежа {payment_id}: Сумма к оплате = {amount_decimal}, Получено {amount_received_btc}")
          if amount_received_btc == amount_decimal :
            logging.info(f"{log_id} - btc_checker.py - _process_transaction: Платеж на сумму {amount_received_btc} BTC подтвержден.")

            order["status"] = "Выполнен"

            if shared_context.user_context and user_id in shared_context.user_context:
                shared_context.user_context[user_id]["payment_status"] = "completed" # <---- Set payment_status to completed here
            else:
                logging.warning(f"{log_id} - btc_checker.py - _process_transaction: user_context not found for user_id: {user_id}")

           # Получаем данные товара
            product_data = await _get_product_data(product_name, order, user_id, bot)
            if not product_data:
                return True # Возвращаем True, чтобы остановить чекер, даже если не удалось получить данные о товаре - чтобы не было повторной выдачи

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
                    f"{log_id} - btc_checker.py - _process_transaction: Город или район не найден для товара '{product_name}'. Сообщение об ошибке отправлено"
                )
               return True # Возвращаем True, чтобы остановить чекер, даже если не удалось получить локацию - чтобы не было повторной выдачи

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
                    f"{log_id} - btc_checker.py - check_payment: Товар '{product_name}' не найден в paid_products"
                 )
                 return True # Возвращаем True, чтобы остановить чекер, даже если товар не найден - чтобы не было повторной выдачи

             # Выбираем любой товар из списка
            paid_product_data = paid_products[0]

            # Получаем id и имя таблицы
            paid_product_id = paid_product_data.get('id')
            table_name = paid_product_data.get('table_name')
            if not paid_product_id:
                logging.error(
                     f"{log_id} - btc_checker.py - _process_transaction: id товара не найден, хотя должен быть, проверьте структуру paid_products"
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
                return True # Возвращаем True, чтобы остановить чекер, даже если нет ID товара - чтобы не было повторной выдачи

            # Получаем текст инструкции и экранируем
            instruction_text =  paid_product_data.get('instruction') if paid_product_data.get("instruction") else "Нет инструкции / No instruction"
            escaped_instruction_text = re.sub(r'([`*_])', r'\\\1', instruction_text)

            # Формируем сообщения для пользователя
            user_text = (
                f"🎉 Спасибо за покупку!\n"
                f"💰 Оплаченная сумма: {amount_decimal} BTC\n"
                f"✅ Ваш заказ успешно оплачен криптовалютой (BITCOIN)\n\n"
                f"📍 Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                f"🗺️ Инструкции: <code>{escaped_instruction_text}</code>"
                 f"\n\nEnglish: 🎉 Thank you for your purchase!\n"
                f"💰 Paid amount: {amount_decimal} BTC\n"
                f"✅ Your order has been successfully paid with cryptocurrency (BITCOIN)\n\n"
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
                f"💵 Сумма: {order.get('amount')} USD\n" # <----- передаем amount а не crypto_amount
                 f"🔗 Адрес: {btc_wallet_address}\n\n"
                f"📍 Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                 f"🗺️ Инструкции: {instruction_text}"
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
                            logging.warning(f"{log_id} - btc_checker.py - _process_transaction: Файл {full_image_path} не найден")

            if media_group:
                try:
                    logging.info(f"{log_id} - btc_checker.py - _process_transaction: Отправка сообщения с медиа и текстом: {media_group}")
                    await bot.send_media_group(chat_id=user_id, media=media_group)
                    await bot.send_message(chat_id=user_id, text=user_text, parse_mode="HTML")
                    logging.info(f"{log_id} - btc_checker.py - _process_transaction: Сообщение с медиа и текстом отправлено успешно")
                except Exception as e:
                    logging.error(f"{log_id} - btc_checker.py - _process_transaction: Ошибка отправки медиа: {e}")
                    await bot.send_message(
                        chat_id=user_id,
                        text=user_text, parse_mode="HTML"
                    )
                    logging.info(f"{log_id} - btc_checker.py - _process_transaction: Сообщение об ошибке отправлено")
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=user_text, parse_mode="HTML"
                )
                logging.info(f"{log_id} - btc_checker.py - _process_transaction: Сообщение без медиа отправлено успешно")
            # Перемещаем товар в sold_products и удаляем из paid_products
            try:
                move_paid_product_to_sold_products(product_name, user_city, user_district, user_id, paid_product_id, table_name)
                logging.info(
                    f"{log_id} - btc_checker.py - _process_transaction: Товар '{product_name}' перемещен в sold_products"
                )
            except Exception as e:
                logging.error(
                    f"{log_id} - btc_checker.py - _process_transaction: Ошибка при перемещении товара в sold_products: {e}"
                )

            # Обновляем статус заказа на 'Выполнен'
            if update_order_status(order_id, "Выполнен"):
                logging.info(f"{log_id} - btc_checker.py - _process_transaction: Статус заказа {order_id} обновлен на 'Выполнен'")
            else:
                logging.error(f"{log_id} - btc_checker.py - _process_transaction: Ошибка при обновлении статуса заказа {order_id}")

            # Отправляем уведомление об успешной оплате
            try:
                await send_order_notification(
                    bot=bot,
                    user_id=user_id,
                    log_id=log_id,
                    username=username,
                    product_name=product_name,
                    category_name=category_name,
                    amount=order.get('amount'), #  <-----  Отправляем amount а не crypto_amount
                    order_id=order_id,
                    status="Выполнен",
                    payment_method="BITCOIN",
                    wallet_address=btc_wallet_address,
                     order_text=otstuk_text,
                    order_media=media_group
                )
            except Exception as e:
                logging.error(f"{log_id} - btc_checker.py - _process_transaction: Ошибка при отправке уведомления об оплате: {e}")


            # Начисляем реферальный бонус РЕФЕРЕРУ (если есть реферал)
            user_data = get_user(user_id)
            if user_data and user_data[2] is not None: # Проверяем, есть ли у пользователя реферер
                referrer_id = user_data[2]  # ID реферера
                bonus_amount = Decimal(str(product_price)) * Decimal("0.03")
                bonus_amount = round(bonus_amount, 2)

                add_referral_reward(referrer_id, bonus_amount) # Начисляем бонус рефереру

                referrer_data = get_user(referrer_id)
                if referrer_data:
                   new_referrer_balance = float(referrer_data[3]) + float(bonus_amount)
                   new_referrer_balance = float(round(new_referrer_balance, 2))

                   update_referral_purchases_amount(referrer_id, float(product_price))
                   # Добавляем запись в базу данных
                   update_referral_purchases_count_column(referrer_id, user_id, float(product_price)) # <----- Исправлено: Передаем amount

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
                           f"{log_id} - btc_checker.py - _process_transaction: Ошибка при отправке уведомления рефереру {referrer_id}: {e}"
                       )
                else:
                   logging.warning(
                        f"{log_id} - btc_checker.py - _process_transaction: Реферер с ID {referrer_id} не найден"
                   )
            logging.info(f"{log_id} - btc_checker.py - _process_transaction: Успешная обработка транзакции завершена, возвращаем True") # <----- Логирование
            return True # <---- Возвращаем True только при полном успехе обработки транзакции

    logging.info(f"{log_id} - btc_checker.py - _process_transaction: Транзакция не соответствует критериям, возвращаем False") # <----- Логирование
    return False # <---- Возвращаем False если транзакция не подходит или не обработана


def _payment_timeout_handler(message: Message, bot: Bot, order: dict):
    """Обрабатывает ситуацию, когда время ожидания оплаты истекло."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    logging.info(f"btc_checker.py - _payment_timeout_handler: Платеж {payment_id} не был получен в течение 30 минут.")
    # ИСПРАВЛЕНИЕ: Проверяем статус платежа перед обработкой таймаута.
    if shared_context.user_context and user_id in shared_context.user_context and shared_context.user_context[user_id].get("payment_status") == "completed":
       logging.info(f"btc_checker.py - _payment_timeout_handler: Пропускаем обработку таймаута для платежа {payment_id} - так как он уже оплачен")
       return
    order["status"] = "Отменен"

    if shared_context.user_context and user_id in shared_context.user_context:
        task = shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(
                f"btc_checker.py - _payment_timeout_handler: Асинхронная задача для платежа {payment_id} отменена."
            )
        shared_context.user_context[user_id]["payment_status"] = "failed"
        shared_context.user_context[user_id] = {}
        logging.info(
            f"btc_checker.py - _payment_timeout_handler: Оплата не прошла. Контекст пользователя {user_id} очищен."
        )
    else:
        logging.warning(
            f"btc_checker.py - _payment_timeout_handler: user_context not found for user_id: {user_id}"
        )
    asyncio.create_task(bot.send_message(
        chat_id=user_id,
        text="Время ожидания оплаты истекло. Ваш заказ отменён. \n\n English: Payment timeout. Your order has been canceled."
    ))

def start_btc_payment_check(message: Message, bot: Bot, order: dict):
    """Запускает процесс проверки платежа."""
    payment_id = order.get("payment_id")
    amount = Decimal(str(order.get("amount"))) # Decimal
    user_id = message.from_user.id
    logging.info(f"start_btc_payment_check: User {user_id}, Payment ID: {payment_id}, Amount: {amount}")

    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_status"] = "pending"
    else:
        logging.warning(f"start_btc_payment_check: user_context not found for user_id: {user_id}")

    now = datetime.now()
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
        logging.info(f"btc_checker.py - _check_payment_task: Проверка платежа {order.get('payment_id')} отменена.")
    except Exception as e:
         logging.error(
                    f"btc_checker.py - _check_payment_task: Неизвестная ошибка в _check_payment_task: {e}"
                )
    finally:
        if shared_context.user_context and message.from_user.id in shared_context.user_context:
          task = shared_context.user_context[message.from_user.id].get("payment_task")
          if task:
            task.cancel()
            logging.info(
              f"btc_checker.py - _check_payment_task: Асинхронная задача для платежа {order.get('payment_id')} отменена."
          )
          shared_context.user_context[message.from_user.id].pop("payment_task", None) # удаляем таск из контекста
          logging.info(
            f"btc_checker.py - _check_payment_task: payment_task удалена из контекста пользователя {message.from_user.id}."
        )