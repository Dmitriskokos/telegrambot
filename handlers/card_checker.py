import logging
import asyncio
import random
import time
import os
from decimal import Decimal
import uuid
from aiogram import Bot, types
from aiogram.types import Message, InputMediaPhoto, FSInputFile
from handlers import shared_context
from datetime import datetime, timedelta
from database import (
    get_user,
    get_wallet_address,
    set_user_balance,
    update_referral_purchases_amount,
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
import re
from keyboards import main_menu_keyboard

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log',
    filemode='a'
)

CHECK_INTERVAL = 30  # Интервал проверки в секундах

async def check_payment(message: Message, bot: Bot, order: dict, last_hour: datetime):
    """Имитация проверки оплаты картой."""
    payment_id = order.get("payment_id")
    amount_decimal = Decimal(str(order.get("amount")))
    user_id = message.from_user.id
    order_id = order.get("id")
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - card_checker.py - check_payment: Начало проверки платежа {payment_id} для пользователя {user_id}, Order: {order}")
    start_time = time.time()

    try:
        while time.time() - start_time < 1800:  # Проверка в течение 30 минут
            try:
                if shared_context.user_context and user_id in shared_context.user_context and shared_context.user_context[user_id].get("payment_status") == "completed":
                    logging.info(f"{log_id} - card_checker.py - check_payment: Платеж {payment_id} уже обработан - выходим из цикла проверки")
                    return

                # Имитация проверки, что оплата прошла (заглушка)
                # В реальном коде тут была бы проверка через API платежной системы
                await asyncio.sleep(CHECK_INTERVAL)  # Ожидание перед следующей попыткой проверки
                if random.random() < 0.5:  # 50% шанс, что "оплата прошла" для демонстрации
                    await _process_successful_payment(message, bot, order, amount_decimal, log_id)
                    return
            except Exception as e:
                logging.error(
                    f"{log_id} - card_checker.py - check_payment: Неизвестная ошибка в цикле проверки платежа: {e}"
                )
                await asyncio.sleep(CHECK_INTERVAL)

    except asyncio.CancelledError:
        logging.info(f"{log_id} - card_checker.py - check_payment: Проверка платежа {payment_id} была отменена.")
    finally:
           _payment_timeout_handler(message, bot, order, log_id)


async def _get_product_data(product_name, order, user_id, bot, log_id):
    """
    Получает данные о продукте из базы данных.
    """
    logging.info(
        f"{log_id} - card_checker.py - _get_product_data: "
        f"Начинаем поиск категории и цены для продукта: {product_name}"
    )
    product_name_for_category = product_name.split(' ')[0]
    category_name = get_product_category(product_name_for_category)
    product_price = get_product_price(order.get("product_id"))
    if not category_name or product_price is None:
        logging.warning(
            f"{log_id} - card_checker.py - _get_product_data: "
            f"Категория или цена товара не найдены для product: {product_name}"
        )
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ Оплата подтверждена! Заказ №{order.get('id')}\n\n"
                f"Товар: {product_name}\n\n"
                f"Инструкция: Не удалось получить данные о товаре. Свяжитесь с администратором."
                f"\n\nEnglish: Payment confirmed! Order №{order.get('id')}\n\n"
                f"Product: {product_name}\n\n"
                f"Instruction: Could not get product data. Contact admin."

            ),
        )
        return None
    logging.info(
        f"{log_id} - card_checker.py - _get_product_data: "
        f"Категория '{category_name}', цена  '{product_price}' для товара: {product_name}"
    )
    return category_name, product_price


