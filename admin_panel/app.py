from flask import Flask, jsonify, request, send_from_directory, render_template, url_for, redirect, session
import os
import base64
import uuid
import asyncio
from flask_cors import CORS
from sys import path
import logging
import json
from functools import wraps
import telegram
from telegram.ext import Application

BOT_TOKEN = "7641588058:AAGjlfeuWRjzoRYh1jC4Kh5NeHpz0qH5_co" # Вставьте свой токен от BotFather
bot = telegram.Bot(token=BOT_TOKEN)
application = Application.builder().token(BOT_TOKEN).build()  # Создаем Application

# Настройка путей к директориям проекта
ADMIN_PANEL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ADMIN_PANEL_DIR)
if PROJECT_ROOT not in path:
    path.append(PROJECT_ROOT)

# Импорт функций для работы с базой данных
from database import (
    db_manager, get_all_users, get_user, add_user, set_paid_products_original_price, update_paid_products_prices, update_username_query, delete_user,
    get_user_balance, get_referral_count, update_referral_purchases_amount,
    get_referral_purchases_amount, get_referral_purchases_count, get_user_tickets, add_ticket,
    execute_query, get_available_products, get_paid_products_table_name,
    add_paid_product
)

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Инициализация Flask приложения
app = Flask(__name__, static_folder='templates')
CORS(app)
app.config['JSON_AS_ASCII'] = False
app.secret_key = os.urandom(24)  # Ключ для сессий, должен быть случайным и секретным. 

# Настройка директории для хранения изображений
IMAGE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    '..',
    'data',
    'images'
))

# Инициализация DB при старте flask
with app.app_context():
    db_manager.create_tables()


# Подключаемся к базе данных при старте приложения
@app.before_request
def before_request():
    # initialize_db() # <-- УДАЛИТЬ
    # Проверяем, если это не запрос на авторизацию и пользователь не авторизован,
    # И также не запрос на статические файлы
    if request.endpoint != 'login' and not session.get('logged_in') and not request.path.startswith('/data/images/') and not request.path.startswith('/templates/'):
         return redirect(url_for('login')) # Перенаправляем на страницу входа
# Закрываем пул соединений
@app.teardown_appcontext
def teardown_db(exception):
   db_manager.close_all_connections()
