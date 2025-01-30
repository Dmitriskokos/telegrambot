from aiogram import Dispatcher, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.utils.markdown import bold, text, italic
from handlers import shared_context
import logging
from aiogram.exceptions import TelegramBadRequest
import os
from database import get_support_channel_id, get_user  # импортируем get_user из database.py

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Функция для удаления сообщений с проверкой
async def delete_message(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        logging.info(f"Ignoring TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Error deleting message: {e}")

def register_earn_handler(dp: Dispatcher):
    @dp.message(lambda message: message.text == "Работа / Jobs")
    async def earn_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        logging.info(f"earn.py - earn_handler: User {user_id} pressed 'Работа / Jobs'")

         # Инициализируем контекст пользователя, если его нет
        if user_id not in shared_context.user_context:
            shared_context.user_context[user_id] = {}

        offer_text = text(
            bold("🇷🇺💸Мы предлагаем:\n"),
            "• ", bold("Стабильную работу\n"),
            "•  Гарантированная занятость с конкурентной оплатой и гибким графиком!\n",
            "•  Полную конфиденциальность и надежную систему безопасности!\n",
            "•  Командировки в соседние города и острова.\n\n",
             bold("От Вас:\n"),
            "• Залог от 600$\n",
            "•  Наличие транспорта\n",
            "•  Отсутствие вредных привычек\n",
            "•  Желание зарабатывать!\n\n",
            "Ждем тебя!😉\n",
            "Просто нажми на кнопку «отправить» и мы свяжемся с тобой в ближайшее время!\n\n",
             "____________________________________\n\n",
            bold("🇺🇸💸We offer:\n"),
            "• ", bold("Stable work\n"),
            "•  Guaranteed employment with competitive pay and flexible hours!\n",
            "•  Full confidentiality and a reliable security system!\n",
            "•  Business trips to neighboring cities and islands.\n\n",
             bold("From you:\n"),
            "• Deposit from $600\n",
            "•  Having transport\n",
            "•  No bad habits\n",
            "•  Desire to earn!\n\n",
            "We are waiting for you!😉\n",
            "Just click the “send” button and we will contact you soon!",
            sep=""
        )

        # Инлайн-клавиатура для отправки сообщения
        send_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отправить / Send", callback_data="vacancies_send_form")]
        ])
        
        # Путь к картинке
        image_path = os.path.join(os.path.dirname(__file__), "..", "data", "images", "123345.jpg")
        logging.info(f"earn.py - earn_handler: DEBUG: Image path - {image_path}")

        try:
            if os.path.exists(image_path):
                photo = FSInputFile(image_path)
                sent_message = await message.answer_photo(photo=photo, caption=offer_text, reply_markup=send_button, parse_mode="Markdown")
                shared_context.user_context[user_id]["application_msg_id"] = sent_message.message_id
                shared_context.user_context[user_id]["image_msg_id"] = sent_message.message_id  # Save message_id of the combined message

            else:
                 sent_message = await message.answer(f"Изображение не найдено. Текст сообщения:\n\n{offer_text}", reply_markup=send_button, parse_mode="Markdown")
                 shared_context.user_context[user_id]["application_msg_id"] = sent_message.message_id
                 shared_context.user_context[user_id]["image_msg_id"] = None

        except Exception as e:
             sent_message = await message.answer(f"Ошибка отправки изображения: {e}. Текст сообщения:\n\n{offer_text}", reply_markup=send_button, parse_mode="Markdown")
             shared_context.user_context[user_id]["application_msg_id"] = sent_message.message_id
             shared_context.user_context[user_id]["image_msg_id"] = None

        shared_context.user_context[user_id]["step"] = "job_form_filled_from_vacancies"
 
    @dp.callback_query(lambda callback_query: callback_query.data == "vacancies_send_form")
    async def handle_vacancies_send_form(callback_query: CallbackQuery, bot: Bot):
        user_id = callback_query.from_user.id
        logging.info(f"earn.py - handle_vacancies_send_form: User {user_id} pressed 'Отправить анкету / Send application' from vacancies")

        # Get user info - get user username from database
        user_data = get_user(user_id)
        if user_data and user_data[5]:
             user_username = user_data[5]
        else:
            user = await bot.get_chat(user_id)
            user_username = user.username
        
        user_link = f"tg://user?id={user_id}"
        # Get text from message caption
        if callback_query.message.caption:
             application_text = callback_query.message.caption
        else:
             application_text = callback_query.message.text

        # Construct message for support channel
        if user_username:
            support_message = f"Новая заявка на устройство на работу от пользователя: @{user_username}\n\nПередайте главному, пусть попиздит с ним, может норм кура"
        else:
            support_message = f"Новая заявка на устройство на работу от пользователя: {user_link}\n\nПередайте главному, пусть попиздит с ним, может норм кура"

        try:
            from main import main_menu_keyboard # Импортируем клавиатуру
            
            # получаем канал поддержки из базы данных
            support_channel_id = get_support_channel_id()
            if support_channel_id:
                if not isinstance(support_channel_id, int):
                     logging.warning(f"earn.py - handle_vacancies_send_form: SUPPORT_CHANNEL_ID is not int, converting to int")
                     support_channel_id = int(support_channel_id)
                     logging.info(f"earn.py - handle_vacancies_send_form: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
                else:
                     logging.info(f"earn.py - handle_vacancies_send_form: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
            else:
                 logging.error(f"earn.py - handle_vacancies_send_form: support_channel_id is None.")
                 await callback_query.answer("Не удалось отправить анкету, попробуйте позже \n\n Failed to send the application, please try again later")
                 return

            await callback_query.answer("Ваша анкета отправлена. \n\n Your application has been sent.")

            application_msg_id = shared_context.user_context[user_id].get("application_msg_id")
            image_msg_id = shared_context.user_context[user_id].get("image_msg_id")

            if application_msg_id:
                await delete_message(bot, user_id, application_msg_id)
            if image_msg_id:
                await delete_message(bot, user_id, image_msg_id)

            shared_context.user_context[user_id]["step"] = "main_menu"  # Возвращаем в главное меню
            await bot.send_message(chat_id=user_id, text="Спасибо! Мы рассмотрим вашу заявку на работу и ответим как можно скорее! \n\n Thank you! We will review your job application and reply as soon as possible!", reply_markup=main_menu_keyboard())
        except Exception as e:
            logging.error(f"earn.py - handle_vacancies_send_form: Error sending message to support channel: {e}")
            await callback_query.answer("Не удалось отправить анкету, попробуйте позже \n\n Failed to send the application, please try again later")