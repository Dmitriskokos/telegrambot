import json
import logging
import time
import asyncio
from decimal import Decimal
import os
from aiogram import Bot, types
from aiogram.types import Message, InputMediaPhoto, FSInputFile
from handlers import shared_context
from datetime import datetime, timedelta
import aiohttp
import sys
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
)
import pytz  # импортируем pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log',
    filemode='a',
)

INITIAL_CHECK_INTERVAL = 60  # Начальный интервал проверки в секундах
MAX_CHECK_INTERVAL = 300  # Максимальный интервал проверки в секундах
PAYMENT_TIMEOUT = 1800  # 30 минут таймаут
MIN_CONFIRMATIONS = 3

async def get_transactions(litecoin_wallet_address, last_hour):
    """Получает все транзакции для указанного адреса через Blockcypher API."""
    blockcypher_url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{litecoin_wallet_address}"
    headers = {"accept": "application/json"}
    transactions = []
    logging.info(
        f"ltc_checker.py - get_transactions: Запрос транзакций через Blockcypher API для адреса: {litecoin_wallet_address}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(blockcypher_url, headers=headers, timeout=10)
            response.raise_for_status()
            response_json = await response.json()
            all_transactions = response_json.get('txrefs', [])
            logging.info(
                f"ltc_checker.py - get_transactions: Получено всего транзакций с Blockcypher API: {len(all_transactions)}"
            )
            filtered_transactions = []
            for tr in all_transactions:
                logging.info(f"ltc_checker.py - get_transactions: Обработка транзакции: {tr}")
                try:
                    received_time_str = tr.get('confirmed')
                    if not received_time_str:
                        logging.warning(
                            f"ltc_checker.py - get_transactions: Время подтверждения не найдено, транзакция пропущена transaction: {tr}"
                        )
                        continue
                    received_time = datetime.strptime(received_time_str, '%Y-%m-%dT%H:%M:%SZ')
                    if received_time >= last_hour:
                        filtered_transactions.append(tr)
                        logging.info(
                            f"ltc_checker.py - get_transactions: Транзакция добавлена после фильтрации по времени: {tr}"
                        )
                    else:
                        logging.info(
                            f"ltc_checker.py - get_transactions: Транзакция отфильтрована по времени: {tr}, received_time: {received_time}, last_hour: {last_hour}"
                        )
                except (ValueError, TypeError, AttributeError) as e:
                    logging.error(
                        f"ltc_checker.py - get_transactions: Ошибка при конвертации времени транзакции: {e}, transaction: {tr}"
                    )
                    continue
            logging.info(
                f"ltc_checker.py - get_transactions: Получено транзакций для проверки: {len(filtered_transactions)}"
            )
            return filtered_transactions

    except aiohttp.ClientError as e:
        logging.error(f"ltc_checker.py - get_transactions: Ошибка при запросе к Blockcypher API: {e}")
        return None  # Возвращаем None в случае ошибки

async def check_payment(message: Message, bot: Bot, order: dict, ltc_amount: Decimal, last_hour: datetime):
    """Проверяет поступление оплаты и отправляет информацию о товаре."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    order_id = order.get("id")
    product_name = order.get("product_name")

    logging.info(
        f"ltc_checker.py - check_payment: Начало проверки платежа {payment_id} для пользователя {user_id}, Ожидаемая сумма LTC: {ltc_amount}"
    )
    start_time = time.time()

    litecoin_wallet_address = get_wallet_address("LITECOIN")
    if not litecoin_wallet_address:
        logging.error("ltc_checker.py - check_payment: Не удалось загрузить адрес LITECOIN из базы данных.")
        await bot.send_message(
            chat_id=user_id, text="Ошибка: Не удалось получить адрес кошелька для проверки оплаты."
        )
        return
    logging.info(f"ltc_checker.py - check_payment: Адрес кошелька для проверки: {litecoin_wallet_address}")
    while time.time() - start_time < PAYMENT_TIMEOUT:
        transactions = await get_transactions(litecoin_wallet_address, last_hour)

        if transactions is None:
            await asyncio.sleep(INITIAL_CHECK_INTERVAL)
            continue

        logging.info(f"ltc_checker.py - check_payment: Получено транзакций с API для проверки: {len(transactions)}")

        for tr in transactions:
            try:
                if await _process_transaction(tr, message, bot, order, ltc_amount, litecoin_wallet_address):
                    return
            except Exception as e:
                logging.error(f"ltc_checker.py - check_payment: Ошибка при обработке транзакции: {e}, transaction: {tr}")
        await asyncio.sleep(INITIAL_CHECK_INTERVAL)  # Ждем перед следующей проверкой
    # Если цикл завершился, значит таймаут
    _payment_timeout_handler(message, bot, order)

async def _process_transaction(
    tr, message: Message, bot: Bot, order: dict, ltc_amount: Decimal, litecoin_wallet_address: str
) -> bool:
    """Обрабатывает транзакцию и отправляет информацию о товаре."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    order_id = order.get("id")
    product_name = order.get("product_name")

    try:
        confirmed_time_str = tr.get('confirmed')
        if confirmed_time_str:  # проверяем, что confirmed_time_str не пуст.
            confirmed_time = datetime.strptime(confirmed_time_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
            # Конвертация UTC в локальную временную зону
            utc_timezone = pytz.utc
            local_timezone = pytz.timezone(time.tzname[0])  # Получаем локальную временную зону
            confirmed_time = utc_timezone.localize(confirmed_time).astimezone(local_timezone)
        else:
            logging.warning(
                f"ltc_checker.py - _process_transaction: Время подтверждения транзакции  не найдено, transaction: {tr}"
            )
            return False

    except (ValueError, TypeError, AttributeError) as e:
        logging.error(
            f"ltc_checker.py - _process_transaction: Ошибка при конвертации времени транзакции: {e}, transaction: {tr}"
        )
        return False

    confirmations = tr.get('confirmations', 0)

    if confirmations < MIN_CONFIRMATIONS:
        logging.info(
            f"ltc_checker.py - _process_transaction: Транзакция {tr.get('tx_hash')} пропущена, так как у нее недостаточно подтверждений ({confirmations}) < {MIN_CONFIRMATIONS} "
        )
        return False

    vout = tr.get("outputs", [])
    if not vout:
        logging.info(f"ltc_checker.py - _process_transaction: Пропущена транзакция , нет vout")
        return False

    for v in vout:
        value = v.get("value")
        scriptpubkey_address = v.get("addresses")
        if value is None or not scriptpubkey_address:
            logging.warning(
                f"ltc_checker.py - _process_transaction: Пропущена транзакция, Не хватает данных: value или scriptpubkey_address"
            )
            return False
        try:
            amount_received_ltc = Decimal(value) / Decimal(100000000)
        except (ValueError, TypeError) as e:
            logging.error(f"ltc_checker.py - _process_transaction: Ошибка при конвертации value: {e}, transaction: {tr}")
            return False
        logging.info(
            f"ltc_checker.py - _process_transaction: Проверка платежа {payment_id}: "
            f"Сумма к оплате = {ltc_amount} LTC, "
            f"Получено {amount_received_ltc} LTC, "
            f"адрес получателя {scriptpubkey_address[0] if scriptpubkey_address else None}, "
            f"наш адрес {litecoin_wallet_address}"
        )
        if (
            amount_received_ltc == ltc_amount
            and scriptpubkey_address[0] == litecoin_wallet_address
        ):
            logging.info(f"ltc_checker.py - _process_transaction: Платеж на сумму {amount_received_ltc} LTC подтвержден.")
            order["status"] = "Выполнен"
            # ... остальной код обработки платежа остается без изменений ...
            if shared_context.user_context and user_id in shared_context.user_context:
                shared_context.user_context[user_id]["payment_status"] = "completed"
            else:
                logging.warning(f"ltc_checker.py - _process_transaction: user_context not found for user_id: {user_id}")

            # Получаем данные товара
            category_name = get_product_category(product_name)
            product_price = get_product_price(order.get("product_id"))
            if not category_name or product_price is None:
                logging.warning(
                    f"ltc_checker.py - _process_transaction: Категория или цена товара не найдены для product: {product_name}"
                )
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"Товар: {product_name}\n\n"
                        f"Инструкция: Не удалось получить данные о товаре. Свяжитесь с администратором."
                    ),
                )
                return True

            user_city = order.get("city")
            user_district = order.get("district")

            if not user_city or not user_district:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"Товар: {product_name}\n\n"
                        f"Инструкция: Не удалось получить локацию. Свяжитесь с администратором."
                    ),
                    parse_mode="Markdown",
                )
                logging.info(
                    f"ltc_checker.py - _process_transaction: Город или район не найден для товара '{product_name}'. Сообщение об ошибке отправлено"
                )
                return True

            # Ищем товар в paid_products
            paid_product_data = get_location_info_from_paid_products(product_name, user_city, user_district)
            if not paid_product_data:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                        f"Товар: {product_name}\n\n"
                        f"Инструкция: Товар не найден в базе. Свяжитесь с администратором."
                    ),
                    parse_mode="Markdown",
                )
                logging.info(
                    f"ltc_checker.py - _process_transaction: Товар '{product_name}' не найден в paid_products"
                )
                return True

            # Формируем сообщение и отправляем
            text = (
                f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
                f"Товар: {product_name}\n\n"
                f"Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
                f"Инструкции: `{paid_product_data.get('instruction')}`"
            )
            media_group = []
            if paid_product_data.get('images') and isinstance(paid_product_data.get('images'), str):
                images = json.loads(paid_product_data.get('images'))
                for image_path in images:
                    full_image_path = os.path.join(
                        os.path.dirname(__file__),
                        "..",
                        image_path.lstrip("\\/"),
                    )
                    if os.path.exists(full_image_path):
                        media_group.append(InputMediaPhoto(media=FSInputFile(full_image_path)))
                    else:
                        logging.warning(
                            f"ltc_checker.py - _process_transaction: Файл {full_image_path} не найден"
                        )

            if media_group:
                try:
                    await bot.send_media_group(chat_id=user_id, media=media_group)
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logging.error(f"ltc_checker.py - _process_transaction: Ошибка отправки медиа: {e}")
                    await bot.send_message(
                        chat_id=user_id,
                        text=text,
                        parse_mode="Markdown",
                    )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown",
                )

            # Перемещаем товар в sold_products и удаляем из paid_products
            try:
                move_paid_product_to_sold_products(paid_product_data, user_id)
                logging.info(
                    f"ltc_checker.py - _process_transaction: Товар '{product_name}' перемещен в sold_products"
                )
            except Exception as e:
                logging.error(
                    f"ltc_checker.py - _process_transaction: Ошибка при перемещении товара в sold_products: {e}"
                )

            # Обновляем баланс пользователя и реферера
            try:
                set_user_balance(user_id, float(product_price))
                logging.info(
                    f"ltc_checker.py - _process_transaction: Пользователю {user_id} обновлен баланс + {product_price}"
                )
            except Exception as e:
                logging.error(
                    f"ltc_checker.py - _process_transaction: Ошибка при обновлении баланса пользователя {user_id}: {e}"
                )

            user_data = get_user(user_id)
            if user_data and user_data[2] is not None:
                referrer_id = user_data[2]

                add_referral_reward(referrer_id, product_price)  # Вызов add_referral_reward

                bonus_amount = Decimal(str(product_price)) * Decimal("0.03")
                bonus_amount = round(bonus_amount, 2)
                referrer_data = get_user(referrer_id)
                if referrer_data:
                    new_referrer_balance = float(referrer_data[3]) + float(bonus_amount)
                    new_referrer_balance = float(round(new_referrer_balance, 2))
                    update_referral_purchases_amount(referrer_id, float(product_price))
                    try:
                        await bot.send_message(
                            chat_id=referrer_id,
                            text=(
                                f"🎉 Ваш реферал совершил покупку!\n\n"
                                f"💰 Вы получили бонус в размере {bonus_amount:.2f} USD.\n"
                                f"💰 Ваш текущий баланс: {new_referrer_balance:.2f} USD."
                            ),
                        )
                    except Exception as e:
                        logging.error(
                            f"ltc_checker.py - _process_transaction: Ошибка при отправке уведомления рефереру {referrer_id}: {e}"
                        )
                else:
                    logging.warning(f"ltc_checker.py - _process_transaction: Реферер с ID {referrer_id} не найден")

            # Очищаем контекст пользователя
            if shared_context.user_context and user_id in shared_context.user_context:
                task = shared_context.user_context[user_id].get("payment_task")
                if task:
                    task.cancel()
                    logging.info(
                        f"ltc_checker.py - _process_transaction: Асинхронная задача для платежа {payment_id} отменена."
                    )
                shared_context.user_context[user_id] = {}
                logging.info(f"ltc_checker.py - _process_transaction: Контекст пользователя {user_id} очищен.")
            return True
    return False

