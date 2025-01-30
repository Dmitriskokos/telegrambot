import logging
import os
import random
import sqlite3
import uuid
from aiogram import Dispatcher, F, Bot, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import bold, text
from handlers import shared_context
from database import add_ticket, get_user_tickets, get_support_channel_id, get_user_sold_products  # Import get_support_channel_id
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types.input_file import FSInputFile
from keyboards import main_menu_keyboard  # Import main_menu_keyboard


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Клавиатура для первого экрана поддержки
def support_keyboard_1():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Новый тикет / New Ticket")],
            [KeyboardButton(text="Мои тикеты / My Tickets")],
            [KeyboardButton(text="Чат с саппортом / Support Chat")], # Добавили кнопку
            [KeyboardButton(text="<<< Назад / Back")],
        ],
        resize_keyboard=True,
    )
    return keyboard

# Клавиатура для второго экрана поддержки с двумя колонками
def support_keyboard_2():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Заказ / Order"),
            ],
            [
                KeyboardButton(text="Услуги / Services"),
            ],
            [
                KeyboardButton(text="Ошибка / Bug"),
                KeyboardButton(text="ОПТ / Wholesale"),
            ],
            [KeyboardButton(text="<<< Назад / Back")],
        ],
        resize_keyboard=True,
    )
    return keyboard

def load_user_orders(user_id):
    """Загружает заказы пользователя из базы данных."""
    user_orders = []
    products = get_user_sold_products(user_id)
    for product in products:
        user_orders.append(f"{product.get('product_name')} - {product.get('city')}, {product.get('district')}")
    logging.info(f"support.py - load_user_orders: Loaded {len(user_orders)} orders for user {user_id}")
    return user_orders

# Функция для создания клавиатуры с заказами
def create_order_keyboard(orders):
    """Создает клавиатуру с заказами пользователя."""
    if not orders:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="<<< Назад / Back")]], resize_keyboard=True)
    keyboard = [[KeyboardButton(text=order)] for order in orders]
    keyboard.append([KeyboardButton(text="<<< Назад / Back")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def open_support_chat_handler(message: Message):
    """
    Открывает чат с @thai_hub_supp по прямой ссылке.
    """

    support_chat_link = "https://t.me/thai_hub_supp"  # Ссылка на чат

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Чат / Chat", url=support_chat_link)]
    ])

    await message.answer("Для связи с поддержкой перейдите в чат: \n\n For support, go to the chat:", reply_markup=keyboard)

