import logging
import os
from aiogram import Dispatcher, Bot, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database import get_all_locations, get_available_products  # Исправленный импорт
from handlers.shared_context import user_context
from keyboards import main_menu_keyboard
from handlers.states import CityStates  # импорт состояния из states.py
from handlers.utils import send_or_edit_message  # Предполагаем, что у вас есть такой модуль

logging.basicConfig(level=logging.INFO)

async def delete_message(bot: Bot, chat_id: int, message_id: int):
    """Удаляет сообщение в указанном чате."""
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest as e:
        logging.info(f"Игнорируется TelegramBadRequest: {e}")
    except Exception as e:
        logging.error(f"Ошибка при удалении сообщения: {e}")

async def send_districts_message(
    bot: Bot,
    user_id: int,
    chat_id: int,
    selected_city: str,
    media_path: str,
    districts_keyboard: types.InlineKeyboardMarkup,
    message_id: int = None,
):
    """
    Отправляет сообщение с районами, сохраняя нижнюю клавиатуру активной.
    """
    await send_or_edit_message(bot, chat_id, message_id,
                               caption=f"Вы выбрали <b>{selected_city}</b>.\nHere are the available districts:",
                               reply_markup=districts_keyboard, media_path=media_path, media_type='photo')

async def get_city_image_path(city: str) -> str:
    """Возвращает путь к изображению города."""
    image_name = "11vibor_raiona.png"  # Default image
    if city == "Бангкок":
        image_name = "bangkok.jpg"
    elif city == "Пхукет":
        image_name = "phuket.jpg"
    elif city == "Самуи":
        image_name = "samui.jpg"
    elif city == "Панган":
        image_name = "phangan.jpg"
    elif city == "Паттайя":
        image_name = "pattaya.jpg"
    return os.path.join("data", "images", image_name)

async def cities_handler(message: Message, bot: Bot, state: FSMContext):
    """Обрабатывает отображение доступных городов пользователю."""
    user_id = message.from_user.id
    logging.info(f"cities.py - cities_handler: Пользователь {user_id}, Текст: {message.text}")

    if user_id not in user_context:
        user_context[user_id] = {}

    await state.set_state(CityStates.CITY_SELECTED)
    user_context[user_id]["step"] = "cities_list"

    locations_data = get_all_locations()
    logging.info(f"cities.py - cities_handler: locations_data: {locations_data}")

    if locations_data:
        cities = sorted(list({loc["city"] for loc in locations_data})) # Получаем уникальные имена городов
        city_buttons = []
        for city in cities:  #  Перебираем только уникальные названия городов
            city_en = next((loc.get("city_en", "") for loc in locations_data if loc["city"] == city), "")
            button_text = f"{city}"
            if city_en:
               button_text = f"{city} ({city_en})" # формируем текст для кнопки
            city_buttons.append(KeyboardButton(text=button_text))
        # Разделяем кнопки городов на пары
        city_rows = [city_buttons[i:i + 2] for i in range(0, len(city_buttons), 2)]
    else:
        logging.warning("cities.py - cities_handler: Не найдено ни одного города в базе данных.")
        await message.answer(
            "Извините, на данный момент нет доступных городов. Попробуйте позже.\nSorry, there are no cities available at the moment. Please try again later.",
            reply_markup=main_menu_keyboard()
        )
        return

    # Создаем кнопку "Главное меню"
    main_menu_button = KeyboardButton(text="Главное меню / Main Menu")

    # Формируем структуру клавиатуры, добавляя кнопку "Главное меню"
    keyboard_rows = city_rows + [[main_menu_button]]

    cities_keyboard_markup = ReplyKeyboardMarkup(keyboard=keyboard_rows, resize_keyboard=True)

    media_path = "data/images/1sdelat_zakaz.png"
    logging.info(f"cities.py - cities_handler: DEBUG: Путь к картинке - {media_path}")

    try:
        if os.path.exists(media_path):
            sent_message = await bot.send_photo(
                chat_id=message.chat.id,
                photo=FSInputFile(media_path),
                caption="Выберите город:\nSelect a city:",
                reply_markup=cities_keyboard_markup,
                parse_mode="HTML"
            )
            user_context[user_id]["city_message_id"] = sent_message.message_id
        else:
            sent_message = await message.answer(
                "Выберите город:\nSelect a city:",
                reply_markup=cities_keyboard_markup
            )
            logging.warning(f"cities.py - cities_handler: Картинка не найдена по пути: {media_path}")
            user_context[user_id]["city_message_id"] = sent_message.message_id  # Сохраняем message_id даже без картинки
    except Exception as e:
        await message.answer(
            f"Ошибка при отправке картинки: {e}\nError sending image: {e}\n\nВыберите город:\nSelect a city:",
            reply_markup=cities_keyboard_markup
        )
        logging.error(f"cities.py - cities_handler: Ошибка при отправке картинки: {e}")

