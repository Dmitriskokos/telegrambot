import uuid
from aiogram import Dispatcher, Bot
from aiogram.types import Message, FSInputFile, InputMediaPhoto, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMedia
import os
import logging
from database import get_user_sold_products, db_manager
from aiogram.enums import ParseMode
from datetime import datetime
import traceback
import json
from database import execute_query
from handlers import shared_context

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

sent_orders = {} # Убираем загрузку и сохранение sent_orders из JSON

# Получаем абсолютный путь к корневой директории (где находится database.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(PROJECT_ROOT, "data", "images")

def register_balance_handler(dp: Dispatcher, bot: Bot):
   # @dp.message(lambda message: message.text == "Покупки / My Orders")
    async def my_orders_handler(message: Message | CallbackQuery, bot: Bot):
        conn = db_manager.get_connection()
        if not conn:
           logging.error("my_orders_handler: Не удалось получить соединение из пула.")
           return
        try:
            if isinstance(message, Message):
               user_id = message.from_user.id
               chat_id = message.chat.id
               msg_id = message.message_id
            elif isinstance(message, CallbackQuery):
               user_id = message.from_user.id
               chat_id = message.message.chat.id
               msg_id = message.message.message_id
               message = message.message
            else:
               logging.warning(f"my_orders_handler: Unknown message type")
               return
            
            logging.info(f"balance.py - my_orders_handler: User {user_id} pressed 'Мои / My Orders'")
            global sent_orders # Используем глобальную переменную
            
            user_orders = get_user_sold_products(user_id)
            logging.info(f"balance.py - my_orders_handler: User {user_id} - Orders found: {len(user_orders)}")
            
            keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="Назад / Back", callback_data="back_to_profile")]
                         ]
                   )

            if not user_orders:
               if isinstance(message, CallbackQuery):
                   await bot.edit_message_text("У вас пока нет заказов / You have no orders yet.", chat_id=chat_id, message_id=msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
               elif isinstance(message, Message):
                   await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                   await bot.send_message(text="У вас пока нет заказов / You have no orders yet.", chat_id=chat_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
               return
            
            sent_orders[user_id] = set()  # Сбрасываем sent_orders при каждом вызове
            
            all_media = []
            all_text = "Вот ваши покупки:\nHere are your purchases:\n\n"
            message_ids_to_delete = [] # Cписок для хранения message_id что нужно удалить 
            
            for order in user_orders:
                 # Проверяем, был ли уже отправлен данный заказ
                order_id = f"{user_id}-{order['product_name']}-{order['sale_date']}"
                if order_id not in sent_orders[user_id]:
                     # Форматируем дату
                    sale_date = datetime.strptime(order['sale_date'], '%Y-%m-%d %H:%M:%S')
                    formatted_date = sale_date.strftime('%d/%m/%y %H:%M')
                
                    order_text = (
                        f"📦 Товар / Product: {order['product_name']}\n"
                        f"📍 Город / City: {order['city']}\n"
                        f"🗺️ Район / District: {order['district']}\n"
                        f"📝 Инструкция / Instruction: 📍<code>{order['instruction']}</code>📍\n"
                        f"📅 Дата / Date: {formatted_date}\n\n"
                    )
                    
                    all_text += order_text
        
                    image_paths_string = order.get("images")
                    image_paths = []
                    if isinstance(image_paths_string, str) and image_paths_string:
                        image_paths = image_paths_string.replace('[', '').replace(']', '').replace('"', '').split(', ')
        
                    if image_paths:
                       for image_path in image_paths:
                            full_image_path = os.path.join(IMAGE_DIR, os.path.basename(image_path))
                            if os.path.exists(full_image_path):
                               all_media.append(InputMediaPhoto(media=FSInputFile(full_image_path)))
                            else:
                                logging.warning(f"balance.py - my_orders_handler: Image not found at {full_image_path} for product {order['product_name']}")

                    sent_orders[user_id].add(order_id)


            if all_media:
               if len(all_media) > 1:
                   if isinstance(message, CallbackQuery):
                      sent_media = await bot.edit_message_media(media=all_media[0], chat_id=chat_id, message_id=msg_id)
                      message_ids_to_delete.append(sent_media.message_id)
                      sent_group = await bot.send_media_group(chat_id=chat_id, media=all_media[1:])
                      for sm in sent_group:
                           message_ids_to_delete.append(sm.message_id)
                      sent_text = await bot.send_message(chat_id=chat_id, text=all_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                      message_ids_to_delete.append(sent_text.message_id)
                   elif isinstance(message, Message):
                       await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                       sent_group = await bot.send_media_group(chat_id=chat_id, media=all_media)
                       for sm in sent_group:
                            message_ids_to_delete.append(sm.message_id)
                       sent_text = await bot.send_message(chat_id=chat_id, text=all_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                       message_ids_to_delete.append(sent_text.message_id)
                       if user_id not in shared_context.user_context:
                          shared_context.user_context[user_id] = {}
                       shared_context.user_context[user_id]["my_orders_msg_ids"] = message_ids_to_delete
               else:
                   if isinstance(message, CallbackQuery):
                       sent_media = await bot.edit_message_media(media=all_media[0], chat_id=chat_id, message_id=msg_id)
                       message_ids_to_delete.append(sent_media.message_id)
                       sent_text = await bot.send_message(chat_id=chat_id, text=all_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                       message_ids_to_delete.append(sent_text.message_id)
                   elif isinstance(message, Message):
                       await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                       sent_media = await bot.send_media_group(chat_id=chat_id, media=all_media)
                       for sm in sent_media:
                            message_ids_to_delete.append(sm.message_id)
                       sent_text = await bot.send_message(chat_id=chat_id, text=all_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                       message_ids_to_delete.append(sent_text.message_id)
                       if user_id not in shared_context.user_context:
                          shared_context.user_context[user_id] = {}
                       shared_context.user_context[user_id]["my_orders_msg_ids"] = message_ids_to_delete

            else:
                if isinstance(message, CallbackQuery):
                    await bot.edit_message_text(text=all_text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                elif isinstance(message, Message):
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    sent_text = await bot.send_message(chat_id=chat_id, text=all_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
                    if user_id not in shared_context.user_context:
                      shared_context.user_context[user_id] = {}
                    shared_context.user_context[user_id]["my_orders_msg_ids"] = [sent_text.message_id]


        except Exception as e:
            logging.error(f"my_orders_handler: Ошибка - {e}")
        finally:
           db_manager.release_connection(conn)
    
    
    async def back_to_profile_handler(callback: CallbackQuery, bot: Bot):
        user_id = callback.from_user.id
        chat_id = callback.message.chat.id
        log_id = uuid.uuid4()
        logging.info(f"balance.py - back_to_profile_handler: INFO: User {user_id} pressed 'Назад'") # User {user_id} pressed 'Back'

        if user_id in shared_context.user_context and "my_orders_msg_ids" in shared_context.user_context[user_id]:
              message_ids_to_delete = shared_context.user_context[user_id]["my_orders_msg_ids"]
              for mid in message_ids_to_delete:
                  try:
                     await bot.delete_message(chat_id=chat_id, message_id=mid)
                  except Exception as e:
                     logging.error(f"balance.py - back_to_profile_handler: error deleting message {mid} : {e}")  #  error deleting message  {e}
              shared_context.user_context[user_id].pop("my_orders_msg_ids", None)
        
        from handlers.profile import _send_profile_info
        await _send_profile_info(callback.message, bot, user_id)

        await callback.answer()
    
    dp.callback_query.register(my_orders_handler, lambda callback: callback.data == "my_orders_inline")
    dp.callback_query.register(back_to_profile_handler, lambda callback: callback.data == "back_to_profile")