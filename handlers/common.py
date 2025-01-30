# handlers/common.py

from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
import logging
import aiofiles
import os

async def send_or_edit_message(
    bot: Bot,
    chat_id: int,
    text: str,
    message_id: int = None,
    reply_markup: types.InlineKeyboardMarkup = None,
    media_path: str = None,
    media_type: str = None,  # 'photo' или 'video'
    parse_mode: str = None
):
    try:
        logging.info(f"send_or_edit_message: chat_id={chat_id}, message_id={message_id}, media_path={media_path}, media_type={media_type}")
        if message_id:
            # Редактируем сообщение
            if media_path and media_type:
                if not os.path.isfile(media_path):
                    logging.error(f"send_or_edit_message: Файл не найден: {media_path}")
                    media_path = None  # Отключаем медиа, если файл не найден
                else:
                    logging.info(f"send_or_edit_message: Отправка медиа из файла: {media_path}")
                if media_type == 'photo':
                    media = types.InputMediaPhoto(
                        media=types.FSInputFile(media_path),
                        caption=text,
                        parse_mode=parse_mode
                    )
                    await bot.edit_message_media(
                        media=media,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=reply_markup
                    )
                elif media_type == 'video':
                    media = types.InputMediaVideo(
                        media=types.FSInputFile(media_path),
                        caption=text,
                        parse_mode=parse_mode
                    )
                    await bot.edit_message_media(
                        media=media,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=reply_markup
                    )
                else:
                    raise ValueError("Unsupported media_type")
            else:
                await bot.edit_message_text(
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        else:
            # Отправляем новое сообщение
            if media_path and media_type:
                if not os.path.isfile(media_path):
                    logging.error(f"send_or_edit_message: Файл не найден: {media_path}")
                    media_path = None  # Отключаем медиа, если файл не найден
                else:
                    logging.info(f"send_or_edit_message: Отправка медиа из файла: {media_path}")
                if media_type == 'photo':
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=types.FSInputFile(media_path),
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                elif media_type == 'video':
                    await bot.send_video(
                        chat_id=chat_id,
                        video=types.FSInputFile(media_path),
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    raise ValueError("Unsupported media_type")
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
    except TelegramBadRequest as e:
        logging.error(f"send_or_edit_message: TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"send_or_edit_message: Ошибка при отправке/редактировании сообщения: {e}")

async def delete_message(bot: Bot, chat_id: int, message_id: int):
    """
    Удаляет сообщение по chat_id и message_id.
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logging.info(f"delete_message: Удалено сообщение {message_id} в чате {chat_id}.")
    except TelegramBadRequest as e:
        logging.error(f"delete_message: Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")
    except Exception as e:
        logging.error(f"delete_message: Произошла ошибка при удалении сообщения {message_id} в чате {chat_id}: {e}")