def register_city_handlers(dp: Dispatcher, bot: Bot):
    """Регистрация обработчиков для выбора города и района."""

    @dp.message(lambda message: user_context.get(message.from_user.id, {}).get("step") == "cities_list")
    async def districts_handler(message: Message, bot: Bot, state: FSMContext):
        """Обрабатывает отображение доступных районов для выбранного города."""
        user_id = message.from_user.id
        selected_city = message.text
        logging.info(f"cities.py - districts_handler: Пользователь {user_id} выбрал город: {selected_city}")

        # Извлекаем только русское название, даже если в кнопке присутствует английское
        selected_city = selected_city.split(' (', 1)[0].strip()

        if selected_city in ["Назад", "Главное меню / Main Menu"]:
            if selected_city == "Назад":
                await back_handler(message, bot, state)
            else:
                await main_menu_handler(message, bot, state)
            return

        locations_data = get_all_locations()
        districts_in_city = sorted([loc["district"] for loc in locations_data if loc["city"] == selected_city])

        if districts_in_city:
            districts_keyboard = InlineKeyboardBuilder()
            for loc in locations_data:
               if loc["city"] == selected_city:
                   district = loc["district"]
                   district_en = loc.get("district_en", "") # получаем значение `district_en`
                   button_text = f"{district}"
                   if district_en:
                      button_text = f"{district} ({district_en})" # формируем текст для кнопки

                   districts_keyboard.button(
                    text=button_text,
                    callback_data=f"district_{selected_city}_{district}"
                )
            districts_keyboard.adjust(2)

            media_path = await get_city_image_path(selected_city)
            logging.info(f"cities.py - districts_handler: DEBUG: Путь к картинке - {media_path}")

            await send_districts_message(
                bot=bot,
                user_id=user_id,
                chat_id=message.chat.id,
                selected_city=selected_city,
                media_path=media_path,
                districts_keyboard=districts_keyboard.as_markup()
            )

            # Удаляем старое сообщение об отсутствии товаров, если оно есть
            if user_context[user_id].get("no_products_message_id"):
                await delete_message(bot, message.chat.id, user_context[user_id]["no_products_message_id"])
                user_context[user_id].pop("no_products_message_id", None)
        else:
            # Если нет районов, отправляем сообщение об отсутствии районов
            no_products_message_id = user_context[user_id].get("no_products_message_id")
            if no_products_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=no_products_message_id,
                        text=f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.",
                        parse_mode="HTML"
                    )
                except TelegramBadRequest:
                    sent_message = await message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                    user_context[user_id]["no_products_message_id"] = sent_message.message_id
            else:
                sent_message = await message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                user_context[user_id]["no_products_message_id"] = sent_message.message_id

        await state.update_data(city=selected_city)
        user_context[user_id]["selected_city"] = selected_city
        user_context[user_id]["step"] = "districts_list"

    @dp.callback_query(lambda query: query.data.startswith("district_"))
    async def select_district_handler(query: CallbackQuery, bot: Bot, state: FSMContext):
        """Обрабатывает выбор района пользователем."""
        user_id = query.from_user.id
        _, city, selected_district = query.data.split("_", 2)
        logging.info(f"cities.py - select_district_handler: Пользователь {user_id}, Город: {city}, Район: {selected_district}")

        # Инициализация контекста пользователя, если его нет
        if user_id not in user_context:
            user_context[user_id] = {}

        # Явно устанавливаем значение для ключа "step"
        user_context[user_id]["step"] = "products_pending"  # Или любое другое подходящее значение

        await state.update_data(city=city, district=selected_district)
        user_context[user_id]["selected_city"] = city
        user_context[user_id]["selected_district"] = selected_district

        logging.info(f"cities.py - select_district_handler: Проверка user_id перед вызовом show_all_products_handler: {user_id}")

        # Теперь при вызове обработчика продуктов, он должен сам определить картинку на основе города
        from handlers.categories import show_all_base_product_names_handler
        await show_all_base_product_names_handler(query, bot, state, get_city_image_path)

        await query.answer()

    @dp.message(lambda message:  any(
        (loc["city"] in message.text or (loc.get("city_en") and loc["city_en"] in message.text)) for loc in get_all_locations()
        ))
    async def city_selected_from_bottom_menu_handler(message: Message, bot: Bot, state: FSMContext):
        """Обрабатывает выбор города из нижнего меню и переходит к отображению районов."""
        user_id = message.from_user.id
        selected_city = message.text
        logging.info(f"cities.py - city_selected_from_bottom_menu_handler: User {user_id} selected city from bottom menu: {selected_city}")

        # Извлекаем только русское название города, даже если в кнопке есть английское
        selected_city = selected_city.split(' (', 1)[0].strip()

        if user_id not in user_context:
            user_context[user_id] = {}

        user_context[user_id]["selected_city"] = selected_city
        user_context[user_id]["step"] = "districts_list"

        locations_data = get_all_locations()
        districts_in_city = sorted([loc["district"] for loc in locations_data if loc["city"] == selected_city])

        if districts_in_city:
            districts_keyboard = InlineKeyboardBuilder()
            for loc in locations_data:
               if loc["city"] == selected_city:
                   district = loc["district"]
                   district_en = loc.get("district_en", "") # получаем значение `district_en`
                   button_text = f"{district}"
                   if district_en:
                      button_text = f"{district} ({district_en})" # формируем текст для кнопки

                   districts_keyboard.button(
                    text=button_text,
                    callback_data=f"district_{selected_city}_{district}"
                )
            districts_keyboard.adjust(2)

            media_path = await get_city_image_path(selected_city)
            logging.info(f"cities.py - districts_handler: DEBUG: Путь к картинке - {media_path}")

            await send_districts_message(
                bot=bot,
                user_id=user_id,
                chat_id=message.chat.id,
                selected_city=selected_city,
                media_path=media_path,
                districts_keyboard=districts_keyboard.as_markup()
            )
        else:
            # Отправляем сообщение об отсутствии районов
            no_districts_message_id = user_context[user_id].get("no_products_message_id")
            if no_districts_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=no_districts_message_id,
                         text=f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.",
                        parse_mode="HTML"
                    )
                except TelegramBadRequest:
                     sent_message = await message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                     user_context[user_id]["no_products_message_id"] = sent_message.message_id
            else:
                sent_message = await message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                user_context[user_id]["no_products_message_id"] = sent_message.message_id

        await state.update_data(city=selected_city)
        user_context[user_id]["selected_city"] = selected_city

    @dp.callback_query(lambda query: query.data == "back_to_cities")
    async def back_to_cities_handler(query: CallbackQuery, bot: Bot, state: FSMContext):
        """Обрабатывает навигацию назад из списка районов к списку городов."""
        user_id = query.from_user.id
        logging.info(f"cities.py - back_to_cities_handler: Пользователь {user_id}")

        if user_id not in user_context:
            user_context[user_id] = {}

        await state.set_state(CityStates.CITY_SELECTED)
        user_context[user_id]["step"] = "cities_list"

        await cities_handler(query.message, bot, state)
        await query.answer()

    @dp.message(lambda message: message.text == "Главное меню / Main Menu")
    async def main_menu_handler(message: Message, bot: Bot, state: FSMContext):
        """Обрабатывает навигацию к главному меню."""
        user_id = message.from_user.id
        logging.info(f"cities.py - main_menu_handler: Пользователь {user_id} нажал 'Главное меню'")

        await state.clear()
        if user_id in user_context:
            del user_context[user_id]

        await message.answer("Вы вернулись в главное меню.\nYou have returned to the main menu.", reply_markup=main_menu_keyboard())

        # Закрываем возможно открытое инлайн меню
        if message.reply_to_message and message.reply_to_message.reply_markup:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=message.chat.id,
                    message_id=message.reply_to_message.message_id,
                    reply_markup=None
                )
            except TelegramBadRequest:
                logging.info("Не удалось закрыть инлайн меню главного меню.")

    @dp.message(lambda message: message.text == "Назад",
               lambda message: user_context.get(message.from_user.id, {}).get("step") != "main_menu")
    async def back_handler(message: Message, bot: Bot, state: FSMContext):
        """Обрабатывает логику навигации назад."""
        user_id = message.from_user.id
        current_step = user_context.get(user_id, {}).get("step", "main_menu")
        logging.info(f"cities.py - back_handler: Пользователь {user_id}, Шаг: {current_step}, Текст: {message.text}")

        if current_step == "cities_list":
            await state.clear()
            user_context[user_id]["step"] = "main_menu"
            await message.answer("Вы вернулись в главное меню.\nYou have returned to the main menu.", reply_markup=main_menu_keyboard())

        elif current_step == "districts_list":
            user_context[user_id]["step"] = "cities_list"
            await state.set_state(CityStates.CITY_SELECTED)
            await cities_handler(message, bot, state)

        elif current_step == "products_list":
             user_context[user_id]["step"] = "districts_list"
             data = await state.get_data()
             selected_city = data.get("city")
             if selected_city:
                 districts_keyboard = InlineKeyboardBuilder()
                 locations_data = get_all_locations()
                 for loc in locations_data:
                     if loc["city"] == selected_city:
                         district = loc["district"]
                         district_en = loc.get("district_en", "")
                         button_text = f"{district}"
                         if district_en:
                             button_text = f"{district} ({district_en})"
                         districts_keyboard.button(
                             text=button_text,
                             callback_data=f"district_{selected_city}_{district}"
                         )
                 districts_keyboard.adjust(2)
                 media_path = await get_city_image_path(selected_city)
                 logging.info(f"cities.py - back_handler: DEBUG: Путь к картинке - {media_path}")

                 await send_districts_message(
                     bot=bot,
                     user_id=user_id,
                     chat_id=message.chat.id,
                     selected_city=selected_city,
                     media_path=media_path,
                     districts_keyboard=districts_keyboard.as_markup()
                 )
             else:
                 await message.answer("Ошибка! Сначала выберите город.\nError! Select a city first.")
                 await state.set_state(CityStates.CITY_SELECTED)

        else:
            await state.clear()
            user_context[user_id]["step"] = "main_menu"
            await message.answer("Вы вернулись в главное меню.\nYou have returned to the main menu.", reply_markup=main_menu_keyboard())

        # Удаляем сообщение с кнопкой "Назад"
        await delete_message(bot, message.chat.id, message.message_id)