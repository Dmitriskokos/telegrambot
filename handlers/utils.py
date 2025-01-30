import logging
import os
import types
from aiogram import Bot
from aiogram.types import FSInputFile

logging.basicConfig(level=logging.INFO)

async def send_or_edit_message(
    bot: Bot,
    chat_id: int,
    message_id: int = None,
    text: str = None,
    reply_markup=None,
    media_path: str = None,
    media_type: str = None,
    caption: str = None,
    parse_mode: str = "HTML",
):
    """Отправляет новое сообщение или редактирует существующее."""
    try:
        if media_path:
            media = FSInputFile(media_path)
            if media_type == 'photo':
                if message_id:
                    logging.info(f"send_or_edit_message: Редактирование сообщения. chat_id={chat_id}, message_id={message_id}, media_path={media_path}, media_type={media_type}")
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=types.InputMediaPhoto(media=media, caption=caption, parse_mode=parse_mode),
                        reply_markup=reply_markup
                    )
                else:
                    logging.info(f"send_or_edit_message: Отправка медиа из файла: {media_path}")
                    await bot.send_photo(chat_id=chat_id, photo=media, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
            elif media_type == 'video':
                if message_id:
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=types.InputMediaVideo(media=media, caption=caption, parse_mode=parse_mode),
                        reply_markup=reply_markup
                    )
                else:
                    await bot.send_video(chat_id=chat_id, video=media, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
            elif media_type == 'animation':
                if message_id:
                    await bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=message_id,
                        media=types.InputMediaAnimation(media=media, caption=caption, parse_mode=parse_mode),
                        reply_markup=reply_markup
                    )
                else:
                    await bot.send_animation(chat_id=chat_id, animation=media, caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        elif text:
            if message_id:
                logging.info(f"send_or_edit_message: Редактирование текста сообщения. chat_id={chat_id}, message_id={message_id}, text='{text[:50]}...'")
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                logging.info(f"send_or_edit_message: Отправка текстового сообщения. chat_id={chat_id}, text='{text[:50]}...'")
                await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            logging.warning("send_or_edit_message: Нет текста или медиа для отправки/редактирования.")
    except Exception as e:
        logging.error(f"send_or_edit_message: Ошибка при отправке/редактировании сообщения: {e}")