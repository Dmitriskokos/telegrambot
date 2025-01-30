import logging
import sqlite3
from aiogram import Dispatcher, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from html import escape
from collections import defaultdict
import re
import os

# Импортируем функции и словарь user_context
from handlers.cities import get_city_image_path
from handlers.shared_context import user_context
from database import (
    db_manager,  # <-- ИМПОРТИРУЕМ
    get_location_info_from_paid_products,
    get_all_products,
    get_product_category,
    get_product_price,
    get_product_by_name,
    get_all_base_product_names,
    get_all_locations,
)

from handlers.common import send_or_edit_message, delete_message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
 
logging.basicConfig(level=logging.INFO)

logging.basicConfig(level=logging.INFO)

def sanitize_html(text: str) -> str:
    """
    Экранирует HTML-теги, кроме разрешённых (<b>, <i>, <u>, <strong>, <em>).
    """
    allowed_tags = ['b', 'i', 'u', 'strong', 'em']
    escaped = escape(text)
    for tag in allowed_tags:
        escaped = re.sub(rf'<({tag})>', f'<{tag}>', escaped)
        escaped = re.sub(rf'<\/({tag})>', f'</{tag}>', escaped)
    return escaped

class CategoryStates(StatesGroup):
    """Состояния для процесса выбора продукта/граммовки/оплаты."""
    CATEGORY_SELECTED = State()
    PRODUCT_SELECTED = State()
    PAYMENT_PENDING = State()

async def show_all_base_product_names_handler(
    query: types.CallbackQuery, bot: Bot, state: FSMContext, get_city_image_path_func
):
    """
    (ШАГ 1) Показывает *короткие названия* всех товаров для выбранного города и района.
    """
    user_id = query.from_user.id
    data = await state.get_data()
    city = data.get("city")
    district = data.get("district")

    if not city or not district:
        await query.answer("Сначала выберите город и район.\nSelect a city and district first.")
        return

    conn = db_manager.get_connection()
    if not conn:
        logging.error("show_all_base_product_names_handler: Не удалось получить соединение из пула.")
        return
    try:
        message_id = query.message.message_id
        base_names = get_all_base_product_names(city, district)
        if not base_names:
            sent_message = await send_or_edit_message(
                 bot=bot,
                 chat_id=query.message.chat.id,
                 text=(
                   f"В районе <b>{sanitize_html(district)}</b>, города <b>{sanitize_html(city)}</b> "
                   f"пока нет доступных товаров.\n"
                     f"No products are available in <b>{sanitize_html(district)}</b>, <b>{sanitize_html(city)}</b> yet."
                ),
                 parse_mode="HTML"
            )
            if user_id not in user_context:
                user_context[user_id] = {}
            user_context[user_id]["no_products_message_id"] = sent_message.message_id
            await query.answer()
            return
        
        if user_id in user_context and "no_products_message_id" in user_context[user_id]:
            await delete_message(bot, query.message.chat.id, user_context[user_id]["no_products_message_id"])
            del user_context[user_id]["no_products_message_id"]
        
        all_products = get_all_products()
        
        inline_rows = []
        for short_name in sorted(base_names):
            # Получаем информацию о продукте
            product_info = next((item for item in all_products if item.get("name") == short_name), None)
            name_en = product_info.get("name_en", "") if product_info else ""
            button_text = f"{short_name}"
            if name_en:
                button_text = f"{short_name} ({name_en})"
            cb_data = f"select_base_{short_name}"
            inline_rows.append(
                [types.InlineKeyboardButton(text=button_text, callback_data=cb_data)]
            )

        # Кнопка назад
        inline_rows.append([types.InlineKeyboardButton(text="Назад / Back", callback_data="back_to_districts")])

        markup = types.InlineKeyboardMarkup(inline_keyboard=inline_rows)

        media_path = await get_city_image_path_func(city)
        sent_message = await send_or_edit_message(
            bot=bot,
            chat_id=query.message.chat.id,
            text="Выберите товар:\nSelect a product:",
            media_path=media_path,
            media_type="photo",
            message_id=message_id,
            reply_markup=markup,
            parse_mode="HTML"
        )
        if sent_message:
           user_context[user_id]["products_message_id"] = sent_message.message_id
        else:
           user_context[user_id]["products_message_id"] = message_id
        user_context[user_id]["step"] = "products_list"

        await query.answer()
    except Exception as e:
      logging.error(f"show_all_base_product_names_handler: Ошибка - {e}")
    finally:
       db_manager.release_connection(conn)

