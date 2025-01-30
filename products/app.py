# app.py
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, abort, send_from_directory
import os
import sys
import logging
import json
import base64
from io import BytesIO
from functools import wraps
from werkzeug.security import check_password_hash
import uuid
import telegram
from telegram.ext import Application
import datetime
from decimal import Decimal
import re

# Настройка логирования (если еще не настроено)
logging.basicConfig(level=logging.INFO)

# Путь к директории, где находится database.py (на уровень выше products/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импорт функций для работы с базой данных
from database import (
    db_manager, get_all_users, get_user, add_user, set_paid_products_original_price, update_paid_products_prices, update_username_query, delete_user,
    get_user_balance, get_referral_count, update_referral_purchases_amount,
    get_referral_purchases_amount, get_referral_purchases_count, get_user_tickets, add_ticket,
    execute_query, get_available_products, get_paid_products_table_name, get_employee_by_username, add_employee, check_password,
    add_paid_product, get_all_locations, get_all_products, get_location_info_from_paid_products, get_product_by_name, get_product_category, get_product_price,
    get_user_sold_products, add_employee_expense, get_employee_expenses
)


app = Flask(__name__)
app.template_folder = 'templates'
app.static_folder = '../data/images'
app.secret_key = os.urandom(24)

# ========================================================================
# ВСТАВЬТЕ СВОЙ ЛОГИН И ПАРОЛЬ ЗДЕСЬ
# ========================================================================
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
# ========================================================================

# Функция декоратор для проверки авторизации сотрудника
def employee_login_required(role=None):
   def decorator(f):
      @wraps(f)
      def decorated_function(*args, **kwargs):
         if 'employee_id' not in session:
             return redirect(url_for('employee_login'))
         if role:
            employee = get_employee_by_username(session['username'])
            if not employee or employee['role'] != role:
                abort(403)
         return f(*args, **kwargs)
      return decorated_function
   return decorator


@app.route('/employee_login', methods=['GET', 'POST'])
def employee_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        employee = get_employee_by_username(username)  # Исправлено
        if employee and check_password(employee, password):
            session['employee_id'] = employee['id']
            session['username'] = employee['username']
            session['role'] = employee['role']
            if employee['role'] == 'admin':
                return redirect(url_for('index'))
            else:
               return redirect(url_for('employee_dashboard'))
        else:
           return render_template('employee_login.html', error='Неверный логин или пароль')
    return render_template('employee_login.html')