def _payment_timeout_handler(message: Message, bot: Bot, order: dict):
    """Обрабатывает ситуацию, когда время ожидания оплаты истекло."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    logging.info(f"ltc_checker.py - _payment_timeout_handler: Платеж {payment_id} не был получен в течение 30 минут.")
    order["status"] = "Отменен"

    if shared_context.user_context and user_id in shared_context.user_context:
        task = shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(
                f"ltc_checker.py - _payment_timeout_handler: Асинхронная задача для платежа {payment_id} отменена."
            )
        shared_context.user_context[user_id]["payment_status"] = "failed"
        shared_context.user_context[user_id] = {}
        logging.info(
            f"ltc_checker.py - _payment_timeout_handler: Оплата не прошла. Контекст пользователя {user_id} очищен."
        )
    else:
        logging.warning(
            f"ltc_checker.py - _payment_timeout_handler: user_context not found for user_id: {user_id}"
        )
    asyncio.create_task(bot.send_message(
        chat_id=user_id,
        text="Время ожидания оплаты истекло. Ваш заказ отменён."
    ))

def start_ltc_payment_check(message: Message, bot: Bot, order: dict, ltc_amount):
    """Запускает процесс проверки платежа."""
    payment_id = order.get("payment_id")
    amount = Decimal(str(order.get("amount")))  # Decimal
    user_id = message.from_user.id
    logging.info(
        f"ltc_checker.py - start_ltc_payment_check: Начинаем проверку платежа. "
        f"User ID: {user_id}, Payment ID: {payment_id}, Сумма в USD: {amount}, Сумма в LTC: {ltc_amount}"
    )
    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_status"] = "pending"
    else:
        logging.warning(
            f"ltc_checker.py - start_ltc_payment_check: user_context not found for user_id: {user_id}"
        )

    now = datetime.now()
    last_hour = now - timedelta(hours=1)
    task = asyncio.create_task(_check_payment_task(message, bot, order, ltc_amount, last_hour))
    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_task"] = task

async def _check_payment_task(message: Message, bot: Bot, order: dict, ltc_amount: Decimal, last_hour: datetime):
    """Обертка для проверки платежа с отменой таска."""
    try:
        await check_payment(message, bot, order, ltc_amount, last_hour)
    except Exception as e:
        logging.error(
            f"ltc_checker.py - _check_payment_task: Неизвестная ошибка в _check_payment_task: {e}"
        )
        # добавим задержку и повторную попытку
        await asyncio.sleep(10)
        await _check_payment_task(message, bot, order, ltc_amount, last_hour)
    finally:
        if shared_context.user_context and message.from_user.id in shared_context.user_context:
            task = shared_context.user_context[message.from_user.id].get("payment_task")
            if task:
                task.cancel()
                logging.info(
                    f"ltc_checker.py - _check_payment_task: Асинхронная задача для платежа {order.get('payment_id')} отменена."
                )
            shared_context.user_context[message.from_user.id].pop("payment_task", None)  # удаляем таск из контекста
            logging.info(
                f"ltc_checker.py - _check_payment_task: payment_task удалена из контекста пользователя {message.from_user.id}."
            )