async def show_product_card_handler(
    query: types.CallbackQuery, bot: Bot, state: FSMContext
):
    """
    Показывает карточку товара с изображением и описанием, а также доступные варианты.
    """
    user_id = query.from_user.id
    data = await state.get_data()
    city = data.get("city")
    district = data.get("district")

    base_name = query.data.replace("select_base_", "", 1)
    conn = db_manager.get_connection()
    if not conn:
        logging.error("show_product_card_handler: Не удалось получить соединение из пула.")
        return

    try:
        if not city or not district:
            await query.answer("Сначала выберите город и район.\nSelect a city and district first.")
            return

        # Получаем информацию о продукте
        product_info = get_product_by_name(base_name)
        if not product_info:
            await query.answer("Информация о товаре не найдена.\nProduct information not found.")
            return

        description = product_info.get("description", "Описание отсутствует.\nDescription is missing.")
        images = product_info.get("images", [])
        image_filename = images[0] if images else None
        name_en = product_info.get("name_en", "") if product_info else ""

        image_path = None
        if image_filename:
            image_filename = os.path.basename(image_filename)
            image_path = os.path.join("data", "images", image_filename)
            if not os.path.isfile(image_path):
                logging.error(f"Файл изображения не найден: {image_path}")
                image_path = None
            else:
                logging.info(f"Файл изображения найден: {image_path}")
        else:
            logging.info("Изображение не указано для продукта.\nNo image specified for product.")

        # Получаем доступные варианты
        variants = get_variants_for_base_name(base_name, city, district)
        if not variants:
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=(
                    f"Товар <b>{sanitize_html(base_name)}</b> в районе <b>{sanitize_html(district)}</b> "
                    f"города <b>{sanitize_html(city)}</b> закончился.\n"
                     f"The product <b>{sanitize_html(base_name)}</b> is out of stock in <b>{sanitize_html(district)}</b>, <b>{sanitize_html(city)}</b>."
                ),
                parse_mode="HTML"
            )
            await query.answer()
            return

        # Агрегируем одинаковые граммовки
        aggregated = defaultdict(lambda: {"price": None, "count": 0})
        for full_name, price in variants:
            splitted = full_name.rsplit(' ', 1)
            if len(splitted) == 2:
                _, short_variant = splitted
            else:
                short_variant = full_name
            if aggregated[short_variant]["price"] is None:
                aggregated[short_variant]["price"] = price
            aggregated[short_variant]["count"] += 1

        # Строим кнопки доступности
        inline_rows = []
        for short_variant, info in aggregated.items():
            price = info["price"]
            count = info["count"]
            text_btn = f"{short_variant} - {int(price)} USD [in stock {count}]"
            cb_data = f"buy_{base_name} {short_variant}"
            inline_rows.append([
                types.InlineKeyboardButton(text=text_btn, callback_data=cb_data)
            ])

        # Кнопка "Назад" (возвращаемся к списку товаров)
        inline_rows.append([
            types.InlineKeyboardButton(text="Назад / Back", callback_data="back_to_base_names")
        ])

        markup = types.InlineKeyboardMarkup(inline_keyboard=inline_rows)

        # Составляем текст для сообщения
        msg_text = f"<b>{sanitize_html(base_name)}</b>"
        if name_en:
            msg_text = f"<b>{sanitize_html(base_name)} ({name_en})</b>"
        msg_text += f"\n\n{description}\n\n"
        msg_text += f"Доступные клады в районе <b>{sanitize_html(district)}</b> города <b>{sanitize_html(city)}</b>:\n"
        msg_text += f"Available caches in <b>{sanitize_html(district)}</b>, <b>{sanitize_html(city)}</b>:\n"
        sent_message = await send_or_edit_message(
            bot=bot,
            chat_id=query.message.chat.id,
            text=msg_text,
            media_path=image_path,
            media_type="photo" if image_path else None,
            message_id=query.message.message_id,
            reply_markup=markup,
            parse_mode="HTML"
        )
        if sent_message:
           user_context[user_id]["product_card_message_id"] = sent_message.message_id
        else:
           user_context[user_id]["product_card_message_id"] = query.message.message_id
        await query.answer()
    except Exception as e:
        logging.error(f"show_product_card_handler: Ошибка - {e}")
    finally:
      db_manager.release_connection(conn)