# Добавим функцию для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Функция для получения локаций продукта из БД
def get_product_locations_from_db(product_id):
    """Получает локации продукта из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_product_locations_from_db: Не удалось получить соединение из пула.")
        return []
    try:
        query = """
            SELECT l.city, l.district
            FROM locations l
            JOIN product_locations pl ON l.id = pl.location_id
            WHERE pl.product_id = ?
        """
        locations = execute_query(query, (product_id,), fetch=True)
        return [
            {
                "city": loc[0],
                "district": loc[1]
            } for loc in locations]
    finally:
        db_manager.release_connection(conn)

# Функция для получения продукта с локациями
def get_product_with_locations(product_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_product_with_locations: Не удалось получить соединение из пула.")
        return None
    try:
        query = "SELECT * FROM products WHERE id = ?"
        product_row = execute_query(query, (product_id,), fetch=True, fetch_one_flag=True)
        if not product_row:
            return None
        locations = get_product_locations_from_db(product_id)
        return {
           "id": product_row[0],
           "name": product_row[1],
           "category_id": product_row[2],
           "price": product_row[3],
           "description": product_row[4],
           "image": product_row[5],
           "locations": locations
        }
    except Exception as e:
         logging.error(f"get_product_with_locations: Ошибка - {e}")
         return None
    finally:
       db_manager.release_connection(conn)

# ========================================================================
# ВСТАВЬТЕ СВОЙ ЛОГИН И ПАРОЛЬ ЗДЕСЬ 
# ========================================================================
ADMIN_USERNAME = "Admin"  
ADMIN_PASSWORD = "sdgjgDFddRrg5dSS45SDfg477ghR47"
# ========================================================================

# Маршрут для авторизации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True  # Пользователь авторизован
            return redirect(url_for('index'))  # Перенаправляем на главную
        else:
            return render_template('login.html', error='Неверный логин или пароль')  # Ошибка
    return render_template('login.html')  # Страница входа

# Маршрут для отдачи изображений
@app.route('/data/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(IMAGE_DIR, filename)



@app.route('/mass-message', methods=['GET', 'POST'])
@login_required
def mass_message():
    if request.method == 'POST':
        message_text = request.form.get('message')
        image = request.files.get('image')

        if not message_text:
            logging.warning("Не было текста сообщения")
            return render_template('mass_message.html', error="Нет текста сообщения")
        conn = db_manager.get_connection()
        if not conn:
             return "Не удалось подключиться к базе данных."
        try:
            users = get_all_users()
            if not users:
                logging.warning("Нет зарегистрированных пользователей")
                return render_template('mass_message.html', error="Нет зарегистрированных пользователей")

            sent_count = 0
            not_sent_count = 0

            image_data = None
            if image and image.filename != '':
                logging.info("Читаем данные изображения")
                image_data = image.read()
                logging.debug(f"Размер изображения: {len(image_data)} байт")


            async def send_message_to_user(user_id, message_text, image_data):
                nonlocal sent_count, not_sent_count
                try:
                    logging.info(f"Отправка сообщения пользователю: {user_id}")
                    if image_data:
                       logging.debug(f"Отправка фото пользователю: {user_id}")
                       await application.bot.send_photo(chat_id=user_id, photo=image_data, caption=message_text, parse_mode="Markdown")
                    else:
                        logging.debug(f"Отправка текста пользователю: {user_id}")
                        await application.bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
                    sent_count += 1
                    logging.info(f"Сообщение успешно отправлено пользователю: {user_id}")
                except telegram.error.TelegramError as e:
                    logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
                    not_sent_count += 1
                except asyncio.TimeoutError as e:
                    logging.error(f"Таймаут при отправке сообщения пользователю {user_id}: {e}")
                    not_sent_count += 1
                except Exception as e:
                   logging.error(f"Непредвиденная ошибка при отправке сообщения пользователю {user_id}: {e}")
                   not_sent_count += 1

            async def main():
                for user in users:
                     await send_message_to_user(user[0], message_text, image_data)

            asyncio.run(main())

            return render_template('mass_message.html', message="Сообщения отправлены", sent_count=sent_count, not_sent_count=not_sent_count)
        except Exception as e:
              logging.error(f"Error in mass_message endpoint: {str(e)}")
              return "An error occurred. Check the logs for details."
        finally:
            db_manager.release_connection(conn)
    return render_template('mass_message.html')

# Inside the index route
@app.route("/")
@login_required
def index():
    conn = db_manager.get_connection()
    if not conn:
        return "Не удалось подключиться к базе данных."
    try:
        query = """
            SELECT
                p.id,
                p.name,
                p.category_id,
                c.name AS category_name,
                p.price,
                p.description,
                p.image
            FROM products p
            JOIN categories c ON p.category_id = c.id
        """
        products = execute_query(query, fetch=True)
        products_list = []
        for product in products:
            product_id = product[0]
            # Fetch grouped and sorted product locations with detailed counts
            product_locations_grouped = get_grouped_product_locations_with_detailed_counts(product_id)
            products_list.append({
                "id": product_id,
                "name": product[1],
                "category_id": product[2],
                "category_name": product[3],
                "price": product[4],
                "description": product[5],
                "image": product[6],
                "locations_grouped": product_locations_grouped
            })
        return render_template("index.html", products=products_list)
    except Exception as e:
        print(f"Ошибка: {e}")
        return "Ошибка при загрузке продуктов."
    finally:
        db_manager.release_connection(conn)
    
def get_grouped_product_locations_with_detailed_counts(product_id):
    """
    Retrieves locations and their detailed counts (including gram/item type and value) for a product
    from the database, grouped by city and ordered by city and district.
    Returns a list of lists, where each sublist contains locations for a specific city.
    """
    locations_with_details = []
    gram_products = [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]
    item_products = [2, 8, 9, 10, 11]
    
    if product_id in gram_products:
        for gram in [1, 2, 5, 10]:
            table_name = get_paid_products_table_name("gram", gram)
            query = f"""
              SELECT city, district, COUNT(*) AS count
              FROM {table_name}
              WHERE product_name LIKE (SELECT name || '%' FROM products WHERE id=?)
              GROUP BY city, district
              ORDER BY city, district
            """
            locations_from_table = execute_query(query, (product_id,), fetch=True)
            if locations_from_table:
               for loc in locations_from_table:
                 locations_with_details.append(
                     {
                         "city": loc[0],
                         "district": loc[1],
                         "count": loc[2],
                         "type": "гр",
                         "value": gram
                       }
                 )

    elif product_id in item_products:
        for item in [1, 2, 5, 10, 20, 50]:
            table_name = get_paid_products_table_name("item", item)
            query = f"""
                SELECT city, district, COUNT(*) AS count
                FROM {table_name}
                WHERE product_name LIKE (SELECT name || '%' FROM products WHERE id=?)
                 GROUP BY city, district
                 ORDER BY city, district
            """
            locations_from_table = execute_query(query, (product_id,), fetch=True)
            if locations_from_table:
              for loc in locations_from_table:
                 locations_with_details.append(
                     {
                         "city": loc[0],
                         "district": loc[1],
                         "count": loc[2],
                         "type": "шт",
                         "value": item
                       }
                 )

    grouped_locations = {}
    for location in locations_with_details:
        city = location['city']
        if city not in grouped_locations:
            grouped_locations[city] = []
        grouped_locations[city].append(location)
    
    return list(grouped_locations.values())

# Маршрут для отдачи статических файлов
@app.route('/templates/<path:filename>')
def serve_templates(filename):
    return send_from_directory(app.static_folder, filename)

# Маршрут для страницы редактирования продукта
@app.route("/product", methods=["GET"])
@app.route("/product/<int:product_id>", methods=["GET"])
@login_required
def product(product_id=None):
    conn = db_manager.get_connection()
    if not conn:
         logging.error(f"product: Не удалось получить соединение из пула.")
         return "Не удалось подключиться к базе данных."
    try:
        categories = execute_query("SELECT name FROM categories", fetch=True)
        categories = [row[0] for row in categories]
        locations = execute_query("SELECT city, district FROM locations", fetch=True)
        locations = {}
        for city, district in locations:
            locations.setdefault(city, []).append(district)
        product_obj = None
        if product_id:
            product_obj = get_product_with_locations(product_id)
        return render_template("product_editor.html",
                               product=product_obj,
                               categories=categories,
                               locations=locations,
                               product_locations=product_obj["locations"] if product_obj else [])
    except Exception as e:
      logging.error(f"Error in product endpoint: {e}")
      return "An error occurred. Check the logs for details.", 500
    finally:
        db_manager.release_connection(conn)

# Функция для генерации ID продукта
def generate_id():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("generate_id: Не удалось получить соединение из пула.")
        return None
    try:
       max_id = execute_query("SELECT MAX(id) FROM products", fetch=True, fetch_one_flag=True)
       return max_id[0] + 1 if max_id and max_id[0] else 1
    except Exception as e:
        logging.error(f"generate_id: Ошибка - {e}")
    finally:
        db_manager.release_connection(conn)


# Маршрут для добавления нового продукта
@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    logging.debug("Attempting to add a product")
    conn = db_manager.get_connection()
    if not conn:
        logging.error("add_product: Не удалось получить соединение из пула.")
        return "Не удалось подключиться к базе данных."
    try:
        product_data = request.get_json()
        image_path = ""
        if "image" in product_data and product_data["image"]:
            image_res = upload_image(product_data["image"])
            if "error" not in image_res:
                image_path = image_res['imagePath']
        query = "SELECT id FROM categories WHERE name = ?"
        category_id_row = execute_query(query, (product_data.get("category"),), fetch=True, fetch_one_flag=True)
        if not category_id_row:
            return jsonify({'error': 'Category not found in DB'}), 400
        category_id = category_id_row[0]
        new_product_id = generate_id()
        query = """
            INSERT INTO products (id, name, category_id, price, description, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        execute_query(query, (
            new_product_id,
            product_data.get("name"),
            category_id,
            product_data.get("price"),
            product_data.get("description"),  # Сохраняем как есть (сырой HTML)
            image_path
        ))
        for location_data in product_data.get("locations", []):
            city = location_data.get('city')
            district = location_data.get('district')
            if not city or not district:
                continue
            query = "SELECT id FROM locations WHERE city = ? AND district = ?"
            location_id_result = execute_query(query, (city, district), fetch=True, fetch_one_flag=True)
            if location_id_result:
                location_id = location_id_result[0]
                query = """
                    INSERT INTO product_locations (product_id, location_id)
                    VALUES (?, ?)
                """
                execute_query(query, (new_product_id, location_id))

        return jsonify({'message': 'Product added successfully'}), 200
    except Exception as e:
        logging.error(f"Error adding product: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db_manager.release_connection(conn)

# Маршрут для обновления существующего продукта
@app.route('/update-product/<int:product_id>', methods=['PUT'])
@login_required
def update_product(product_id):
    logging.debug(f"Attempting to update product with id: {product_id}")
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"update_product: Не удалось получить соединение из пула.")
        return "Не удалось подключиться к базе данных."
    try:
        product_data = request.get_json()
        if not product_data:
            return jsonify({'error': 'No data provided'}), 400
        query = "SELECT image FROM products WHERE id = ?"
        old_image_path_row = execute_query(query, (product_id,), fetch=True, fetch_one_flag=True)
        old_image_path = old_image_path_row[0] if old_image_path_row and old_image_path_row[0] else ""
        if "image" in product_data and product_data["image"]:
            image_res = upload_image(product_data["image"])
            if "error" not in image_res:
                image_path = image_res['imagePath']
            else:
                return jsonify(image_res), 500
        else:
            image_path = old_image_path
        query = "SELECT id FROM categories WHERE name = ?"
        cat_row = execute_query(query, (product_data.get("category"),), fetch=True, fetch_one_flag=True)
        if not cat_row:
            return jsonify({'error': 'Category not found in DB'}), 400
        category_id = cat_row[0]
        query = """
            UPDATE products
            SET name = ?, category_id = ?, price = ?, description = ?, image = ?
            WHERE id = ?
        """
        execute_query(query, (
            product_data.get("name"),
            category_id,
            product_data.get("price"),
            product_data.get("description"), # Сохраняем как есть (сырой HTML)
            image_path,
            product_id
        ))
        execute_query("DELETE FROM product_locations WHERE product_id = ?", (product_id,))
        for location_data in product_data.get("locations", []):
            city = location_data.get('city')
            district = location_data.get('district')
            if not city or not district:
                continue
            query = "SELECT id FROM locations WHERE city=? AND district=?"
            loc_id_row = execute_query(query, (city, district), fetch=True, fetch_one_flag=True)
            if loc_id_row:
                location_id = loc_id_row[0]
                query = """
                    INSERT INTO product_locations (product_id, location_id)
                    VALUES (?, ?)
                """
                execute_query(query, (product_id, location_id))

        logging.debug(f"Product with id: {product_id} updated successfully")
        return jsonify({'message': 'Product updated successfully', 'success': True}), 200
    except Exception as e:
        logging.error(f"Error updating product with id: {product_id} - {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
       db_manager.release_connection(conn)


@app.route("/structured-products")
@login_required
def structured_products_page():
    print(">>> Функция structured_products_page ВЫЗВАНА!")  # <--- Добавили отладочный вывод перед функцией
    conn = db_manager.get_connection()
    if not conn:
        logging.error("structured_products_page: Не удалось получить соединение из пула.")
        return "Не удалось подключиться к базе данных."
    try:
        structured_data = get_structured_product_data()
        print(">>> Данные structured_data успешно получены.") # <--- Добавили отладочный вывод внутри try
        return render_template("structured_products.html", structured_data=structured_data)
    except Exception as e:
        logging.error(f"Error in structured_products_page endpoint: {e}")
        print(f">>> ОШИБКА в structured_products_page: {e}") # <--- Добавили отладочный вывод в except
        return "Ошибка при загрузке структурированных данных.", 500
    finally:
        db_manager.release_connection(conn)

def get_structured_product_data():
    """
    Получает структурированные данные о товарах для отображения на странице.
    Структура: {
        'Город': {
            'Район': {
                'Название товара': {'type': 'гр/шт', 'value': '1/2/5/10...', 'count': количество}
            }
        }
    }
    """
    structured_data = {}
    gram_products = [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]
    item_products = [2, 8, 9, 10, 11]

    # Получаем все товары, чтобы итерироваться по ним и собрать данные о кладах
    query_products = "SELECT id, name, category_id, name FROM products" # Добавил name для удобства
    all_products = execute_query(query_products, fetch=True)

    if not all_products:
        return structured_data # Возвращаем пустой словарь, если нет товаров

    for product_id, product_name, category_id, product_name_full in all_products: # Используем product_name_full
        product_structured_data = {} # Данные для текущего товара

        if product_id in gram_products:
            for gram in [1, 2, 5, 10]:
                table_name = get_paid_products_table_name("gram", gram)
                query = f"""
                    SELECT city, district, COUNT(*) AS count
                    FROM {table_name}
                    WHERE product_name LIKE ?
                    GROUP BY city, district
                """
                locations_data = execute_query(query, (product_name_full + '%',), fetch=True) # Используем product_name_full

                for city, district, count in locations_data:
                    if city not in structured_data:
                        structured_data[city] = {}
                    if district not in structured_data[city]:
                        structured_data[city][district] = {}
                    product_key = f"{product_name_full} ({gram}гр)" # Используем product_name_full
                    product_structured_data[product_key] = {'type': 'гр', 'value': gram, 'count': count}

        elif product_id in item_products:
            for item in [1, 2, 5, 10, 20, 50]:
                table_name = get_paid_products_table_name("item", item)
                query = f"""
                    SELECT city, district, COUNT(*) AS count
                    FROM {table_name}
                    WHERE product_name LIKE ?
                    GROUP BY city, district
                """
                locations_data = execute_query(query, (product_name_full + '%',), fetch=True) # Используем product_name_full

                for city, district, count in locations_data:
                    if city not in structured_data:
                        structured_data[city] = {}
                    if district not in structured_data[city]:
                        structured_data[city][district] = {}
                    product_key = f"{product_name_full} ({item}шт)" # Используем product_name_full
                    product_structured_data[product_key] = {'type': 'шт', 'value': item, 'count': count}

        # Объединяем данные для текущего товара в общую структуру
        for city, districts in structured_data.items():
            for district in districts:
                if district not in structured_data[city]: # Проверка на случай, если район не был добавлен ранее
                    structured_data[city][district] = {}
                structured_data[city][district].update(product_structured_data) # Добавляем данные о текущем товаре

    return structured_data



# Маршрут для обновления цены продукта
@app.route('/update-product-prices', methods=['POST'])
@login_required
def update_product_prices():
    conn = db_manager.get_connection()
    if not conn:
         logging.error("update_product_prices: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        product_name = data.get('product_name')
        category_name = data.get('category_name')
        city = data.get('city')
        discount = data.get('discount')

        if not all([product_name, category_name, city, discount]):
           return jsonify({'error': 'All fields (product_name, category_name, city, discount) are required'}), 400

        update_result = update_paid_products_prices(product_name, category_name, city, discount)

        if update_result:
            return jsonify({'message': 'Цены на товары успешно обновлены'}), 200
        else:
            return jsonify({'error': 'Не удалось обновить цены на товары'}), 500


    except Exception as e:
         logging.error(f"Error updating product prices: {str(e)}")
         return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)


# Маршрут для обновления цены продукта до оригинальной
@app.route('/set-original-price', methods=['POST'])
@login_required
def set_original_price():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("set_original_price: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
    
        product_name = data.get('product_name')
        category_name = data.get('category_name')
        city = data.get('city')

        if not all([product_name, category_name, city]):
          return jsonify({'error': 'All fields (product_name, category_name, city) are required'}), 400

        update_result = set_paid_products_original_price(product_name, category_name, city)

        if update_result:
            return jsonify({'message': 'Цены на товары успешно установлены в оригинальные'}), 200
        else:
            return jsonify({'error': 'Не удалось установить цены в оригинальные'}), 500

    except Exception as e:
        logging.error(f"Error setting original product prices: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)

# Функция для загрузки изображения
def upload_image(image_data):
    if not image_data:
        return {'error': 'No image data provided'}
    try:
        image_format = image_data.split(';')[0].split('/')[1]
        image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        image_name = f"{uuid.uuid4()}.{image_format}"
        # Формируем путь с прямыми слешами
        image_path = f"/data/images/{image_name}"
        full_image_path = os.path.join(IMAGE_DIR, image_name)
        with open(full_image_path, 'wb') as f:
            f.write(image_bytes)
        logging.debug(f"Image saved to: {full_image_path}")
        return {'imagePath': image_path}
    except Exception as e:
        logging.error(f"Error during image processing: {str(e)}")
        return {'error': 'Failed to process image'}



@app.route("/get_district_products")
@login_required
def get_district_products():
    """
    Возвращает список товаров для выбранного города и района.
    """
    city = request.args.get('city')
    district = request.args.get('district')

    if not city or not district:
        return jsonify({'error': 'Необходимы параметры city и district'}), 400

    structured_data = get_structured_product_data() # Получаем все структурированные данные

    if city not in structured_data or district not in structured_data[city]:
        return jsonify([]), 200 # Возвращаем пустой список, если нет данных для города/района

    district_products_data = structured_data[city][district]
    products_list = []
    for product_name_full, product_info in district_products_data.items():
        products_list.append({
            'name': product_name_full, # Полное имя товара (с граммовкой/штуками)
            'count': product_info['count'],
            'type': product_info['type']
        })

    return jsonify(products_list)


@app.route("/get_product_details")
@login_required
def get_product_details():
    """
    Возвращает детали кладов для выбранного товара, города и района.
    """
    city = request.args.get('city')
    district = request.args.get('district')
    product_name_query = request.args.get('productName')

    if not city or not district or not product_name_query:
        return jsonify({'error': 'Необходимы параметры city, district и productName'}), 400

    product_name = product_name_query.split('(')[0].strip() # Извлекаем чистое имя продукта
    category_name = None # Вам может понадобиться логика для определения category_name

    # Получаем ID продукта по имени
    query_product_id = "SELECT id, category_id, name FROM products WHERE name = ?" # <--- Добавил name
    product_id_result = execute_query(query_product_id, (product_name,), fetch=True, fetch_one_flag=True)
    if not product_id_result:
        return jsonify({'error': 'Продукт не найден'}), 404
    product_id, category_id, full_product_name = product_id_result # <--- Получаем full_product_name

    # Получаем имя категории по ID
    query_category_name = "SELECT name FROM categories WHERE id = ?"
    category_name_result = execute_query(query_category_name, (category_id,), fetch=True, fetch_one_flag=True)
    if category_name_result:
        category_name = category_name_result[0]
    else:
        return jsonify({'error': 'Категория не найдена'}), 404


    paid_products = get_paid_products_with_images(full_product_name, category_name, product_id) # <--- Используем full_product_name

    # Фильтруем результаты по городу и району
    filtered_products = [
        p for p in paid_products
        if p['city'] == city and p['district'] == district and p['name'] == full_product_name # <--- Используем full_product_name для фильтрации
    ]

    # Форматируем данные для ответа JSON
    product_details = []
    for product in filtered_products:
        product_details.append({
            'id': product['id'],
            'instruction': product['instruction'],
            'images': product['images']
        })

    return jsonify(product_details)



@app.route("/orders")
@login_required
def orders():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("orders: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        orders = execute_query("SELECT * FROM orders", fetch=True)
        # Преобразуйте данные в формат, который можно сериализовать в JSON
        # Например, список словарей:
        orders_list = []
        if orders:
            for order in orders:
                orders_list.append({
                    "id": order[0],
                    "user_id": order[1],
                    "product_name": order[2],
                    "category": order[3],
                    "city": order[4],
                    "district": order[5],
                    "status": order[6],
                    "quantity": order[7],
                    "payment_id": order[8]
                })
        return jsonify({'orders': orders_list, 'ensure_ascii': False})
    except Exception as e:
        logging.error(f"Error in orders endpoint: {e}")
        return jsonify({'error': str(e), 'ensure_ascii': False}), 500
    finally:
      db_manager.release_connection(conn)

@app.route("/test_orders")
@login_required
def test_orders():
    return render_template("test_orders.html")

# Маршрут для удаления продукта
@app.route("/delete/<int:product_id>", methods=["GET"])
@login_required
def delete_product(product_id):
    conn = db_manager.get_connection()
    if not conn:
         logging.error(f"delete_product: Не удалось получить соединение из пула.")
         return "Не удалось подключиться к базе данных."
    try:
        execute_query("DELETE FROM products WHERE id = ?", (product_id,))
        execute_query("DELETE FROM product_locations WHERE product_id = ?", (product_id,))
        return redirect(url_for("index"))
    except Exception as e:
      logging.error(f"Error in delete_product endpoint: {e}")
      return "An error occurred. Check the logs for details.", 500
    finally:
        db_manager.release_connection(conn)
# ----- ПЛАТНЫЕ ТОВАРЫ -----

def get_paid_products_with_images(product_name, category_name, product_id):
    """Получает локации продукта из базы данных с учетом граммовки."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_paid_products_with_images: Не удалось получить соединение из пула.")
        return []
    try:
        all_paid_products = []
        gram_products = [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]
        item_products = [2, 8, 9, 10, 11]

        if product_id in gram_products:
            for gram in [1, 2, 5, 10]:
                table_name = get_paid_products_table_name("gram", gram)
                query = f"""
                    SELECT
                        pp.id,
                        pp.product_name,
                        pp.city,
                        pp.district,
                        pp.instruction,
                        pp.images,
                        pp.price,
                        '{table_name}' as table_name,
                        '{gram}' as gram
                    FROM {table_name} pp
                    WHERE pp.product_name LIKE ? AND pp.category_name = ?
                """
                logging.debug(f"Executing query: {query} with params: {(product_name + '%', category_name)}")
                paid_rows = execute_query(query, (product_name + '%', category_name), fetch=True)
                logging.debug(f"Query result for {table_name}: {paid_rows}")
                if paid_rows: # <--- ПРОВЕРКА НА None
                    for row in paid_rows:
                        all_paid_products.append({
                            "id": row[0],
                            "name": row[1],
                            "city": row[2],
                            "district": row[3],
                            "instruction": row[4],
                            "images": json.loads(row[5]) if row[5] else [],
                            "price": row[6],
                            "table_name": row[7],
                            "gram": row[8],
                            "item": None
                        })

        elif product_id in item_products:
            for item in [1, 2, 5, 10, 20, 50]:
                table_name = get_paid_products_table_name("item", item)
                query = f"""
                    SELECT
                        pp.id,
                        pp.product_name,
                         pp.city,
                        pp.district,
                        pp.instruction,
                        pp.images,
                         pp.price,
                         '{table_name}' as table_name,
                        '{item}' as item
                    FROM {table_name} pp
                    WHERE pp.product_name LIKE ? AND pp.category_name = ?
                """
                logging.debug(f"Executing query: {query} with params: {(product_name + '%', category_name)}")
                paid_rows = execute_query(query, (product_name + '%', category_name), fetch=True)
                logging.debug(f"Query result for {table_name}: {paid_rows}")
                if paid_rows: # <--- ПРОВЕРКА НА None
                    for row in paid_rows:
                        all_paid_products.append({
                            "id": row[0],
                           "name": row[1],
                            "city": row[2],
                            "district": row[3],
                            "instruction": row[4],
                            "images": json.loads(row[5]) if row[5] else [],
                             "price": row[6],
                            "table_name": row[7],
                             "item": row[8],
                            "gram": None
                        })
        return all_paid_products
    except Exception as e:
        logging.error(f"get_paid_products_with_images: Ошибка - {e}")
        return []
    finally:
       db_manager.release_connection(conn)

# Маршрут для получения всех локаций
@app.route('/locations', methods=['GET'])
@login_required
def get_locations():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_locations: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        locations = execute_query("SELECT id, city, district FROM locations", fetch=True)
        locations_list = []
        for row in locations:
            locations_list.append({
                "id": row[0],
                "city": row[1],
                "district": row[2]
            })
        return jsonify({'locations': locations_list, 'ensure_ascii': False}), 200
    except Exception as e:
        logging.error(f"Error fetching locations: {str(e)}")
        return jsonify({'error': str(e), 'ensure_ascii': False}), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для добавления новой локации
@app.route('/add-location', methods=['POST'])
@login_required
def add_location():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("add_location: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        location_data = request.get_json()
        if not location_data or 'city' not in location_data or 'district' not in location_data:
            return jsonify({'error': 'City and district are required'}), 400
        city = location_data.get('city')
        district = location_data.get('district')
        query = "INSERT INTO locations (city, district) VALUES (?, ?)"
        execute_query(query, (city, district))
        return jsonify({'message': 'Location added successfully'}), 201
    except Exception as e:
        logging.error(f"Error adding location: {str(e)}")
        return jsonify({'error': str(e)}, ensure_ascii=False), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для обновления локации
@app.route('/update-location/<int:location_id>', methods=['PUT'])
@login_required
def update_location(location_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("update_location: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        location_data = request.get_json()
        if not location_data or 'city' not in location_data or 'district' not in location_data:
            return jsonify({'error': 'City and district are required'}), 400
        city = location_data.get('city')
        district = location_data.get('district')
        query = "UPDATE locations SET city = ?, district = ? WHERE id = ?"
        cursor = execute_query(query, (city, district, location_id))
        if cursor.rowcount == 0:
            return jsonify({'error': 'Location not found'}), 404
        return jsonify({'message': 'Location updated successfully'}), 200
    except Exception as e:
        logging.error(f"Error updating location {location_id}: {str(e)}")
        return jsonify({'error': str(e)}, ensure_ascii=False), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для удаления локации
@app.route('/delete-location/<int:location_id>', methods=['DELETE'])
@login_required
def delete_location(location_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("delete_location: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        query = "DELETE FROM locations WHERE id = ?"
        cursor = execute_query(query, (location_id,))
        if cursor.rowcount == 0:
            return jsonify({'error': 'Location not found'}), 404
        return jsonify({'message': 'Location deleted successfully'}), 200
    except Exception as e:
        logging.error(f"Error deleting location {location_id}: {str(e)}")
        return jsonify({'error': str(e)}, ensure_ascii=False), 500
    finally:
       db_manager.release_connection(conn)

@app.route('/sold-orders-part1')
@login_required
def sold_orders_part1():
      return render_template('sold_orders_part1.html')


@app.route('/sold-orders-part2')
@login_required
def sold_orders_part2():
      return render_template('sold_orders_part2.html')

@app.route('/sold-orders', methods=['GET'])
@login_required
def get_sold_orders():
    conn = db_manager.get_connection()
    if not conn:
         logging.error("get_sold_orders: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        sold_orders = execute_query("""
            SELECT 
                product_name,
                instruction,
                city,
                district,
                username,
                price,
                sale_date
            FROM sold_products
        """, fetch=True)
        sold_orders_list = []
        if sold_orders:
            for order in sold_orders:
                sold_orders_list.append({
                   "product_name": order[0],
                   "instruction": order[1],
                   "city": order[2],
                   "district": order[3],
                   "username": order[4],
                   "price": order[5],
                   "sale_date": order[6]
               })

        return jsonify({'sold_orders': sold_orders_list, 'ensure_ascii': False}), 200
    except Exception as e:
        logging.error(f"Error fetching sold orders: {str(e)}")
        return jsonify({'error': str(e), 'ensure_ascii': False}), 500
    finally:
      db_manager.release_connection(conn)

@app.route('/update-user-balance/<int:user_id>', methods=['PUT'])
@login_required
def update_user_balance(user_id):
    conn = db_manager.get_connection()
    if not conn:
         logging.error("update_user_balance: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        data = request.get_json()
        new_balance = data.get('new_balance')
        if new_balance is None:
             return jsonify({'error': 'New balance not provided'}), 400

        query = "UPDATE users SET balance = ? WHERE user_id = ?"
        execute_query(query, (new_balance, user_id))
        return jsonify({'message': f'Balance for user {user_id} updated to {new_balance}'}), 200
    except Exception as e:
        logging.error(f"Error updating user balance for user {user_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)

@app.route("/delete-order/<string:order_id>", methods=["DELETE"])
@login_required
def delete_order(order_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("delete_order: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        logging.info(f"Попытка удаления заказа с ID: {order_id}")
        query = "DELETE FROM orders WHERE id=?"
        cursor = execute_query(query, (order_id,), fetch=False, fetch_one_flag=False)
        if cursor.rowcount == 0:
            logging.warning(f"Не найден заказ с ID {order_id} для удаления")
            return jsonify({'error': 'Order not found'}), 404
        return jsonify({'message': 'Order deleted successfully'}), 200
    except Exception as e:
        logging.error(f"Ошибка при удалении заказа с ID {order_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)

# Маршрут для страницы платных товаров
@app.route("/paid-products")
@login_required
def paid_products():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("paid_products: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
         all_paid_products = {}
         categories = execute_query("SELECT name FROM categories", fetch=True)
         cat_list = [row[0] for row in categories]
         for cat in cat_list:
            query = "SELECT id, name FROM products WHERE category_id = (SELECT id FROM categories WHERE name = ?)"
            products = execute_query(query, (cat,), fetch=True)
            if products:  # <--- ПРОВЕРКА НА None
                for product in products:
                    product_name = product[1]
                    product_id = product[0]
                    all_paid_products[product_name] = get_paid_products_with_images(product_name, cat, product_id)
         locations = execute_query("SELECT city, district FROM locations", fetch=True)
         locs = {}
         for city, district in locations:
            locs.setdefault(city, []).append(district)
         return render_template("paid_products_editor.html",
                               paid_products=all_paid_products,
                               locations=locs,
                               categories=cat_list)
    except Exception as e:
        error_message = f"Error in paid_products endpoint: {e}"
        logging.error(error_message)
        return f"An error occurred: {error_message}", 500
    finally:
       db_manager.release_connection(conn)

@app.route('/users', methods=['GET'])
@login_required
def get_users():
    conn = db_manager.get_connection()
    if not conn:
         logging.error("get_users: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        users = execute_query("SELECT user_id, referral_code, referred_by, balance, username FROM users", fetch=True)
        users_list = []
        if users:
            for user in users:
                users_list.append(
                    {
                        "user_id": user[0],
                        "username": user[4],
                        "referral_code": user[1],
                        "balance": user[3],
                        "referred_by": user[2]
                    }
                )
        return jsonify(users_list), 200
    except Exception as e:
        logging.error(f"Error fetching users: {str(e)}")
        return jsonify({'error': 'Failed to fetch users'}), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для редактирования платного товара
@app.route('/paid-products/<string:category_name>/<string:product_name>', methods=['GET', 'POST'])
@login_required
def edit_paid_product(category_name, product_name):
    conn = db_manager.get_connection()
    if not conn:
         logging.error("edit_paid_product: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        if request.method == 'POST':
            data = request.get_json()
            logging.info(f"Получены данные для сохранения закладки: {data}")
            city = data.get('city')
            district = data.get('district')
            instruction = data.get('instruction')
            images_data = data.get('images', [])
            selected_value = data.get("selectedValue")
            selected_type = data.get("selectedType")
            total_price = data.get("totalPrice")

            # Обработка изображений
            saved_image_paths = []
            for image_data in images_data:
                image_res = upload_image(image_data)
                if "error" not in image_res:
                    saved_image_paths.append(image_res['imagePath'])
                else:
                    return jsonify({'error': f"Ошибка сохранения изображения: {image_res['error']}"}), 400

            images_json = json.dumps(saved_image_paths)

            # Проверка обязательных полей
            if not all([city, district, instruction, selected_value, selected_type, total_price]):
                return jsonify({'error': 'All fields (city, district, instruction, selected_value, selected_type, totalPrice) are required'}), 400

            try:
                table_name = get_paid_products_table_name(selected_type, selected_value)
                logging.info(f"Попытка сохранения в таблицу: {table_name}")
            except ValueError as e:
                logging.error(f"Ошибка формирования имени таблицы: {e}")
                return jsonify({'error': str(e)}), 400
            
            # Вызов функции add_paid_product
            add_paid_product(product_name, instruction, city, district, total_price, category_name, images_json, selected_value, selected_type)
            return jsonify({'message': 'Record added successfully'}), 200


        # Обработка GET запроса
        query = "SELECT id, price FROM products WHERE name = ?"
        product_row = execute_query(query, (product_name,), fetch=True, fetch_one_flag=True)
        if not product_row:
            return "Product not found", 404
        product_id = product_row[0]
        product_price = product_row[1] if product_row and len(product_row) > 1 else None

        all_paid_products = get_paid_products_with_images(product_name, category_name, product_id)

        locations = execute_query("SELECT city, district FROM locations", fetch=True)
        locs = {}
        for city, district in locations:
            locs.setdefault(city, []).append(district)

        return render_template(
            "paid_products_product.html",
            paid_products=all_paid_products,
            locations=locs,
            category_name=category_name,
            product_name=product_name,
            product_id=product_id,
            product_price=product_price
        )

    except Exception as e:
        print("Database error:", e)
        print(f"Error in edit_paid_product: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)
      
# Маршрут для обновления локации платного товара
@app.route('/update-paid-product-location/<int:record_id>/<string:table_name>', methods=['PUT'])
@login_required
def update_paid_product_location(record_id, table_name):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("update_paid_product_location: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        data = request.get_json()
        if not data or not all(key in data for key in ['instruction', 'price', 'city', 'district']):
            return jsonify({'error': 'Instruction, price, city and district are required'}), 400
        instruction = data.get('instruction')
        price = data.get("price")
        city = data.get("city")
        district = data.get("district")

        query = f"UPDATE {table_name} SET instruction = ?, price = ?, city = ?, district = ? WHERE id = ?"
        execute_query(query, (instruction, price, city, district, record_id))

        return jsonify({'message': 'Location updated successfully'}), 200

    except Exception as e:
        print(f"Error in update_paid_product_location: {e}")
        return jsonify({'error': 'An error occurred'}), 500
    finally:
      db_manager.release_connection(conn)

# Маршрут для удаления платного продукта
@app.route('/delete-paid-product/<int:record_id>/<string:table_name>', methods=['DELETE'])
@login_required
def delete_paid_product(record_id, table_name):
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"delete_paid_product: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
       
        query = f"DELETE FROM {table_name} WHERE id = ?"
        execute_query(query, (record_id,))
        return jsonify({'message': 'Record deleted successfully'}), 200

    except Exception as e:
        print(f"Error in delete_paid_product: {e}")
        return jsonify({'error': 'An error occurred'}), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для получения списка кошельков
@app.route('/wallets', methods=['GET'])
@login_required
def get_wallets():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_wallets: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        wallets = execute_query("SELECT id, name, address FROM wallets", fetch=True)
        wallets_list = []
        for row in wallets:
            wallets_list.append({
                "id": row[0],
                "currency": row[1],
                "wallet_address": row[2]
            })
        return jsonify(wallets_list), 200
    except Exception as e:
        logging.error(f"Error fetching wallets: {str(e)}")
        return jsonify({'error': 'Failed to fetch wallets'}), 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для обновления кошелька
@app.route('/update-wallet/<int:wallet_id>', methods=['PUT'])
@login_required
def update_wallet(wallet_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("update_wallet: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        wallet_data = request.get_json()
        logging.debug(f"Received data for wallet update: {wallet_data}")
        if not wallet_data or 'wallet_address' not in wallet_data:
            return jsonify({'error': 'No wallet address provided'}), 400
        new_address = wallet_data["wallet_address"]
        query = "UPDATE wallets SET address=? WHERE id=?"
        cursor = execute_query(query, (new_address, wallet_id), fetch=False, fetch_one_flag=False)
        if cursor.rowcount == 0:
            return jsonify({'error': 'Wallet not found'}), 404
        return jsonify({'message': 'Wallet updated successfully', 'success': True}), 200
    except Exception as e:
        logging.error(f"Error updating wallet {wallet_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db_manager.release_connection(conn)

@app.route('/add-wallet', methods=['POST'])
@login_required
def add_wallet():
    conn = db_manager.get_connection()
    if not conn:
         logging.error("add_wallet: Не удалось получить соединение из пула.")
         return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        wallet_data = request.get_json()
        logging.debug(f"Received data for new wallet: {wallet_data}")
        if not wallet_data or 'name' not in wallet_data or 'address' not in wallet_data:
            return jsonify({'error': 'Currency and wallet address must be provided'}), 400
        name = wallet_data.get("name").upper()
        wallet_address = wallet_data.get("address")
        query = "INSERT INTO wallets (name, address) VALUES (?, ?)"
        execute_query(query, (name, wallet_address))
        return jsonify({'message': 'Wallet added successfully', 'success': True}), 201
    except Exception as e:
        logging.error(f"Error adding wallet: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
       db_manager.release_connection(conn)
#  Маршрут для удаления кошелька
@app.route('/delete-wallet/<int:wallet_id>', methods=['DELETE'])
@login_required
def delete_wallet(wallet_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("delete_wallet: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        logging.debug(f"Attempting to delete wallet with ID: {wallet_id}")
        query = "DELETE FROM wallets WHERE id=?"
        cursor = execute_query(query, (wallet_id,), fetch=False, fetch_one_flag=False)
        if cursor.rowcount == 0:
            return jsonify({'error': 'Wallet not found'}), 404
        return jsonify({'message': 'Wallet deleted successfully', 'success': True}), 200
    except Exception as e:
        logging.error(f"Error deleting wallet {wallet_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
      db_manager.release_connection(conn)

# Маршрут для обновления платного продукта
@app.route('/update-paid-product', methods=['POST'])
@login_required
def update_paid_product():
    conn = db_manager.get_connection()
    if not conn:
        logging.error("update_paid_product: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        category_name = data.get("category")
        product_name = data.get("product_name")
        city = data.get("city")
        district = data.get("district")
        instruction = data.get("instruction")
        images = data.get("images", [])
        if not category_name or not product_name or not city or not district:
            return jsonify({'error': 'Category, product name, city, and district must be provided'}), 400
        images_str = json.dumps(images)
        query = """
            INSERT INTO paid_products (product_name, description, images, instruction, city, district, category_name)
            VALUES (?, '', ?, ?, ?, ?, ?)
        """
        execute_query(query, (product_name, images_str, instruction, city, district, category_name))
        return jsonify({'message': 'Paid product updated successfully'}), 200
    except Exception as e:
      logging.error(f"Error in update_paid_product endpoint: {e}")
      return "An error occurred. Check the logs for details.", 500
    finally:
      db_manager.release_connection(conn)


# Маршрут для удаления локации платного продукта
@app.route('/delete-paid-product/<string:category_name>/<string:product_name>', methods=['DELETE'])
@app.route('/delete-paid-product/<string:category_name>/<string:product_name>/<int:location_index>', methods=['DELETE'])
@login_required
def delete_paid_product_location(category_name, product_name, location_index=None):
    try:
        return jsonify({'error': 'This route is not used anymore'}), 404
    except Exception as e:
        print(f"Error in delete_paid_product_location: {e}")
        return jsonify({'error': 'An error occurred'}), 500

# Маршрут для страницы платных товаров по категории
@app.route("/paid-products/<string:category_name>")
@login_required
def paid_products_category(category_name):
    conn = db_manager.get_connection()
    if not conn:
        logging.error("paid_products_category: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    try:
        # Получаем ID категории по ее имени
        query = "SELECT id FROM categories WHERE name = ?"
        category_row = execute_query(query, (category_name,), fetch=True, fetch_one_flag=True)
        if not category_row:
            return "Категория не найдена", 404
        category_id = category_row[0]

        # Получаем список товаров, принадлежащих к этой категории
        query = """
            SELECT id, name
            FROM products
            WHERE category_id = ?
        """
        products = execute_query(query, (category_id,), fetch=True)

        # Формируем список товаров с количеством закладок
        product_list = []
        for product in products:
            # Получаем количество закладок для текущего товара
            bookmark_count = 0
            product_id = product[0]
            gram_products = [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]
            item_products = [2, 8, 9, 10, 11]
            if product_id in gram_products:
               for gram in [1, 2, 5, 10]:
                   table_name = get_paid_products_table_name("gram", gram)
                   query = f"""
                       SELECT COUNT(*)
                       FROM {table_name}
                       WHERE product_name LIKE ? AND category_name = ?
                   """
                   count_result = execute_query(query, (product[1] + '%', category_name), fetch=True, fetch_one_flag=True)
                   if count_result and count_result[0] is not None:
                       bookmark_count += count_result[0]

            elif product_id in item_products:
                 for item in [1, 2, 5, 10, 20, 50]:
                    table_name = get_paid_products_table_name("item", item)
                    query = f"""
                       SELECT COUNT(*)
                       FROM {table_name}
                       WHERE product_name LIKE ? AND category_name = ?
                    """
                    count_result = execute_query(query, (product[1] + '%', category_name), fetch=True, fetch_one_flag=True)
                    if count_result and count_result[0] is not None:
                        bookmark_count += count_result[0]

            product_list.append({
                "id": product[0],
                "name": product[1],
                "bookmark_count": bookmark_count
            })

        return render_template("paid_products_category.html",
                               category_name=category_name,
                               products=product_list)
    except Exception as e:
      logging.error(f"Error in paid_products_category endpoint: {e}")
      return "An error occurred. Check the logs for details.", 500
    finally:
       db_manager.release_connection(conn)

# Маршрут для админ-панели
@app.route("/admin")
@login_required
def admin_panel():
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"admin_panel: Не удалось получить соединение из пула.")
        return "Не удалось подключиться к базе данных."
    try:
        # Запрашиваем пользователей
        users = execute_query("SELECT user_id, referral_code, referred_by, balance, username FROM users", fetch=True)
        users_list = []
        if users:
            for user in users:
                users_list.append(
                    {
                        "user_id": user[0],
                        "username": user[4],
                        "referral_code": user[1],
                        "balance": user[3],
                        "referred_by": user[2]
                    }
                )
        else:
            users_list = None
        # Запрашиваем продукты вместе с названием категории
        query = """
            SELECT
                p.id,
                p.name,
                p.category_id,
                c.name AS category_name,
                p.price,
                p.description,
                p.image
            FROM products p
            JOIN categories c ON p.category_id = c.id
        """
        products = execute_query(query, fetch=True)

        # Дополнительные запросы
        all_paid_products = []
        for gram in [1, 2, 5, 10]:
            table_name = get_paid_products_table_name("gram", gram)
            query = f"SELECT * FROM {table_name}"
            paid_products = execute_query(query, fetch=True)
            all_paid_products.extend(paid_products)
        for item in [1, 2, 5, 10, 20, 50]:
            table_name = get_paid_products_table_name("item", item)
            query = f"SELECT * FROM {table_name}"
            paid_products = execute_query(query, fetch=True)
            all_paid_products.extend(paid_products)

        orders = execute_query("SELECT * FROM orders", fetch=True)

        categories = execute_query("SELECT * FROM categories", fetch=True)

        locations = execute_query("SELECT * FROM locations", fetch=True)

        referrals = execute_query("SELECT * FROM referrals", fetch=True)

        wallets = execute_query("SELECT * FROM wallets", fetch=True)

        # Собираем данные о продуктах в список словарей
        products_list = []
        for row in products:
            product_id = row[0]
            product_name = row[1]
            product_cat_id = row[2]
            product_cat_name = row[3]  # Название категории
            product_price = row[4]
            product_desc = row[5]
            product_image = row[6]

            # Получаем локации для продукта
            product_locations = get_product_locations_from_db(product_id)

                # Создаём объект продукта
            product_dict = {
                "id": product_id,
                "name": product_name,
                "category_id": product_cat_id,
                "category_name": product_cat_name,
                "price": product_price,
                "description": product_desc,
                "image": product_image,
                "locations": product_locations
            }
            products_list.append(product_dict)

        # Отладочный вывод
        print("Products list:")
        print(products_list)

        # Передаём данные в шаблон
        return render_template(
            "admin_panel.html",
            users=users_list,
            products=products_list,
            paid_products=all_paid_products,
            orders=orders,
            categories=categories,
            locations=locations,
            referrals=referrals,
            wallets=wallets
        )
    except Exception as e:
        print(f"Error in admin_panel: {e}")
        return "An error occurred. Check the logs for details."
    finally:
       db_manager.release_connection(conn)
       
if __name__ == '__main__':
 app.run(debug=True, host='0.0.0.0', port=52265)