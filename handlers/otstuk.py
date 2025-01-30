import asyncio
import logging
from aiogram import Bot, types
import os
from decimal import Decimal
from aiogram.exceptions import TelegramForbiddenError, TelegramAPIError
from aiogram.utils.chat_action import ChatActionSender
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

async def send_order_notification(bot: Bot, user_id: int, log_id: str, product_name: str, category_name: str, amount: Decimal, order_id: str, status: str, payment_method: str, crypto_amount=None, wallet_address=None, username=None, order_text=None, order_media=None):
    """Отправляет уведомление об успешной оплате в телеграм-группу."""
    group_chat_id = os.getenv('GROUP_ID')
    if not group_chat_id:
        logging.error(f"{log_id} - otstuk.py - send_order_notification: GROUP_ID не установлен в переменных окружения.")
        return
    try:
        group_chat_id = int(group_chat_id) # Попробуем конвертировать ID в int для избежания ошибок
    except ValueError:
         logging.error(f"{log_id} - otstuk.py - send_order_notification: Некорректный GROUP_ID, должен быть целым числом. ID группы: {group_chat_id}")
         return

    if status != "Выполнен":
        logging.info(f"{log_id} - otstuk.py - send_order_notification: Уведомление не отправлено, статус заказа: {status}")
        return

    try:
        if not username:
            username = f"ID: {user_id}"
            logging.warning(
                f"{log_id} - otstuk.py - send_order_notification: имя пользователя не передано, используется ID {user_id}"
            )
        else:
            username = f"@{username}"

        try:
            chat = await bot.get_chat(group_chat_id)
            if not chat:
                logging.error(f"{log_id} - otstuk.py - send_order_notification: Бот не может получить информацию о группе. Проверьте ID группы. group_chat_id: {group_chat_id}")
                return
            async with ChatActionSender(bot=bot, chat_id=group_chat_id, action="typing"):
                if order_text:
                    if order_media:
                        # If media is present, send as media group
                        try:
                            # Отправляем сообщение с текстом, а затем медиа группу
                           
                            await bot.send_message(chat_id=group_chat_id, text=order_text, parse_mode='HTML')
                            await bot.send_media_group(chat_id=group_chat_id, media=order_media)


                        except Exception as e:
                              logging.error(
                            f"{log_id} - otstuk.py - send_order_notification: Outer Exception during sending media group {e} ,group_chat_id:{group_chat_id}"
                        )
                    else:
                         await bot.send_message(chat_id=group_chat_id, text=order_text, parse_mode='HTML')
                else:
                    logging.warning(f"{log_id} - otstuk.py - send_order_notification: order_text is None.")
                    return

            logging.info(f"{log_id} - otstuk.py - send_order_notification: Уведомление об оплате {order_id} отправлено в группу.")
        except TelegramForbiddenError:
                logging.error(f"{log_id} - otstuk.py - send_order_notification: Бот заблокирован в группе. Дайте боту права на отправку сообщений. group_chat_id:{group_chat_id}")
        except TelegramAPIError as e:
                logging.error(f"{log_id} - otstuk.py - send_order_notification: Ошибка отправки уведомления в группу: {e}, text:{order_text}, group_chat_id:{group_chat_id}")
        except Exception as e:
             logging.error(f"{log_id} - otstuk.py - send_order_notification: Outer Exception {e} ,group_chat_id:{group_chat_id}")
    except Exception as e:
         logging.error(f"{log_id} - otstuk.py - send_order_notification: Outter try exception: {e}")