def get_all_base_product_names(city: str, district: str) -> set:
    """
    Возвращает множество (set) всех «коротких» названий товаров для указанного города и района.
    Например, если в таблице есть «КЕТАМИН 1гр», «КЕТАМИН 2гр», вернётся «{'КЕТАМИН'}».
    """
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_all_base_product_names: не удалось подключиться к базе данных.")
        return set()

    table_names = [
        "paid_products",
        "gr_1_paid_products", "gr_2_paid_products", "gr_5_paid_products", "gr_10_paid_products",
        "item_1_paid_products", "item_2_paid_products", "item_5_paid_products", 
        "item_10_paid_products", "item_20_paid_products", "item_50_paid_products"
    ]
    base_names = set()
    try:
        cursor = conn.cursor()
        for table_name in table_names:
            query = f"""
                SELECT product_name
                FROM {table_name}
                WHERE city=? AND district=?
            """
            cursor.execute(query, (city, district))
            results = cursor.fetchall()
            for row in results:
                full_name = row[0]
                short_name = full_name.rsplit(' ', 1)[0]
                base_names.add(short_name)
        return base_names
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении коротких названий товаров: {e}")
        return set()
    finally:
        db_manager.release_connection(conn)

def get_variants_for_base_name(base_name: str, city: str, district: str):
    """
    Ищет записи product_name LIKE '{base_name}%' во всех таблицах, возвращает
    [(full_name, price), (full_name, price), ...].
    """
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_variants_for_base_name: БД недоступна.")
        return []
    table_names = [
        "paid_products",
        "gr_1_paid_products", "gr_2_paid_products", "gr_5_paid_products", "gr_10_paid_products",
        "item_1_paid_products", "item_2_paid_products", "item_5_paid_products",
        "item_10_paid_products", "item_20_paid_products", "item_50_paid_products"
    ]
    results = []
    try:
        cursor = conn.cursor()
        like_pattern = base_name + '%'
        for tbl in table_names:
            query = f"""
                SELECT product_name, price
                FROM {tbl}
                WHERE city=? AND district=? AND product_name LIKE ?
            """
            cursor.execute(query, (city, district, like_pattern))
            rows = cursor.fetchall()
            results.extend(rows)
    except sqlite3.Error as e:
        logging.error(f"get_variants_for_base_name: ошибка в БД: {e}")
    finally:
         db_manager.release_connection(conn)
    return results

async def product_buy_handler(
    query: types.CallbackQuery, bot: Bot, state: FSMContext
):
    """
    (ШАГ 3) Покупка конкретной граммовки: "buy_КЕТАМИН 1гр".
    """
    user_id = query.from_user.id
    data = await state.get_data()
    city = data.get("city")
    district = data.get("district")

    full_cmd = query.data.replace("buy_", "", 1).strip()  # "КЕТАМИН 1гр"
    conn = db_manager.get_connection()
    if not conn:
        logging.error("product_buy_handler: Не удалось получить соединение из пула.")
        return

    if not city or not district:
        await query.answer("Сначала выберите город и район.\nSelect a city and district first.")
        return

    try:
        # Получаем имя товара из полного названия
        base_name = full_cmd.rsplit(' ', 1)[0] if len(full_cmd.rsplit(' ', 1)) > 1 else full_cmd

        # Проверяем, есть ли товар
        product_info = get_location_info_from_paid_products(full_cmd, city, district)
        if not product_info:
            await bot.send_message(
                chat_id=query.message.chat.id,
                text=f"Товар <b>{sanitize_html(full_cmd)}</b> закончился.\nThe product <b>{sanitize_html(full_cmd)}</b> is out of stock.",
                parse_mode="HTML"
            )
            await query.answer()
            return

        # Получаем путь к изображению из контекста (можно игнорировать или использовать для дальнейших шагов)
        media_path = None # remove

        # Сохраняем данные для оплаты
        if user_id not in user_context:
             user_context[user_id] = {}
        user_context[user_id]["product_name"] = full_cmd
        user_context[user_id]["selected_city"] = city
        user_context[user_id]["selected_district"] = district
        # Получаем цену товара и сохраняем ее
        variants = get_variants_for_base_name(base_name, city, district)
        for full_name, price in variants:
            if full_name == full_cmd:
                user_context[user_id]["selected_product_price"] = price
                break

        # Получаем категорию товара
        product_category = get_product_category(base_name)
        if product_category:
            user_context[user_id]["selected_category"] = product_category
        else:
            logging.warning(f"Не удалось получить категорию товара для {base_name}\nFailed to get product category for {base_name}")
            user_context[user_id]["selected_category"] = None

        # Получаем ID продукта для будущих покупок
        all_products = get_all_products()
        product_id = next((item.get("id") for item in all_products if item.get("name") == base_name), None)

        if not product_id:
            logging.error(f"categories.py - product_buy_handler: ID товара не найден: {base_name}")
            await query.message.answer("Ошибка: ID товара не найден\nError: Product ID not found")
            return

        user_context[user_id]["selected_product_id"] = product_id
        user_context[user_id]["step"] = "payment_pending"
        await state.set_state(CategoryStates.PAYMENT_PENDING)

        # Импортируем обработчик оплаты
        from handlers.payment_handler import payment_options_handler

        await payment_options_handler(query.message, user_context=user_context[user_id])
        await query.answer()

    except Exception as e:
         logging.error(f"product_buy_handler: Ошибка - {e}")
    finally:
        db_manager.release_connection(conn)