async def _process_successful_payment(message: Message, bot: Bot, order: dict, amount_decimal: Decimal, log_id: uuid.UUID):
    """Обрабатывает успешную оплату картой."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    order_id = order.get("id")
    product_name = order.get("product_name")
    logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Платеж {payment_id} от пользователя {user_id} подтвержден.")

    order["status"] = "Выполнен"

    if shared_context.user_context and user_id in shared_context.user_context:
         shared_context.user_context[user_id]["payment_status"] = "completed"
    else:
        logging.warning(f"{log_id} - card_checker.py - _process_successful_payment: user_context not found for user_id: {user_id}")

    # Получаем данные товара
    product_data = await _get_product_data(product_name, order, user_id, bot, log_id)
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
        )
         await bot.send_message(
            chat_id=user_id,
            text=user_error_text, parse_mode='HTML'
        )
         logging.info(
            f"{log_id} - card_checker.py - _process_successful_payment: Город или район не найден для товара '{product_name}'. Сообщение об ошибке отправлено"
        )
         return True

    # Ищем товар в paid_products
    paid_products = get_location_info_from_paid_products(product_name, user_city, user_district)
    if not paid_products:
          user_error_text = (
            f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
            f"📦 Товар: {product_name}\n\n"
            f"⚠️ Инструкция: Товар не найден в базе. Свяжитесь с администратором."
        )
          await bot.send_message(
            chat_id=user_id,
            text=user_error_text, parse_mode='HTML'
        )
          logging.info(
            f"{log_id} - card_checker.py - _process_successful_payment: Товар '{product_name}' не найден в paid_products"
        )
          return True

    # Выбираем любой товар из списка
    paid_product_data = paid_products[0]

     # Получаем id и имя таблицы
    paid_product_id = paid_product_data.get('id')
    table_name = paid_product_data.get('table_name')
    if not paid_product_id:
        logging.error(
            f"{log_id} - card_checker.py - _process_successful_payment: id товара не найден, хотя должен быть, проверьте структуру paid_products"
        )
        user_error_text = (
            f"✅ Оплата подтверждена! Заказ №{order_id}\n\n"
            f"📦 Товар: {product_name}\n\n"
            f"⚠️ Инструкция: id товара не найден, свяжитесь с админом."
        )
        await bot.send_message(
            chat_id=user_id,
            text=user_error_text, parse_mode='HTML'
        )
        return True

    # Получаем текст инструкции и экранируем
    instruction_text = paid_product_data.get('instruction') if paid_product_data.get("instruction") else "Нет инструкции / No instruction"
    escaped_instruction_text = re.sub(r'([`*_])', r'\\\1', instruction_text) # Экранируем

    # Формируем сообщения для пользователя
    user_text = (
        f"🎉 Спасибо за покупку!\n"
        f"💰 Оплаченная сумма: {amount_decimal}\n"
        f"✅ Ваш заказ успешно оплачен картой.\n\n"
        f"📍 Локация: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
        f"🗺️ Инструкции: <code>{escaped_instruction_text}</code>"
        f"\n\nEnglish: 🎉 Thank you for your purchase!\n"
        f"💰 Paid amount: {amount_decimal}\n"
        f"✅ Your order has been successfully paid with card.\n\n"
        f"📍 Location: {paid_product_data.get('city')}, {paid_product_data.get('district')}\n"
        f"🗺️ Instructions: <code>{escaped_instruction_text}</code>"
    )

      # Формируем сообщение для отстука
    user_obj = await bot.get_chat(user_id)
    username = user_obj.username if user_obj.username else 'нет юзернейма'
    usdt_trc20_wallet = get_wallet_address('USDT_TRC20')
    otstuk_text = (
            f"💰 Успешная оплата!\n"
            f"👤 Покупатель: @{username} (ID: {user_id})\n"
            f"📦 Товар: {product_name}\n"
            f"💵 Сумма: {amount_decimal} USD\n"
            f"🔗 Адрес: {usdt_trc20_wallet if usdt_trc20_wallet else 'Неизвестно'}\n\n"
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
                    logging.warning(f"{log_id} - card_checker.py - _process_successful_payment: Файл {full_image_path} не найден / File {full_image_path} not found")
    
    if media_group:
         try:
            logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Отправка сообщения с медиа и текстом: {media_group}")
            await bot.send_media_group(chat_id=user_id, media=media_group)
            await bot.send_message(chat_id=user_id, text=user_text, parse_mode="HTML")
            logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Сообщение с медиа и текстом отправлено успешно / Message with media and text sent successfully")
         except Exception as e:
                logging.error(f"{log_id} - card_checker.py - _process_successful_payment: Ошибка отправки медиа: {e}")
                await bot.send_message(
                    chat_id=user_id,
                    text=user_text, parse_mode="HTML"
                )
                logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Сообщение об ошибке отправлено / Error message sent")
    else:
         await bot.send_message(
            chat_id=user_id,
            text=user_text, parse_mode="HTML"
        )
         logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Сообщение без медиа отправлено успешно / Message without media sent successfully")

    # Перемещаем товар в sold_products и удаляем из paid_products
    try:
        move_paid_product_to_sold_products(product_name, user_city, user_district, user_id, paid_product_id, table_name)
        logging.info(
             f"{log_id} - card_checker.py - _process_successful_payment: Товар '{product_name}' перемещен в sold_products / Product '{product_name}' moved to sold_products"
        )
    except Exception as e:
        logging.error(
            f"{log_id} - card_checker.py - _process_successful_payment: Ошибка при перемещении товара в sold_products: {e}"
        )

     # Обновляем статус заказа на 'Выполнен'
    if update_order_status(order_id, "Выполнен"):
         logging.info(f"{log_id} - card_checker.py - _process_successful_payment: Статус заказа {order_id} обновлен на 'Выполнен' / Status of order {order_id} updated to 'Completed'")
    else:
        logging.error(f"{log_id} - card_checker.py - _process_successful_payment: Ошибка при обновлении статуса заказа {order_id} / Error updating order status {order_id}")

    # Отправляем уведомление об успешной оплате
    try:
            await send_order_notification(
                bot=bot,
                user_id=user_id,
                log_id=log_id,
                username=username,
                product_name=product_name,
                category_name=category_name,
                amount=amount_decimal,
                order_id=order_id,
                status="Выполнен",
                payment_method="CARD",
                wallet_address="Карта",
                order_text=otstuk_text,
                order_media=media_group
            )
    except Exception as e:
            logging.error(f"{log_id} - card_checker.py - _process_successful_payment: Ошибка при отправке уведомления об оплате: {e}")

    # Начисляем реферальный бонус РЕФЕРЕРУ (если есть реферал)
    user_data = get_user(user_id)
    if user_data and user_data[2] is not None:  # Проверяем, есть ли у пользователя реферер
            referrer_id = user_data[2]  # ID реферера
            bonus_amount = amount_decimal * Decimal("0.03")
            bonus_amount = round(bonus_amount, 2)

            add_referral_reward(referrer_id, bonus_amount)  # Начисляем бонус рефереру

            referrer_data = get_user(referrer_id)
            if referrer_data:
                new_referrer_balance = float(referrer_data[3]) + float(bonus_amount)
                new_referrer_balance = float(round(new_referrer_balance, 2))
                update_referral_purchases_amount(referrer_id, float(amount_decimal))
                # Добавляем запись в базу данных
                update_referral_purchases_count_column(referrer_id, user_id, float(amount_decimal))
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
                        f"{log_id} - card_checker.py - _process_successful_payment: Ошибка при отправке уведомления рефереру {referrer_id}: {e}"
                    )
            else:
                logging.warning(
                    f"{log_id} - card_checker.py - _process_successful_payment: Реферер с ID {referrer_id} не найден / Referrer with ID {referrer_id} not found"
                )


def _payment_timeout_handler(message: Message, bot: Bot, order: dict, log_id):
    """Обрабатывает ситуацию, когда время ожидания оплаты истекло."""
    payment_id = order.get("payment_id")
    user_id = message.from_user.id
    logging.info(f"{log_id} - card_checker.py - _payment_timeout_handler: Платеж {payment_id} не был получен в течение 30 минут.")
    # ИСПРАВЛЕНИЕ: Проверяем статус платежа перед обработкой таймаута.
    if shared_context.user_context and user_id in shared_context.user_context and shared_context.user_context[user_id].get("payment_status") == "completed":
        logging.info(f"{log_id} - card_checker.py - _payment_timeout_handler: Пропускаем обработку таймаута для платежа {payment_id} - так как он уже оплачен")
        return

    order["status"] = "Отменен"
    if shared_context.user_context and user_id in shared_context.user_context:
        task = shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(
                 f"{log_id} - card_checker.py - _payment_timeout_handler: Асинхронная задача для платежа {payment_id} отменена."
            )
        shared_context.user_context[user_id]["payment_status"] = "failed"
        shared_context.user_context[user_id] = {}
        logging.info(
            f"{log_id} - card_checker.py - _payment_timeout_handler: Оплата не прошла. Контекст пользователя {user_id} очищен."
        )
    else:
        logging.warning(
            f"{log_id} - card_checker.py - _payment_timeout_handler: user_context not found for user_id: {user_id}"
        )
    asyncio.create_task(bot.send_message(
        chat_id=user_id,
        text="Время ожидания оплаты истекло. Ваш заказ отменён. / Payment timeout. Your order has been canceled."
    ))



def start_payment_check(message: Message, bot: Bot, order: dict):
    """Запускает процесс проверки платежа."""
    payment_id = order.get("payment_id")
    amount = Decimal(str(order.get("amount")))  # Decimal
    user_id = message.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - card_checker.py - start_payment_check: User {user_id}, Payment ID: {payment_id}, Amount: {amount}")

    if shared_context.user_context and user_id in shared_context.user_context:
        # Отменяем предыдущую задачу, если она есть
        task = shared_context.user_context[user_id].get("payment_task")
        if task:
            task.cancel()
            logging.info(f"{log_id} - card_checker.py - start_payment_check: Отменили предыдущий payment_task для user {user_id}")
        shared_context.user_context[user_id]["payment_status"] = "pending"
    else:
        logging.warning(f"{log_id} - card_checker.py - start_payment_check: user_context not found for user_id: {user_id}")

    now = datetime.now()
    last_checked_time = now - timedelta(hours=1)
    task = asyncio.create_task(_check_payment_task(message, bot, order, last_checked_time, log_id))
    
    if shared_context.user_context and user_id in shared_context.user_context:
        shared_context.user_context[user_id]["payment_task"] = task

    # Immediate return to the main menu
    asyncio.create_task(bot.send_message(message.chat.id, "Ожидаю подтверждения оплаты... \n\n Waiting for payment confirmation...", reply_markup=main_menu_keyboard()))
    return task


async def _check_payment_task(message: Message, bot: Bot, order: dict, last_hour: datetime, log_id: uuid.UUID):
    """Обертка для проверки платежа с отменой таска."""
    try:
        await check_payment(message, bot, order, last_hour)
    except asyncio.CancelledError:
        logging.info(f"{log_id} - card_checker.py - _check_payment_task: Проверка платежа {order.get('payment_id')} отменена.")
    except Exception as e:
        logging.error(
            f"{log_id} - card_checker.py - _check_payment_task: Неизвестная ошибка в _check_payment_task: {e}"
        )
    finally:
        if shared_context.user_context and message.from_user.id in shared_context.user_context:
            task = shared_context.user_context[message.from_user.id].get("payment_task")
            if task:
                task.cancel()
                logging.info(
                    f"{log_id} - card_checker.py - _check_payment_task: Асинхронная задача для платежа {order.get('payment_id')} отменена."
                )
            shared_context.user_context[message.from_user.id].pop("payment_task", None)
            logging.info(
                f"{log_id} - card_checker.py - _check_payment_task: payment_task удалена из контекста пользователя {message.from_user.id}."
            )