# Регистрация обработчика для кнопки "Саппорт / Support" и навигации
def register_support_handler(dp: Dispatcher, bot: Bot):
    @dp.message(lambda message: message.text == "Саппорт / Support")
    async def support_handler(message: Message):
        user_id = message.from_user.id
        logging.info(f"support.py - support_handler: User {user_id} pressed 'Саппорт / Support'")
        if user_id not in shared_context.user_context:
            shared_context.user_context[user_id] = {}
        shared_context.user_context[user_id]["step"] = "support_main_menu"
        await message.answer("Выберите действие: \n\n Select an action:", reply_markup=support_keyboard_1())

    @dp.message(lambda message: message.text == "Новый тикет / New Ticket")
    async def create_ticket_handler(message: Message):
        user_id = message.from_user.id
        logging.info(f"support.py - create_ticket_handler: User {user_id} pressed 'Новый тикет'")
        if user_id not in shared_context.user_context:
            shared_context.user_context[user_id] = {}
        shared_context.user_context[user_id]["step"] = "support_second_menu"
        await message.answer("Выберите тип: \n\n Select the type:", reply_markup=support_keyboard_2())
    
    #Новый обработчик для кнопки "Чат с саппортом / Support Chat"
    @dp.message(lambda message: message.text == "Чат с саппортом / Support Chat")
    async def support_chat_button_handler(message: Message):
        await open_support_chat_handler(message)    

    @dp.message(lambda message: message.text == "<<< Назад / Back")
    async def back_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        if user_id not in shared_context.user_context:
            shared_context.user_context[user_id] = {}

        current_step = shared_context.user_context[user_id].get("step")

        if current_step == "support_second_menu":
            logging.info(f"support.py - back_handler: User {user_id} pressed '<<< Назад / Back' from second support menu, back to first")
            shared_context.user_context[user_id]["step"] = "support_main_menu"
            await message.answer("Выберите действие: \n\n Select an action:", reply_markup=support_keyboard_1())
        elif current_step == "order_selection_menu":
            logging.info(f"support.py - back_handler: User {user_id} pressed '<<< Назад / Back' from order selection menu, back to second support menu")
            shared_context.user_context[user_id]["step"] = "support_second_menu"
            await message.answer("Выберите тип: \n\n Select the type:", reply_markup=support_keyboard_2())
        elif current_step == "support_main_menu":
            logging.info(
                f"support.py - back_handler: User {user_id} pressed '<<< Назад / Back' in support menu, returning to main menu")
            shared_context.user_context[user_id]["step"] = "main_menu"
            await message.answer("Вы вернулись в главное меню. \n\n You have returned to the main menu.", reply_markup=main_menu_keyboard())
        elif current_step in ["bug_report_input", "advertising_input", "opt_input"]: 
            logging.info(
               f"support.py - back_handler: User {user_id} pressed '<<< Назад / Back' in input, returning to support main menu")
            shared_context.user_context[user_id]["step"] = "support_main_menu" 
            await message.answer("Выберите действие: \n\n Select an action:", reply_markup=support_keyboard_1()) 
        else:
           logging.info(f"support.py - back_handler: User {user_id} pressed '<<< Назад / Back' with unknown step: {current_step}, returning to main menu")
           shared_context.user_context[user_id]["step"] = "main_menu"
           await message.answer("Вы вернулись в главное меню. \n\n You have returned to the main menu.", reply_markup=main_menu_keyboard())

    @dp.message(lambda message: message.text == "Заказ / Order")
    async def order_issues_handler(message: Message, bot:Bot):
        user_id = message.from_user.id
        logging.info(f"support.py - order_issues_handler: User {user_id} selected 'Заказ'")
        if user_id not in shared_context.user_context:
             shared_context.user_context[user_id] = {}

        user_orders = load_user_orders(user_id)
        if not user_orders:
            await message.answer("У вас нет заказов. \n\n You have no orders.",
                                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="<<< Назад / Back")]],
                                                               resize_keyboard=True))
        else:
            shared_context.user_context[user_id]["step"] = "order_selection_menu"
            await message.answer("Выберите заказ: \n\n Select the order:",
                                reply_markup=create_order_keyboard(user_orders))
           
    # Обработка выбора заказа
    @dp.message(lambda message: message.text != "<<< Назад / Back" and
            message.text != "Мои тикеты / My Tickets" and shared_context.user_context.get(message.from_user.id, {}).get("step") == "order_selection_menu")
    async def selected_order_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        order_text = message.text
        logging.info(f"support.py - selected_order_handler: User {user_id} selected order '{order_text}'")

        user_orders = load_user_orders(user_id)
        if order_text in user_orders:  
            
            user = await bot.get_chat(user_id)
            user_username = user.username 

            user_link = f"tg://user?id={user_id}"
                     
            if user_username:
                support_message = f"Проблема с заказом: {order_text}\nПользователь: @{user_username}" 
            else:
                support_message = f"Проблема с заказом: {order_text}\nСсылка на пользователя: {user_link}" 
                    
            try:
                support_channel_id = get_support_channel_id()
                if support_channel_id:
                    if not isinstance(support_channel_id, int):
                         logging.warning(f"support.py - selected_order_handler: SUPPORT_CHANNEL_ID is not int, converting to int")
                         support_channel_id = int(support_channel_id)
                         logging.info(f"support.py - selected_order_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                    else:
                         logging.info(f"support.py - selected_order_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                    # Save ticket to db
                    add_ticket(user_id, support_message)
                    shared_context.user_context[user_id]["step"] = "support_main_menu" 
                    await message.answer("Сообщение отправлено в поддержку. \n\n Message sent to support.",
                                        reply_markup=support_keyboard_1())
                else:
                    logging.error(f"support.py - selected_order_handler: support_channel_id is None.")
                    await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                        reply_markup=support_keyboard_1())
            except Exception as e:
                logging.error(f"support.py - selected_order_handler: Error sending message to support channel: {e}")
                await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                    reply_markup=support_keyboard_1())
        else:
            logging.warning(f"support.py - selected_order_handler: Order text '{order_text}' not in user's orders.")
            await message.answer("Выберите заказ из списка. \n\n Select an order from the list.")


    @dp.message(lambda message: message.text == "Мои тикеты / My Tickets")
    async def list_tickets_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        logging.info(f"support.py - list_tickets_handler: User {user_id} pressed 'Мои тикеты'")

        tickets = get_user_tickets(user_id)
        if tickets:
            response_text = "Ваши тикеты:\n\n / Your tickets:\n\n"
            for ticket in tickets:
                response_text += f"- {ticket}\n"
        else:
            response_text = "У вас нет тикетов. \n\n You have no tickets."
            
        await message.answer(response_text, reply_markup=support_keyboard_1())


    @dp.message(lambda message: message.text == "Ошибка / Bug")
    async def bug_report_handler(message: Message):
        user_id = message.from_user.id
        logging.info(f"support.py - bug_report_handler: User {user_id} selected 'Ошибка'")
        if user_id not in shared_context.user_context:
             shared_context.user_context[user_id] = {}
        shared_context.user_context[user_id]["step"] = "bug_report_input"  
        await message.answer(
            "Опишите ошибку. \n\n Describe the bug."
        )

    @dp.message(lambda message: shared_context.user_context.get(message.from_user.id, {}).get("step") == "bug_report_input")
    async def bug_report_input_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        logging.info(f"support.py - bug_report_input_handler: User {user_id} is inputting bug report")

        
        user = await bot.get_chat(user_id) 
        user_username = user.username 
        user_link = f"tg://user?id={user_id}"
        report_text = message.text.strip() 
        if report_text and report_text != "<<< Назад / Back":
            if user_username:
                support_message = f"Ошибка в боте: \n\n{report_text}\n\nПользователь: @{user_username}"  
            else:
                support_message = f"Ошибка в боте: \n\n{report_text}\n\nСсылка на пользователя: {user_link}"  
            
            try:
                 support_channel_id = get_support_channel_id()
                 if support_channel_id:
                    if not isinstance(support_channel_id, int):
                         logging.warning(f"support.py - bug_report_input_handler: SUPPORT_CHANNEL_ID is not int, converting to int")
                         support_channel_id = int(support_channel_id)
                         logging.info(f"support.py - bug_report_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                    else:
                         logging.info(f"support.py - bug_report_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                     # Save ticket to db
                    add_ticket(user_id, support_message)
                    await message.answer("Сообщение отправлено в поддержку. \n\n Message sent to support.",
                                       reply_markup=support_keyboard_1())
                 else:
                     logging.error(f"support.py - bug_report_input_handler: support_channel_id is None.")
                     await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                        reply_markup=support_keyboard_1())
            except Exception as e:
                logging.error(f"support.py - bug_report_input_handler: Error sending message to support channel: {e}")
                await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                    reply_markup=support_keyboard_1())
            shared_context.user_context[user_id]["step"] = "support_main_menu" 
        elif report_text == "<<< Назад / Back": 
            shared_context.user_context[user_id]["step"] = "support_second_menu" 
            await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
            return 
        else:
             #Если пользователь нажал другую кнопку, сбрасываем шаг и возвращаемся в меню 2
            shared_context.user_context[user_id]["step"] = "support_second_menu"
            await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
            return 


    @dp.message(lambda message: message.text == "Услуги / Services")
    async def advertising_handler(message: Message):
        user_id = message.from_user.id
        logging.info(f"support.py - advertising_handler: User {user_id} selected 'Услуги'")
        if user_id not in shared_context.user_context:
             shared_context.user_context[user_id] = {}
        shared_context.user_context[user_id]["step"] = "advertising_input"
        await message.answer(
            text(
                bold("Текст обращения: / Message text:"),
                "\n\nВаши предложения? / Your offers?\n",
                "Напишите нам, если интересно. / Write to us if interested.\n"
                ,sep=""
            ),
            parse_mode="Markdown"
        )

    @dp.message(lambda message: shared_context.user_context.get(message.from_user.id, {}).get("step") == "advertising_input")
    async def advertising_input_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        logging.info(f"support.py - advertising_input_handler: User {user_id} is inputting advertising message")
         
        user = await bot.get_chat(user_id) 
        user_username = user.username 
        user_link = f"tg://user?id={user_id}"
        report_text = message.text.strip() 

        if report_text and report_text != "<<< Назад / Back":
            if user_username:
                support_message = f"Сообщение о сотрудничестве: \n\n{report_text}\n\nПользователь: @{user_username}"
            else:
                support_message = f"Сообщение о сотрудничестве: \n\n{report_text}\n\nСсылка на пользователя: {user_link}"

            try:
                support_channel_id = get_support_channel_id()
                if support_channel_id:
                     if not isinstance(support_channel_id, int):
                         logging.warning(f"support.py - advertising_input_handler: SUPPORT_CHANNEL_ID is not int, converting to int")
                         support_channel_id = int(support_channel_id)
                         logging.info(f"support.py - advertising_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                     else:
                         logging.info(f"support.py - advertising_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                     add_ticket(user_id, support_message) 
                     await message.answer(
                        "Сообщение отправлено, спасибо! / Message sent, thanks!",
                        reply_markup=support_keyboard_1(),
                    )
                else:
                    logging.error(f"support.py - advertising_input_handler: support_channel_id is None.")
                    await message.answer("Ошибка отправки. Попробуйте позже. / Send error. Try again later.",
                                        reply_markup=support_keyboard_1())

            except Exception as e:
                logging.error(f"support.py - advertising_input_handler: Error sending message to support channel: {e}")
                await message.answer("Ошибка отправки. Попробуйте позже. / Send error. Try again later.",
                                    reply_markup=support_keyboard_1())
            shared_context.user_context[user_id]["step"] = "support_main_menu" 
        elif report_text == "<<< Назад / Back":
             shared_context.user_context[user_id]["step"] = "support_second_menu" 
             await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
             return 
        else:
             #Если пользователь нажал другую кнопку, сбрасываем шаг и возвращаемся в меню 2
            shared_context.user_context[user_id]["step"] = "support_second_menu"
            await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
            return 

    @dp.message(lambda message: message.text == "ОПТ / Wholesale")
    async def opt_handler(message: Message):
        user_id = message.from_user.id
        logging.info(f"support.py - opt_handler: User {user_id} selected 'ОПТ'")
        if user_id not in shared_context.user_context:
             shared_context.user_context[user_id] = {}
        shared_context.user_context[user_id]["step"] = "opt_input"
        await message.answer(
            "Опишите ваш запрос. / Describe your request."
        )

    @dp.message(lambda message: shared_context.user_context.get(message.from_user.id, {}).get("step") == "opt_input")
    async def opt_input_handler(message: Message, bot: Bot):
        user_id = message.from_user.id
        logging.info(f"support.py - opt_input_handler: User {user_id} is inputting opt message")
        
        user = await bot.get_chat(user_id) 
        user_username = user.username 
        user_link = f"tg://user?id={user_id}"
        report_text = message.text.strip() 
        if report_text and report_text != "<<< Назад / Back":
            if user_username:
                support_message = f"Сообщение по ОПТу: \n\n{report_text}\n\nПользователь: @{user_username}"
            else:
                support_message = f"Сообщение по ОПТу: \n\n{report_text}\n\nСсылка на пользователя: {user_link}"
            try:
                support_channel_id = get_support_channel_id()
                if support_channel_id:
                    if not isinstance(support_channel_id, int):
                         logging.warning(f"support.py - opt_input_handler: SUPPORT_CHANNEL_ID is not int, converting to int")
                         support_channel_id = int(support_channel_id)
                         logging.info(f"support.py - opt_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                    else:
                         logging.info(f"support.py - opt_input_handler: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                         await bot.send_message(chat_id=support_channel_id, text=support_message)
                    add_ticket(user_id, support_message) 
                    await message.answer("Сообщение отправлено, скоро свяжемся. \n\n Message sent, we will contact you soon.",
                                       reply_markup=support_keyboard_1())
                else:
                    logging.error(f"support.py - opt_input_handler: support_channel_id is None.")
                    await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                        reply_markup=support_keyboard_1())

            except Exception as e:
                logging.error(f"support.py - opt_input_handler: Error sending message to support channel: {e}")
                await message.answer("Ошибка отправки. Попробуйте позже. \n\n Send error. Try again later.",
                                    reply_markup=support_keyboard_1())
            shared_context.user_context[user_id]["step"] = "support_main_menu"
        elif report_text == "<<< Назад / Back":
             shared_context.user_context[user_id]["step"] = "support_second_menu" 
             await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
             return 
        else:
            #Если пользователь нажал другую кнопку, сбрасываем шаг и возвращаемся в меню 2
            shared_context.user_context[user_id]["step"] = "support_second_menu"
            await message.answer("Выберите тип: / Select the type:", reply_markup=support_keyboard_2())
            return 

    @dp.callback_query(lambda callback_query: callback_query.data == "send_job_form" and shared_context.user_context.get(callback_query.from_user.id,{}).get("step") == "job_form_filled")
    async def send_job_form(callback_query, bot:Bot):
        user_id = callback_query.from_user.id
        logging.info(f"support.py - send_job_form: User {user_id} pressed 'Отправить анкету'")

        
        user = await bot.get_chat(user_id)  
        user_username = user.username  
        
        user_link = f"tg://user?id={user_id}"

        application_text = callback_query.message.text
        
        if user_username:
            support_message = f"Заявка на работу: @{user_username}\n\n"  
        else:
            support_message = f"Заявка на работу: {user_link}\n\n"  

        try:
            support_channel_id = get_support_channel_id()
            if support_channel_id:
                if not isinstance(support_channel_id, int):
                     logging.warning(f"support.py - send_job_form: SUPPORT_CHANNEL_ID is not int, converting to int")
                     support_channel_id = int(support_channel_id)
                     logging.info(f"support.py - send_job_form: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
                else:
                     logging.info(f"support.py - send_job_form: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
                await callback_query.answer("Анкета отправлена. / Application sent.")
                shared_context.user_context[user_id]["step"] = "support_main_menu" 
                await bot.send_message(chat_id=user_id, text="Главное меню / Main menu", reply_markup=support_keyboard_1())
            else:
                logging.error(f"support.py - send_job_form: support_channel_id is None.")
                await callback_query.answer("Ошибка отправки. / Send error.")
        except Exception as e:
            logging.error(f"support.py - send_job_form: Error sending message to support channel: {e}")
            await callback_query.answer("Ошибка отправки. / Send error.")
    @dp.callback_query(lambda callback_query: callback_query.data == "send_job_form_from_vacancies" and shared_context.user_context.get(callback_query.from_user.id,{}).get("step") == "job_form_filled_from_vacancies")
    async def send_job_form_from_vacancies(callback_query, bot:Bot):
        user_id = callback_query.from_user.id
        logging.info(f"support.py - send_job_form_from_vacancies: User {user_id} pressed 'Отправить анкету'")

        
        user = await bot.get_chat(user_id)  
        user_username = user.username  
        
        user_link = f"tg://user?id={user_id}"

        application_text = callback_query.message.text
        
        if user_username:
            support_message = f"Анкета (из вакансий): @{user_username}\n\n{application_text}"  
        else:
            support_message = f"Анкета (из вакансий): {user_link}\n\n{application_text}"  

        try:
            support_channel_id = get_support_channel_id()
            if support_channel_id:
                 if not isinstance(support_channel_id, int):
                     logging.warning(f"support.py - send_job_form_from_vacancies: SUPPORT_CHANNEL_ID is not int, converting to int")
                     support_channel_id = int(support_channel_id)
                     logging.info(f"support.py - send_job_form_from_vacancies: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
                 else:
                     logging.info(f"support.py - send_job_form_from_vacancies: sending message to channel ID: {support_channel_id}, type: {type(support_channel_id)}")
                     await bot.send_message(chat_id=support_channel_id, text=support_message)
            else:
                logging.error(f"support.py - send_job_form_from_vacancies: support_channel_id is None.")
                await callback_query.answer("Ошибка отправки. / Send error.")
            await callback_query.answer("Анкета отправлена. / Application sent.")
            shared_context.user_context[user_id]["step"] = "main_menu" 
            await bot.send_message(chat_id=user_id, text="Главное меню / Main menu", reply_markup=main_menu_keyboard())
        except Exception as e:
            logging.error(f"support.py - send_job_form_from_vacancies: Error sending message to support channel: {e}")
            await callback_query.answer("Ошибка отправки. / Send error.")