async def back_to_base_names_handler(query: types.CallbackQuery, bot: Bot, state: FSMContext):
        """Возврат к списку коротких названий (шаг 1)."""
        from handlers.cities import get_city_image_path
        await show_all_base_product_names_handler(query, bot, state, get_city_image_path)
        await query.answer()

def register_category_handlers(dp: Dispatcher, bot: Bot):
    """
    Регистрируем новые хендлеры:
      - Показ списка товаров (короткие имена)
      - Показ карточки товара (изображение и описание) и доступных вариантов
      - Покупка
      - "Назад"
    """
    
    # (ШАГ 1) Показ коротких названий (вызов через callback_data="show_base_products" или напрямую)
    @dp.callback_query(lambda q: q.data == "show_base_products")
    async def handle_show_base_products_callback(query: types.CallbackQuery, bot: Bot, state: FSMContext):
        from handlers.cities import get_city_image_path
        await show_all_base_product_names_handler(query, bot, state, get_city_image_path)

    # (ШАГ 2) Пользователь выбрал товар (показываем карточку)
    @dp.callback_query(lambda q: q.data.startswith("select_base_"))
    async def handle_select_base_callback(query: types.CallbackQuery, bot: Bot, state: FSMContext):
        await show_product_card_handler(query, bot, state)

    # (ШАГ 3) Покупка
    @dp.callback_query(lambda q: q.data.startswith("buy_"))
    async def handle_buy_callback(query: types.CallbackQuery, bot: Bot, state: FSMContext):
        await product_buy_handler(query, bot, state)

    # Назад к выбору товаров
    @dp.callback_query(lambda q: q.data == "back_to_base_names")
    async def handle_back_to_base_names(query: types.CallbackQuery, bot: Bot, state: FSMContext):
        await back_to_base_names_handler(query, bot, state)

    # Назад к выбору районов
    @dp.callback_query(lambda q: q.data == "back_to_districts")
    async def back_to_districts(query: types.CallbackQuery, bot: Bot, state: FSMContext):
         """Обрабатывает навигацию назад из списка товаров к списку районов."""
         from handlers.cities import send_districts_message
         user_id = query.from_user.id
         data = await state.get_data()
         city = data.get("city")
         selected_city = data.get("city")
         
         logging.info(f"categories.py - back_to_districts: User {user_id} going back to district selection for {selected_city}")
         conn = db_manager.get_connection()
         if not conn:
            logging.error("categories.py - back_to_districts: Не удалось получить соединение из пула.")
            return
         try:
             if user_id not in user_context:
                 user_context[user_id] = {}
             
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
                     chat_id=query.message.chat.id,
                     selected_city=selected_city,
                     media_path=media_path,
                     districts_keyboard=districts_keyboard.as_markup(),
                     message_id=user_context[user_id].get("district_message_id") # передаем message_id
                 )
             else:
                 # Отправляем сообщение об отсутствии районов
                 no_districts_message_id = user_context[user_id].get("no_products_message_id")
                 if no_districts_message_id:
                     try:
                         await bot.edit_message_text(
                             chat_id=query.message.chat.id,
                             message_id=no_districts_message_id,
                              text=f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.",
                             parse_mode="HTML"
                         )
                     except TelegramBadRequest:
                          sent_message = await query.message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                          user_context[user_id]["no_products_message_id"] = sent_message.message_id
                 else:
                     sent_message = await query.message.answer(f"Для города <b>{selected_city}</b> нет доступных районов.\nNo districts are available for <b>{selected_city}</b>.", parse_mode="HTML")
                     user_context[user_id]["no_products_message_id"] = sent_message.message_id
             
             user_context[user_id]["step"] = "districts_list"
             await query.answer()
         except Exception as e:
             logging.error(f"back_to_districts: Ошибка - {e}")
         finally:
           db_manager.release_connection(conn)