# Маршрут для выхода сотрудников
@app.route('/employee_logout')
def employee_logout():
    session.pop('employee_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('employee_login'))

@app.route('/add_employee', methods=['GET','POST'])
@employee_login_required(role="admin")
def add_employee_route():
      if request.method == 'POST':
          username = request.form['username']
          password = request.form['password']
          role = request.form['role']
          add_employee(username, password, role) # Исправлено
          return redirect(url_for('index'))
      return render_template('add_employee.html')

@app.route("/")
@employee_login_required(role="admin")
def index():
    """Главная страница - выбор локации."""
    locations = get_all_locations()

    # Словарь для хранения количества закладок по городам
    cities_with_counts = {}

    for loc in locations:
        city = loc['city']
        if city not in cities_with_counts:
             cities_with_counts[city] = 0

    for city_data in cities_with_counts:
         total_count_for_city = 0
         locations_in_city = [loc for loc in locations if loc['city'] == city_data]
         products = get_all_products()
         for product in products:
            for loc in locations_in_city:
                available_products_for_city_and_district = get_available_products(loc['city'], loc['district'], product['id'])
                if available_products_for_city_and_district:
                   total_count_for_city += len(available_products_for_city_and_district)
         cities_with_counts[city_data] = total_count_for_city
         print(f"City: {city_data}, total_count: {total_count_for_city}")


    # Преобразуем словарь в список кортежей
    cities_list = list(cities_with_counts.items())


    return render_template('index.html', cities=cities_list)


@app.route("/city/<city_name>")
@employee_login_required()
def city_districts(city_name):
    """Страница выбора районов для выбранного города."""
    locations = get_all_locations()

    # Словарь для хранения количества закладок по районам
    districts_with_counts = {}

    for loc in locations:
        if loc['city'] == city_name:
            district = loc['district']
            if district not in districts_with_counts:
                districts_with_counts[district] = 0
            # Подсчет закладок для каждого района
            products = get_all_products()
            for product in products:
               available_products = get_available_products(city_name, district, product['id'])
               if available_products:
                 districts_with_counts[district] += len(available_products) # Увеличиваем счетчик закладок для данного района
    # Преобразуем словарь в список кортежей для передачи в шаблон
    districts_list = list(districts_with_counts.items())

    return render_template('city_districts.html', city_name=city_name, districts=districts_list)


@app.route("/city/<city_name>/district/<district_name>")
@employee_login_required()
def product_list(city_name, district_name):
    """Страница списка товаров для выбранного города и района."""
    products = get_all_products()
    available_products_data = {}
    for product in products:
        available = get_available_products(city_name, district_name, product['id'])
        if available:
            available_products_data[product['name']] = available

    # Process data to count product variations
    product_counts = {}
    for base_product_name, variations in available_products_data.items():
        for variation in variations:
            full_product_name = variation['product_name']
            if full_product_name not in product_counts:
                product_counts[full_product_name] = 0
            product_counts[full_product_name] += 1

    return render_template(
        'product_list.html',
        city_name=city_name,
        district_name=district_name,
        product_counts=product_counts, # Pass the counts to the template
        available_products_data=available_products_data # Keep original data for links
    )


@app.route("/city/<city_name>/district/<district_name>/product/<product_name>")
@employee_login_required()
def zakladki_list(city_name, district_name, product_name):
    """Страница списка закладок для выбранного товара, города и района."""
    logging.info(f"Запрос закладок: город={city_name}, район={district_name}, товар={product_name}")

    # Передаем полное название товара БЕЗ обрезки
    zakladki_all = get_location_info_from_paid_products(product_name, city_name, district_name, role=session.get('role'), user_id=session.get('employee_id'))

    logging.info(f"Результат get_location_info_from_paid_products: {zakladki_all}")

    zakladki = []
    if zakladki_all:
        for zakladka in zakladki_all:
            if zakladka['product_name'] == product_name:
                zakladki.append(zakladka)

    logging.info(f"Отфильтрованные закладки: {zakladki}")

    return render_template(
        'zakladki_list.html',
        city_name=city_name,
        district_name=district_name,
        product_name=product_name,
        zakladki=zakladki,
        is_admin=session.get('role') == 'admin'
    )


@app.route('/download_image/<filename>')
@employee_login_required(role="admin")
def download_image(filename):
    """Скачивание одного изображения."""
    logging.info(f"Запрос на скачивание изображения: filename={filename}")
    image_path = os.path.join(app.static_folder, filename)

    if not os.path.exists(image_path):
        return "Файл не найден", 404

    return send_file(
        image_path,
        mimetype='image/jpeg',
        as_attachment=True,
        download_name=filename
    )


# ---  Delete Route ---
@app.route('/delete_zakladka/<string:table_name>/<int:zakladka_id>', methods=['DELETE'])
@employee_login_required(role="admin")
def delete_zakladka(table_name, zakladka_id):
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"delete_zakladka: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    cursor = None
    try:
        logging.info(f"Удаление закладки ID: {zakladka_id} из таблицы {table_name}")
        query = f"DELETE FROM {table_name} WHERE id = ?"
        cursor = execute_query(query, (zakladka_id,))
        return jsonify({'message': 'Record deleted successfully'}), 200
    except Exception as e:
        logging.error(f"Error in delete_paid_product: {e}")
        return jsonify({'error': 'An error occurred'}), 500
    finally:
       if cursor:
          cursor.close()
       db_manager.release_connection(conn)

@app.route('/employee_dashboard', methods=['GET', 'POST'])
@employee_login_required()
def employee_dashboard():
    """Страница личного кабинета сотрудника"""
    locations = get_all_locations()  # Get all locations for dropdowns
    products = get_all_products()  # Get all products for dropdown
    cities = sorted(list(set([loc['city'] for loc in locations])))  # get unique list of cities

    if request.method == 'POST':
            product_name = request.form['product_name']
            instruction = request.form['instruction']
            city = request.form['city']
            district = request.form['district']
            selected_value = int(request.form['selected_value'])  # Получаем выбранное значение граммовки/количества

            # Очищаем название товара от чисел
            product_name_for_key = re.sub(r'\s*\d+[а-яё]*', '', product_name)
            
            product_info = get_product_by_name(product_name)
            if product_info:
                category_name = get_product_category(product_name)
            else:
                category_name = "ЭЙФОРИЯ"  # дефолтная категория
                logging.warning(f"Не найдена категория для {product_name}")
    
            product_id_from_products = next((product['id'] for product in products if product['name'] == product_name), None)
            if product_id_from_products:
                price_from_db = get_product_price(product_id_from_products)
            else:
                price_from_db = 0.0  # дефолтная цена
                logging.warning(f"Не найдена цена для {product_name}")
            
            # Умножаем цену на выбранное значение граммовки/количества
            price = price_from_db * selected_value
            
            # Получаем загруженные изображения
            images = request.files.getlist('images')
            # Формируем список путей к файлам
            image_paths = []
            for image in images:
                if image and image.filename != '':  # Проверка, что файл действительно загружен
                    filename = str(uuid.uuid4()) + os.path.splitext(image.filename)[1]
                    image_path = os.path.join(app.static_folder, filename)  # Сохранение в static папку
                    relative_image_path = f'/data/images/{filename}' #  <-- Относительный путь
                    image.save(image_path)  # Сохраняем файл
                    image_paths.append(relative_image_path) #  <-- сохраняем относительный путь
    
            # Определяем тип на основе product_id
            if product_id_from_products in [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]:
                selected_type = 'gram'
            elif product_id_from_products in [2, 8, 9, 10, 11]:
                selected_type = 'item'
            else:
                selected_type = 'item'
    
            # Correctly format image_paths as JSON array string
            images_json = json.dumps(image_paths)
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            add_paid_product(
                product_name_for_key,  # Теперь сохраняем название товара без размера
                instruction,
                city,
                district,
                price,  # Используем цену с учетом граммовки/количества
                category_name,
                images=images_json,  # Сохраняем JSON строку в БД
                selected_value=selected_value,
                selected_type=selected_type,
                employee_id=session.get('employee_id'),
                created_at=current_time
            )
            return redirect(url_for('employee_dashboard'))

    # выборка для таблицы закладок
    logging.info(f"Запрос закладок для пользователя с ID: {session.get('employee_id')}, роль: {session.get('role')}")
    employee_zakladki_all = get_location_info_from_paid_products(product_name="", city="", district="", role=session.get('role'), user_id=session.get('employee_id'))

    if employee_zakladki_all:
        logging.info(f"Найдено {len(employee_zakladki_all)} закладок для пользователя.")
        employee_zakladki = [zakladka for zakladka in employee_zakladki_all]
        logging.debug(f"Закладки: {employee_zakladki}")
        # Parse images JSON string to list for template rendering
        for zakladka in employee_zakladki:
            if zakladka.get('images'):
                try:
                    zakladka['images'] = json.loads(zakladka['images'])
                except json.JSONDecodeError:
                    logging.error(f"JSONDecodeError: Could not decode images JSON: {zakladka['images']}")
                    zakladka['images'] = [] # Handle error, set to empty list or other default
            else:
                zakladka['images'] = [] # Ensure images is always a list in template

    else:
        logging.info("Нет закладок для текущего пользователя.")
        employee_zakladki = []
    logging.debug(f"Данные передаваемые в шаблон: {employee_zakladki}")
    
    sold_products_all = get_user_sold_products(username=session.get('username')) # Получаем проданные товары

    if sold_products_all:
      for sold_product in sold_products_all:
        if sold_product not in employee_zakladki:
           employee_zakladki.append(sold_product) # Добавляем проданные в общий список

    return render_template('employee_dashboard.html', locations=locations, products=products, zakladki=employee_zakladki, cities=cities)

# Маршрут для отдачи изображений
@app.route('/data/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(app.static_folder, filename)


# Расценки для расчета заработка
PRICES = {
      ('КЕТАМИН', 'gr1'): {'price': 10, 'value': 1},
      ('КЕТАМИН', 'gr2'): {'price': 15, 'value': 2},
      ('МДМА', 'gr1'): {'price': 10, 'value': 1},
      ('МДМА', 'gr2'): {'price': 15, 'value': 2},
      ('МЕФЕДРОН', 'gr1'): {'price': 10, 'value': 1},
      ('МЕФЕДРОН', 'gr2'): {'price': 15, 'value': 2},
      ('КОКАИН', 'gr1'): {'price': 10, 'value': 1},
      ('КОКАИН', 'gr2'): {'price': 15, 'value': 2},
      ('АМФЕТАМИН', 'gr1'): {'price': 10, 'value': 1},
      ('АМФЕТАМИН', 'gr2'): {'price': 15, 'value': 2},
      ('МЕТАМФЕТАМИН', 'gr1'): {'price': 10, 'value': 1},
      ('МЕТАМФЕТАМИН', 'gr2'): {'price': 15, 'value': 2},
      ('МЕФ МУКА', 'gr1'): {'price': 10, 'value': 1},
      ('МЕФ МУКА', 'gr2'): {'price': 15, 'value': 2},
      ('ГАШИШ', 'gr1'): {'price': 10, 'value': 1},
      ('ГАШИШ', 'gr2'): {'price': 15, 'value': 2},
      ('ЭКСТАЗИ', 'item2'): {'price': 10, 'value': 2},
      ('ЭКСТАЗИ', 'item5'): {'price': 15, 'value': 5},
      ('ГРИБЫ', 'gr5'): {'price': 10, 'value': 5},
      ('ГРИБЫ', 'gr10'): {'price': 15, 'value': 10},
      ('NEO-COUGH', 'item1'): {'price': 10, 'value': 1},
       ('ТРАНКМАZIN', 'item5'): {'price': 10, 'value': 5},
       ('ТРАНКМАZIN', 'item10'): {'price': 15, 'value': 10},
       ('Codethazine', 'item1'): {'price': 10, 'value': 1},
      ('Codethazine', 'item2'): {'price': 15, 'value': 2},
       ('CodeThazine', 'item5'): {'price': 25, 'value': 5},
       ('КЕТАМИН', 'gr5'): {'price': 20, 'value': 5},
       ('КЕТАМИН', 'gr10'): {'price': 30, 'value': 10},
       ('МДМА', 'gr5'): {'price': 20, 'value': 5},
       ('МДМА', 'gr10'): {'price': 30, 'value': 10},
         ('МЕФЕДРОН', 'gr5'): {'price': 20, 'value': 5},
        ('МЕФЕДРОН', 'gr10'): {'price': 30, 'value': 10},
      ('КОКАИН', 'gr5'): {'price': 30, 'value': 5},
      ('КОКАИН', 'gr10'): {'price': 50, 'value': 10},
      ('АМФЕТАМИН', 'gr5'): {'price': 20, 'value': 5},
      ('АМФЕТАМИН', 'gr10'): {'price': 30, 'value': 10},
      ('МЕТАМФЕТАМИН', 'gr5'): {'price': 20, 'value': 5},
      ('МЕТАМФЕТАМИН', 'gr10'): {'price': 30, 'value': 10},
     ('МЕФ МУКА', 'gr5'): {'price': 20, 'value': 5},
     ('МЕФ МУКА', 'gr10'): {'price': 30, 'value': 10},
     ('ГАШИШ', 'gr5'): {'price': 10, 'value': 5},
     ('ГАШИШ', 'gr10'): {'price': 20, 'value': 10},
     ('ЭКСТАЗИ', 'item10'): {'price': 25, 'value': 10},
     ('ЭКСТАЗИ', 'item20'): {'price': 35, 'value': 20},
     ('ЭКСТАЗИ', 'item50'): {'price': 50, 'value': 50},
     ('Codethazine', 'item20'): {'price': 50, 'value': 20},
     ('Codethazine', 'item50'): {'price': 100, 'value': 50},
     ('Alprazolam', 'item5'): {'price': 5, 'value': 5},
     ('Alprazolam', 'item10'): {'price': 10, 'value': 10},
     ('Alprazolam', 'item20'): {'price': 15, 'value': 20},
     ('Alprazolam', 'item50'): {'price': 20, 'value': 50}
  }


def calculate_zakladka_earnings(zakladka):
    product_name = zakladka.get('product_name')
    table_name = zakladka.get('table_name')
    selected_value = zakladka.get('selected_value')

    logging.info(f"calculate_zakladka_earnings: Processing zakladka: {zakladka}")

    if not product_name or not table_name:
        logging.warning(f"calculate_zakladka_earnings: Закладка пропущена из-за отсутствия product_name или table_name: {zakladka}")
        return 0

    size_key = None

    if table_name != 'paid_products':
        size_match = re.search(r'([a-zA-Z]+)_(\d+)', table_name)
        if size_match:
            size_key = f"{size_match.group(1)}{size_match.group(2)}"
            logging.info(f"calculate_zakladka_earnings: size_key from table_name: {size_key}, table_name: {table_name}")

    if not size_key:
      if selected_value:
        size_key = f"item{selected_value.replace('гр', '').replace('шт','')}"
        logging.info(f"calculate_zakladka_earnings: size_key from selected_value: {size_key}, table_name: {table_name}, selected_value: {selected_value}")
      else:
         size_match_from_name = re.search(r'(\d+)([а-яё]+)', product_name)
         if size_match_from_name:
            size_key = f"{size_match_from_name.group(2)}{size_match_from_name.group(1)}"
            logging.info(f"calculate_zakladka_earnings: size_key from product_name: {size_key}, table_name: {table_name}, product_name: {product_name}")
         else:
            size_key = "item1"
            logging.info(f"calculate_zakladka_earnings: size_key default item1: {size_key}, table_name: {table_name}, product_name:{product_name}")

    # Удаляем граммовку из названия товара динамически
    product_name_cleaned = re.sub(r'\s*\d+[а-яё]*', '', product_name).strip()

    key = (product_name_cleaned, size_key)
    logging.info(f"calculate_zakladka_earnings: Calculating earnings for: product_name: {product_name}, table_name: {table_name}, product_name_cleaned: {product_name_cleaned}, size_key: {size_key}, key: {key}")

    if key in PRICES:
        price_data = PRICES[key]
        logging.info(f"calculate_zakladka_earnings: Found price for {key}: {price_data['price']}")
        return price_data['price']
    else:
        logging.warning(f"calculate_zakladka_earnings: Не найдено расценки для {key} - {zakladka}")
        return 0

def is_in_current_month(date_string):
    """Проверяет, относится ли дата к текущему месяцу и году."""
    if not date_string:
      return False
    try:
        created_date = datetime.datetime.fromisoformat(date_string)
        return created_date.month == datetime.datetime.now().month and created_date.year == datetime.datetime.now().year
    except (ValueError, TypeError):
        logging.warning(f"Неверный формат даты: {date_string}")
        return False


@app.route('/employee_stats')
@employee_login_required()
def employee_stats():
    """Страница статистики сотрудника."""
    employee_id = session.get('employee_id')
    role = session.get('role')

    logging.info(f"employee_stats: Starting stats calculation for employee_id: {employee_id}, role: {role}")
    
    # Получаем все закладки сотрудника
    logging.info(f"employee_stats: Calling get_location_info_from_paid_products")
    employee_zakladki_all = get_location_info_from_paid_products(product_name="", city="", district="", role=role, user_id=employee_id)
    logging.info(f"employee_stats: get_location_info_from_paid_products result: {employee_zakladki_all}")
    
    if not employee_zakladki_all:
        logging.info("employee_stats: No zakladki found, returning empty stats")
        return render_template('employee_stats.html', stats_by_month={}, total_earnings=0, current_month_earnings=0, expenses=[])

    # Инициализация словаря для хранения статистики по месяцам
    monthly_stats = {}
    total_earnings = Decimal('0')

    if employee_zakladki_all:
         for zakladka in employee_zakladki_all:
            logging.debug(f"employee_stats: Processing zakladka: {zakladka}")
            created_at = zakladka.get('created_at')
            if created_at:
              try:
                created_date = datetime.datetime.fromisoformat(created_at)
              except (ValueError, TypeError):
                    logging.warning(f"employee_stats: Неверный формат даты: {created_at}")
                    continue
              month_year = created_date.strftime("%B %Y")
            else:
              logging.warning(f"employee_stats: Неверная дата: {created_at}")
              continue
            
            earnings = calculate_zakladka_earnings(zakladka)
            total_earnings += Decimal(str(earnings))
            logging.debug(f"employee_stats: Earnings: {earnings}, total_earnings: {total_earnings}")

            if month_year not in monthly_stats:
                monthly_stats[month_year] = {}
                
            table_name = zakladka.get('table_name')
            size_match = re.search(r'([a-zA-Z]+)_(\d+)', table_name)
            if size_match:
              size_key = f"{size_match.group(1)}{size_match.group(2)}"
            elif table_name == 'paid_products':
                size_key = 'item1'
            else:
               logging.warning(f"employee_stats: Не удалось определить size_key для: {table_name}")
               continue

            product_name_cleaned = re.sub(r'\s*\d+[а-яё]*', '', zakladka.get('product_name'))
            
            if product_name_cleaned not in monthly_stats[month_year]:
                monthly_stats[month_year][product_name_cleaned] = {"count": 0, 'earnings': Decimal('0')}
            
            monthly_stats[month_year][product_name_cleaned]["count"] += 1
            monthly_stats[month_year][product_name_cleaned]["earnings"] += Decimal(str(earnings))
            logging.debug(f"employee_stats: monthly_stats after zakladka: {monthly_stats}")
            
    logging.info("employee_stats: Calling get_user_sold_products")
    sold_products_all = get_user_sold_products(username=session.get('username'))
    logging.info(f"employee_stats: get_user_sold_products result: {sold_products_all}")
    
    if sold_products_all:
      for sold_product in sold_products_all:
          logging.debug(f"employee_stats: Processing sold_product: {sold_product}")
          sale_date = sold_product.get('sale_date')
          if sale_date:
              try:
                  sale_date_date = datetime.datetime.fromisoformat(sale_date)
              except (ValueError, TypeError):
                   logging.warning(f"employee_stats: Неверный формат даты: {sale_date}")
                   continue
              month_year = sale_date_date.strftime("%B %Y")
          else:
              logging.warning(f"employee_stats: Неверная дата: {sale_date}")
              continue
              
          earnings = calculate_zakladka_earnings(sold_product)
          total_earnings += Decimal(str(earnings))
          logging.debug(f"employee_stats: Earnings: {earnings}, total_earnings: {total_earnings}")

          if month_year not in monthly_stats:
              monthly_stats[month_year] = {}

          table_name = sold_product.get('table_name')
          size_match = re.search(r'([a-zA-Z]+)_(\d+)', table_name)
          if size_match:
                size_key = f"{size_match.group(1)}{size_match.group(2)}"
          elif table_name == 'paid_products':
               size_key = "item1"
          else:
             logging.warning(f"employee_stats: Не удалось определить size_key для: {table_name}")
             continue
          product_name_cleaned = re.sub(r'\s*\d+[а-яё]*', '', sold_product.get('product_name'))
          if product_name_cleaned not in monthly_stats[month_year]:
             monthly_stats[month_year][product_name_cleaned] = {"count": 0, 'earnings': Decimal('0')}
          monthly_stats[month_year][product_name_cleaned]["count"] += 1
          monthly_stats[month_year][product_name_cleaned]["earnings"] += Decimal(str(earnings))
          logging.debug(f"employee_stats: monthly_stats after sold_product: {monthly_stats}")

    current_month = datetime.datetime.now().strftime("%B %Y")
    current_month_earnings = monthly_stats.get(current_month, {}).get('total_earnings', Decimal('0'))

    for month, month_stats in monthly_stats.items():
         total_month_earnings = Decimal('0')
         for size_stats in month_stats.values():
              total_month_earnings += size_stats['earnings']
         monthly_stats[month]['total_earnings'] = total_month_earnings
    
    expenses = get_employee_expenses(employee_id) if employee_id else []

    logging.info(f"employee_stats: Final total_earnings: {total_earnings}, current_month_earnings: {current_month_earnings}")
    logging.info("employee_stats: Returning stats data to template")
    return render_template(
        'employee_stats.html',
        stats_by_month=monthly_stats,
        total_earnings=float(total_earnings),
        current_month_earnings=float(current_month_earnings),
        expenses=expenses
    )

@app.route('/save_expense', methods=['POST'])
@employee_login_required()
def save_expense():
    """Сохранение затрат сотрудника."""
    try:
        data = request.get_json()
        expense_date = data['expense_date']
        expense_description = data['expense_description']
        expense_amount = data['expense_amount']
        employee_id = data['employee_id']
        
        if add_employee_expense(employee_id, expense_date, expense_description, expense_amount): # Исправлено вызов как обычную функцию
          return jsonify({'message': 'Record saved successfully'}), 200
        else:
          return jsonify({'message': 'Record saved failed'}), 500
    except Exception as e:
        logging.error(f"Error in save_expense: {e}")
        return jsonify({'error': 'Invalid data'}), 400


@app.route('/delete_employee_zakladka/<string:table_name>/<int:zakladka_id>', methods=['DELETE'])
@employee_login_required()
def delete_employee_zakladka(table_name, zakladka_id):
    """Удаление закладки сотрудника."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error(f"delete_employee_zakladka: Не удалось получить соединение из пула.")
        return jsonify({'error': 'Не удалось подключиться к базе данных.'}), 500
    cursor = None
    try:
        logging.info(f"Удаление закладки ID: {zakladka_id} из таблицы {table_name} от пользователя с ID {session.get('employee_id')}")
        query = f"DELETE FROM {table_name} WHERE id = ?"
        cursor = execute_query(query, (zakladka_id,))
        if cursor and cursor.rowcount > 0:
             
             return jsonify({'message': 'Record deleted successfully'}), 200
        else:
            logging.warning(f"delete_employee_zakladka: Не найдена закладка id: {zakladka_id} в {table_name}")
            return jsonify({'message': 'Record not found'}), 404

    except Exception as e:
        logging.error(f"Error in delete_employee_zakladka: {e}")
        return jsonify({'error': 'An error occurred'}), 500
    finally:
       if cursor:
         cursor.close()
       db_manager.release_connection(conn)

@app.template_filter('calculate_month_earnings')
def calculate_month_earnings_filter(month_stats):
    """Фильтр для шаблона для расчета общей суммы заработка за месяц."""
    total_month_earnings = 0
    for size_stats in month_stats.values():
        total_month_earnings += size_stats['earnings']
    return total_month_earnings

@app.template_filter('format_decimal')
def format_decimal_filter(value):
   """Форматирует Decimal в строку с двумя знаками после запятой."""
   if isinstance(value, Decimal):
      return f"{value:.2f}"
   return value

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=50065)