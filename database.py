import datetime
import sqlite3
import logging
import threading
import os
from decimal import Decimal
from typing import Dict, Optional, List
import json
import re
from werkzeug.security import generate_password_hash, check_password_hash
import time

logging.basicConfig(
    level=logging.DEBUG, # <-- изменили INFO на DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

# Получаем абсолютный путь к корневой директории (где находится database.py)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATABASE_NAME = os.path.join(PROJECT_ROOT, "bot.db")


class DatabaseManager:
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        with cls._lock:
          if not cls._instance:
             cls._instance = super(DatabaseManager, cls).__new__(cls)
             cls._instance._pool = []
             cls._instance._max_connections = 100 #Увеличил до 100
             cls._instance._pool_lock = threading.Lock()
             cls._instance._create_connection_once()
        return cls._instance
    def _create_connection_once(self):
        """Создает первое соединение и гарантирует, что это происходит только раз"""
        conn = self._create_connection()
        if conn:
            self._pool.append(conn)
        else:
            logging.critical("database.py - DatabaseManager: Не удалось создать начальное соединение с БД.")
            exit(1)
    def _create_connection(self):
        """Создает новое подключение к базе данных."""
        try:
            conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
            logging.info("database.py - DatabaseManager: Подключение к БД установлено.")
            return conn
        except sqlite3.Error as e:
            logging.error(f"database.py - DatabaseManager: Ошибка подключения к БД: {e}")
            return None
    def get_connection(self):
        """Получает соединение из пула, либо создает новое если это возможно"""
        max_retries = 5
        retry_delay = 0.1
        for attempt in range(max_retries):
            with self._pool_lock:
                if self._pool:
                    return self._pool.pop()
                if len(self._pool) < self._max_connections:
                    conn = self._create_connection()
                    if conn:
                        logging.debug("database.py - DatabaseManager: Создали новое соединение")
                        return conn
            logging.debug(f"database.py - DatabaseManager: Нет свободных соединений ({len(self._pool)}/{self._max_connections}), запрос ждет")
            time.sleep(retry_delay)
        logging.error(f"database.py - DatabaseManager: Не удалось получить соединение из пула после {max_retries} попыток")
        return None

    def release_connection(self, conn):
        """Возвращает соединение в пул."""
        if conn:
            with self._pool_lock:
                if len(self._pool) < self._max_connections:
                   self._pool.append(conn)
                   logging.debug("database.py - DatabaseManager: Соединение возвращено в пул")
                else:
                   conn.close()
                   logging.debug("database.py - DatabaseManager: Соединение закрыто (слишком много соединений)")

    def close_all_connections(self):
        """Закрывает все соединения в пуле."""
        with self._pool_lock:
          for conn in self._pool:
               conn.close()
          self._pool.clear()
          logging.info("database.py - DatabaseManager: Все соединения в пуле закрыты.")

    def create_tables(self):
        """Создает необходимые таблицы, если их нет."""
        conn = self.get_connection()
        if not conn:
            logging.error("database.py - create_tables: Не удалось получить соединение из пула.")
            return
        try:
            cursor = conn.cursor()
            
             # -- 1. users --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    balance REAL DEFAULT 0,
                    referral_purchases_amount REAL DEFAULT 0,
                    username TEXT,
                    FOREIGN KEY (referred_by) REFERENCES users(user_id)
                )
            """)
            # -- 2. categories --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE
                )
            """)

            # -- 3. locations --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT,
                    district TEXT,
                    UNIQUE(city, district)
                )
            """)

            # -- 4. products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    category_id INTEGER,
                    price REAL,
                    description TEXT,
                    image TEXT,
                    name_en TEXT,
                    FOREIGN KEY (category_id) REFERENCES categories(id)
                )
            """)

            # -- 5. product_locations --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_locations (
                    product_id INTEGER,
                    location_id INTEGER,
                    PRIMARY KEY (product_id, location_id),
                    FOREIGN KEY (product_id) REFERENCES products(id),
                    FOREIGN KEY (location_id) REFERENCES locations(id)
                )
            """)
            # -- 6. paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 7. gr_1_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gr_1_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 8. gr_2_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gr_2_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 9. gr_5_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gr_5_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 10. gr_10_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gr_10_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)
             # -- 11. item_1_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_1_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 12. item_2_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_2_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 13. item_5_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_5_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 14. item_10_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_10_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 15. item_20_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_20_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)

            # -- 16. item_50_paid_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS item_50_paid_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)
            # -- 17. orders --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    product_name TEXT,
                    category TEXT,
                    city TEXT,
                    district TEXT,
                    status TEXT,
                    amount REAL,
                    payment_id TEXT,
                    crypto_amount TEXT,
                    product_id INTEGER
                )
            """)
            # -- 18. referrals --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referral_id INTEGER NOT NULL,
                    username TEXT,
                    purchases_count INTEGER DEFAULT 0,
                    purchases_amount REAL DEFAULT 0,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                    FOREIGN KEY (referral_id) REFERENCES users(user_id)
                )
            """)
            # -- 19. wallets --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    address TEXT
                )
            """)
             # -- 20. tickets --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            # -- 21. settings --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    name TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # -- 22. sold_products --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sold_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT,
                    instruction TEXT,
                    city TEXT,
                    district TEXT,
                    username TEXT,
                    price REAL,
                    category_name TEXT,
                    images TEXT,
                    sale_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # -- 23. employees --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL CHECK( role IN ('admin', 'samurai', 'ninja'))
                )
            """)
            
            # -- 24. employee_expenses --
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL,
                    expense_date DATE NOT NULL,
                    expense_description TEXT NOT NULL,
                    expense_amount REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)            
             

            conn.commit()
            logging.info("database.py - create_tables: Таблицы созданы или уже существуют.")
        except sqlite3.Error as e:
            logging.error(f"database.py - create_tables: Ошибка создания таблицы: {e}")
        finally:
            self.release_connection(conn)


db_manager = DatabaseManager()

def get_user(user_id):
    """Получает информацию о пользователе из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_user: Не удалось получить соединение из пула.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user_data = cursor.fetchone()
        logging.info(f"database.py - get_user: Пользователь с ID {user_id} получен из БД")
        logging.debug(f"database.py - get_user: User data: {user_data}")
        return user_data
    except sqlite3.Error as e:
        logging.error(f"database.py - get_user: Ошибка при получении пользователя: {e}")
        return None
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def add_user(user_id, referral_code, referred_by=None, username=None):  # Добавили username
    """Добавляет нового пользователя в базу данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - add_user: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, referral_code, referred_by, username) VALUES (?, ?, ?, ?)",
                       (user_id, referral_code, referred_by, username))
        conn.commit()
        logging.info(f"database.py - add_user: Пользователь с ID {user_id} добавлен в БД.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_user: Ошибка при добавлении пользователя: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)

def add_to_user_balance(user_id, amount):
    """Добавляет сумму к балансу пользователя в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - add_to_user_balance: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance=balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        logging.info(f"database.py - add_to_user_balance: Баланс пользователя с ID {user_id} увеличен на {amount}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_to_user_balance: Ошибка при добавлении суммы к балансу пользователя: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def set_user_balance(user_id, new_balance):
    """Устанавливает точное значение баланса пользователя в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - set_user_balance: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
        conn.commit()
        logging.info(f"database.py - set_user_balance: Баланс пользователя с ID {user_id} установлен на {new_balance}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - set_user_balance: Ошибка при установке баланса пользователя: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def set_referrer_balance(user_id, new_balance):
    """Устанавливает баланс реферера в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - set_referrer_balance: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user_id))
        conn.commit()
        logging.info(f"database.py - set_referrer_balance: Баланс рефера пользователя с ID {user_id} обновлен на {new_balance}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - set_referrer_balance: Ошибка при обновлении баланса реферера: {e}")
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)

def update_paid_products_prices(product_name, category_name, city, discount):
    """Обновляет цены на товары в указанном городе и категории для всех таблиц."""
    conn = db_manager.get_connection()
    if not conn:
            logging.error(
                "database.py - update_paid_products_prices: Соединение с БД не установлено.")
            return False
    try:
        table_names = [
            "gr_1_paid_products", "gr_2_paid_products", "gr_5_paid_products", "gr_10_paid_products",
            "item_1_paid_products", "item_2_paid_products", "item_5_paid_products",
            "item_10_paid_products", "item_20_paid_products", "item_50_paid_products"
        ]

        for table_name in table_names:
            query = f"""
              UPDATE {table_name}
                SET price = (price * (1 + ? / 100))
              WHERE SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1) = ?
                AND city = ?
                AND category_name = ?
            """
            execute_query(query, (float(discount), product_name, city, category_name))
            
        logging.info(f"database.py - update_paid_products_prices: Цены обновлены для {product_name} в {city}, discount={discount}")
        return True
    
    except sqlite3.Error as e:
        logging.error(f"database.py - update_paid_products_prices: Ошибка при обновлении цен: {e}")
        return False
    finally:
        db_manager.release_connection(conn)

def set_paid_products_original_price(product_name, category_name, city):
    """Устанавливает оригинальные цены на товары в указанном городе и категории для всех таблиц."""
    conn = db_manager.get_connection()
    if not conn:
            logging.error("database.py - set_paid_products_original_price: Соединение с БД не установлено.")
            return False
    try:
        table_names = [
            "gr_1_paid_products", "gr_2_paid_products", "gr_5_paid_products", "gr_10_paid_products",
            "item_1_paid_products", "item_2_paid_products", "item_5_paid_products",
            "item_10_paid_products", "item_20_paid_products", "item_50_paid_products"
        ]

        for table_name in table_names:
            # Используем регулярное выражение для поиска числа в имени таблицы (граммовка)
            match = re.search(r'[-_](\d+)', table_name)
            multiplier = 1.0
            if match:
                multiplier = float(match.group(1))  # Извлекаем множитель граммовки из имени таблицы
            
            # Получаем оригинальную цену за 1 грамм из таблицы `products`
            query_get_base_price = "SELECT price FROM products WHERE name LIKE ?"
            base_product_name = product_name.split(' ')[0]  # Извлекаем только название продукта без граммовки
            original_price_row = execute_query(query_get_base_price, (base_product_name,), fetch=True, fetch_one_flag=True)

            if not original_price_row or original_price_row[0] is None:
                logging.warning(f"database.py - set_paid_products_original_price: Не найдена оригинальная цена для товара {product_name}")
                continue
            original_price = float(original_price_row[0])

            # Рассчитываем новую цену с учетом граммовки
            new_price = original_price * multiplier

            # Обновляем цену в таблице
            query = f"""
                UPDATE {table_name}
                SET price = ?
                WHERE SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1) = ?
                  AND city = ?
                  AND category_name = ?
            """
            execute_query(query, (new_price, base_product_name, city, category_name))

        logging.info(f"database.py - set_paid_products_original_price: Цены установлены в оригинальные для {product_name} в {city}")
        return True

    except sqlite3.Error as e:
        logging.error(f"database.py - set_paid_products_original_price: Ошибка при установке цен в оригинальные: {e}")
        return False
    finally:
        db_manager.release_connection(conn)


def update_referral_purchases_amount(user_id, amount):
    """Обновляет сумму покупок рефералов пользователя в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - update_referral_purchases_amount: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        # Используем actual_amount
        cursor.execute("UPDATE users SET referral_purchases_amount = referral_purchases_amount + ? WHERE user_id=?",
                       (amount, user_id))
        conn.commit()
        logging.info(
            f"database.py - update_referral_purchases_amount: Сумма покупок рефералов пользователя с ID {user_id} увеличена на {amount}")
    except sqlite3.Error as e:
        logging.error(
            f"database.py - update_referral_purchases_amount: Ошибка при обновлении суммы покупок рефералов {e}")
    finally:
        if cursor:
           cursor.close()
        db_manager.release_connection(conn)

def update_referral_purchases_count_column(referrer_id, referral_id, amount):
    """Обновляет количество покупок реферала у реферера в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - update_referral_purchases_count_column: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE referrals SET purchases_count = purchases_count + 1, purchases_amount = purchases_amount + ? WHERE referrer_id=? AND referral_id=?",
                       (float(amount), referrer_id, referral_id))
        conn.commit()
        logging.info(
            f"database.py - update_referral_purchases_count_column: Количество покупок реферала {referral_id} у реферера с ID {referrer_id} увеличено на 1, purchases_amount = {amount}")
    except sqlite3.Error as e:
        logging.error(
            f"database.py - update_referral_purchases_count_column: Ошибка при обновлении количества покупок реферала: {e}")
    finally:
        if cursor:
           cursor.close()
        db_manager.release_connection(conn)


def get_referral_purchases_count(user_id):
    """Получает количество рефералов пользователя которые совершили покупки."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_referral_purchases_count: Не удалось получить соединение из пула.")
        return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(purchases_count) FROM referrals WHERE referrer_id=?", (user_id,))
        total_purchases = cursor.fetchone()
        if total_purchases and total_purchases[0]:
             logging.info(
                f"database.py - get_referral_purchases_count: Сумма покупок рефералов пользователя с ID {user_id} = {total_purchases[0]}.")
             return total_purchases[0]
        else:
             logging.info(
                 f"database.py - get_referral_purchases_count: Сумма покупок рефералов пользователя с ID {user_id} = 0 (or None).")
             return 0
    except sqlite3.Error as e:
        logging.error(
            f"database.py - get_referral_purchases_count: Ошибка при получении количества рефералов совершивших покупки {e}")
        return 0
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)


def get_all_users():
    """Получает всех пользователей из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_all_users: Не удалось получить соединение из пула.")
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, referral_code FROM users")
        all_users = cursor.fetchall()
        logging.info(f"database.py - get_all_users: Получены все пользователи из БД")
        return all_users
    except sqlite3.Error as e:
        logging.error(f"database.py - get_all_users: Ошибка при получении всех пользователей: {e}")
        return []
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)


def add_sold_product(product_name, instruction, city, district, username, price, category_name, images=None):
    """Добавляет запись о проданном продукте в базу данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - add_sold_product: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sold_products (product_name, instruction, city, district, username, price, category_name, images) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (product_name, instruction, city, district, username, price, category_name, images)
        )
        conn.commit()
        logging.info(
            f"database.py - add_sold_product: Запись о проданном продукте '{product_name}' добавлена в sold_products. username={username}")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_sold_product: Ошибка при добавлении записи о проданном продукте: {e}")
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)

def add_order(order):
    """Добавляет новый ордер в таблицу orders."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - add_order: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        logging.info(f"database.py - add_order: Добавляем ордер: {order}")

        cursor.execute("""
            INSERT INTO orders (id, user_id, product_name, category, city, district, status, amount, payment_id, crypto_amount, product_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order.get('id'),
            order.get('user_id'),
            order.get('product_name'),
            order.get('category'),
            order.get('city'),
            order.get('district'),
            order.get('status'),
            float(order.get('amount')) if order.get('amount') else None,
            order.get('payment_id'),
            str(order.get('crypto_amount')) if order.get('crypto_amount') is not None else None,
            order.get('product_id')
        ))
        conn.commit()
        logging.info(f"database.py - add_order: Запись о заказе добавлена.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_order: Ошибка при добавлении записи о заказе: {e}")
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)


def add_paid_product(product_name, instruction, city, district, price, category_name, images=None, selected_value=None, selected_type=None, employee_id=None, created_at=None):
    """Добавляет запись о купленном продукте в базу данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - add_paid_product: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        
        if selected_type and selected_value:
            table_name = get_paid_products_table_name(selected_type, selected_value)
            product_name = f"{product_name} {selected_value}{'гр' if selected_type == 'gram' else 'шт'}"
            if not created_at:
                created_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
             # Insert data into the selected table
            cursor.execute(
                f"INSERT INTO {table_name} (product_name, instruction, city, district, price, category_name, images, employee_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (product_name, instruction, city, district, price, category_name, str(images), employee_id, created_at)
            )
            conn.commit()
            logging.info(
                f"database.py - add_paid_product: Запись о покупке продукта '{product_name}' добавлена в {table_name}.")
        else:
           if not created_at:
                created_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
           cursor.execute(
                "INSERT INTO paid_products (product_name, instruction, city, district, price, category_name, images, employee_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (product_name, instruction, city, district, price, category_name, str(images), employee_id, created_at)
            )
           conn.commit()
           logging.info(
                f"database.py - add_paid_product: Запись о покупке продукта '{product_name}' добавлена в paid_products.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_paid_product: Ошибка при добавлении записи о купленном продукте: {e}")
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)


def get_referral_count(user_id):
    """Получает количество рефералов пользователя."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_referral_count: Не удалось получить соединение из пула.")
         return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        referral_count = cursor.fetchone()[0]
        logging.info(f"database.py - get_referral_count: Количество рефералов пользователя с ID {user_id} = {referral_count}.")
        return referral_count
    except sqlite3.Error as e:
        logging.error(f"database.py - get_referral_count: Ошибка при получении количества рефералов: {e}")
        return 0
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_referral_purchases_amount(user_id):
    """Получает сумму покупок рефералов пользователя."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_referral_purchases_amount: Не удалось получить соединение из пула.")
         return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT referral_purchases_amount FROM users WHERE user_id=?", (user_id,))
        total_purchases_amount = cursor.fetchone()
        if total_purchases_amount and total_purchases_amount[0]:
            logging.info(
                f"database.py - get_referral_purchases_amount: Сумма покупок рефералов пользователя с ID {user_id} = {total_purchases_amount[0]}.")
            return total_purchases_amount[0]
        else:
            logging.info(
                f"database.py - get_referral_purchases_amount: Сумма покупок рефералов пользователя с ID {user_id} = 0 (or None).")
            return 0
    except sqlite3.Error as e:
        logging.error(f"database.py - get_referral_purchases_amount: Ошибка при получении суммы покупок рефералов: {e}")
        return 0
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_referral_purchases_count(user_id):
    """Получает количество рефералов пользователя которые совершили покупки."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_referral_purchases_count: Не удалось получить соединение из пула.")
         return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by=? AND balance > 0", (user_id,))
        referral_purchases_count = cursor.fetchone()[0]
        logging.info(
            f"database.py - get_referral_purchases_count: Количество рефералов совершивших покупки пользователя с ID {user_id} = {referral_purchases_count}")
        return referral_purchases_count
    except sqlite3.Error as e:
        logging.error(
            f"database.py - get_referral_purchases_count: Ошибка при получении количества рефералов совершивших покупки {e}")
        return 0
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_user_balance(user_id):
    """Получает баланс пользователя из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_user_balance: Не удалось получить соединение из пула.")
        return 0
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()
        if balance and balance[0]:
            logging.info(f"database.py - get_user_balance: Баланс пользователя с ID {user_id} = {balance[0]}.")
            return balance[0]
        else:
            logging.info(f"database.py - get_user_balance: Баланс пользователя с ID {user_id} не найден.")
            return 0
    except sqlite3.Error as e:
        logging.error(f"database.py - get_user_balance: Ошибка при получении баланса пользователя {e}")
        return 0
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)

def add_referral_reward(referrer_id, amount):
    """
    Добавляет реферальное вознаграждение к балансу реферера.
    """
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - add_referral_reward: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        bonus_amount = Decimal(str(amount)) * Decimal("0.03")
        bonus_amount = round(bonus_amount, 2)
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(bonus_amount), referrer_id))
        conn.commit()
        logging.info(f"database.py - add_referral_reward: Рефереру {referrer_id} начислен бонус {bonus_amount:.2f} USD за покупку реферала.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_referral_reward: Ошибка при начислении реферального бонуса: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)

def update_referred_by(user_id, referred_by):
    """Обновляет реферера пользователя в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - update_referred_by: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET referred_by=? WHERE user_id=?", (referred_by, user_id))
        conn.commit()
        logging.info(f"database.py - update_referred_by: Реферер пользователя с ID {user_id} обновлен на {referred_by}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - update_referred_by: Ошибка при обновлении рефера пользователя: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def add_ticket(user_id, message):
    """Добавляет тикет в базу данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - add_ticket: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tickets (user_id, message) VALUES (?, ?)", (user_id, message))
        conn.commit()
        logging.info(f"database.py - add_ticket: Тикет пользователя с ID {user_id} добавлен в БД.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_ticket: Ошибка при добавлении тикета: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_user_tickets(user_id):
    """Получает все тикеты пользователя из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_user_tickets: Не удалось получить соединение из пула.")
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT message FROM tickets WHERE user_id=?", (user_id,))
        tickets = cursor.fetchall()
        logging.info(f"database.py - get_user_tickets: Получены тикеты пользователя с ID {user_id} из БД")
        return [ticket[0] for ticket in tickets]
    except sqlite3.Error as e:
        logging.error(f"database.py - get_user_tickets: Ошибка при получении тикетов пользователя: {e}")
        return []
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def delete_user(user_id):
    """Удаляет пользователя из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - delete_user: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
        logging.info(f"database.py - delete_user: Пользователь с ID {user_id} удален из БД.")
    except sqlite3.Error as e:
        logging.error(f"database.py - delete_user: Ошибка при удалении пользователя: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_user_by_username(username):
    """Получает информацию о пользователе из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_user_by_username: Не удалось получить соединение из пула.")
         return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=?", (username,))
        user_data = cursor.fetchone()
        logging.info(f"database.py - get_user_by_username: Пользователь с логином {username} получен из БД")
        return user_data
    except sqlite3.Error as e:
        logging.error(f"database.py - get_user_by_username: Ошибка при получении пользователя: {e}")
        return None
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)
      
def get_employee_by_username(username):
        """Получает данные сотрудника по имени пользователя."""
        conn = db_manager.get_connection() # исправил вызов db_manager
        if not conn:
            logging.error("database.py - get_employee_by_username: Не удалось получить соединение из пула.")
            return None
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM employees WHERE username=?", (username,))
            employee_data = cursor.fetchone()
            if employee_data:
                logging.info(f"database.py - get_employee_by_username: Сотрудник с логином {username} получен из БД")
                return dict(zip([column[0] for column in cursor.description], employee_data))
            else:
                logging.warning(f"database.py - get_employee_by_username: Сотрудник с логином {username} не найден.")
                return None
        except sqlite3.Error as e:
            logging.error(f"database.py - get_employee_by_username: Ошибка при получении данных сотрудника: {e}")
            return None
        finally:
            if cursor:
              cursor.close()
            db_manager.release_connection(conn)

def add_employee(username, password, role):
        """Добавляет нового сотрудника в базу данных."""
        conn = db_manager.get_connection() # исправил вызов db_manager
        if not conn:
            logging.error("database.py - add_employee: Не удалось получить соединение из пула.")
            return
        cursor = None
        try:
            cursor = conn.cursor()
            hashed_password = generate_password_hash(password)
            cursor.execute("INSERT INTO employees (username, password, role) VALUES (?, ?, ?)",
                        (username, hashed_password, role))
            conn.commit()
            logging.info(f"database.py - add_employee: Сотрудник с логином {username} добавлен в БД.")
        except sqlite3.Error as e:
            logging.error(f"database.py - add_employee: Ошибка при добавлении сотрудника: {e}")
        finally:
            if cursor:
                cursor.close()
            db_manager.release_connection(conn)          

def update_username_query(user_id, username):
    """Обновляет логин пользователя в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - update_username_query: Не удалось получить соединение из пула.")
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()
        logging.info(f"database.py - update_username_query: Логин пользователя с ID {user_id} обновлен на {username}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - update_username_query: Ошибка при обновлении логина пользователя: {e}")
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)


def add_referral(referrer_id, referral_id, username):
    """Добавляет запись о реферале в базу данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - add_referral: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO referrals (referrer_id, referral_id, username) VALUES (?, ?, ?)",
                       (referrer_id, referral_id, username))
        conn.commit()
        logging.info(
            f"database.py - add_referral: Реферал пользователя с ID {referral_id} добавлен к рефереру {referrer_id}.")
    except sqlite3.Error as e:
        logging.error(f"database.py - add_referral: Ошибка при добавлении реферала: {e}")
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_user_sold_products(username):
    """Получает список проданных продуктов пользователя из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_user_sold_products: Не удалось получить соединение из пула.")
         return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                product_name, city, district, instruction, price, sale_date, images,
                CASE 
                   WHEN product_name LIKE (SELECT name || '%гр' FROM products WHERE name=SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1)) THEN 'gram'
                   WHEN product_name LIKE (SELECT name || '%шт' FROM products WHERE name=SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1)) THEN 'item'
                    ELSE 'paid_products' 
                END AS table_name,
                 CASE
                    WHEN product_name LIKE (SELECT name || '% гр' FROM products WHERE name=SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1)) THEN SUBSTR(product_name, INSTR(product_name, ' ') + 1)
                    WHEN product_name LIKE (SELECT name || '% шт' FROM products WHERE name=SUBSTR(product_name, 1, INSTR(product_name, ' ') - 1)) THEN SUBSTR(product_name, INSTR(product_name, ' ') + 1)
                    ELSE ''
                END AS selected_value
            FROM sold_products WHERE username=?""",
                       (username,))
        sold_products = cursor.fetchall()
        logging.info(
            f"database.py - get_user_sold_products: Получены проданные продукты для пользователя с логином {username}")
        # Преобразуем результаты в список словарей
        return [
            {"product_name": item[0], "city": item[1], "district": item[2], "instruction": item[3], "price": item[4],
             "sale_date": item[5], "images": item[6], "table_name":item[7], "selected_value":item[8]}
            for item in sold_products
        ]
    except sqlite3.Error as e:
        logging.error(f"database.py - get_user_sold_products: Ошибка при получении проданных продуктов: {e}")
        return []
    finally:
      if cursor:
         cursor.close()
      db_manager.release_connection(conn)


def get_support_channel_id():
    """Получает ID канала поддержки из таблицы settings."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_support_channel_id: Не удалось получить соединение из пула.")
         return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE name='support_channel_id'")
        result = cursor.fetchone()
        if result and result[0]:
            logging.info(f"database.py - get_support_channel_id: support_channel_id = {result[0]}")
            return result[0]
        else:
            logging.warning(f"database.py - get_support_channel_id: No support_channel_id found in settings")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_support_channel_id: Ошибка при получении ID канала поддержки: {e}")
        return None
    finally:
        if cursor:
          cursor.close()
        db_manager.release_connection(conn)


def set_support_channel_id(channel_id):
    """Устанавливает ID канала поддержки в таблице settings."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - set_support_channel_id: Не удалось получить соединение из пула.")
         return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?)",
                       ("support_channel_id", channel_id))
        conn.commit()
        logging.info(f"database.py - set_support_channel_id: ID канала поддержки установлен в {channel_id}")
    except sqlite3.Error as e:
        logging.error(f"database.py - set_support_channel_id: Ошибка при установке ID канала поддержки: {e}")
    finally:
        if cursor:
          cursor.close()
        db_manager.release_connection(conn)


def get_all_locations():
  """Получает все локации из базы данных."""
  conn = db_manager.get_connection()
  if not conn:
      logging.error("database.py - get_all_locations: Не удалось получить соединение из пула.")
      return None
  cursor = None
  try:
    cursor = conn.cursor()
    cursor.execute("SELECT id, city, district FROM locations")
    locations = []
    rows = cursor.fetchall()
    for row in rows:
      location = {
        "id": row[0],
        "city": row[1],
        "district": row[2],
      }
      locations.append(location)

    return locations
  except sqlite3.Error as e:
     logging.error(f"database.py - get_all_locations: ERROR:  {e}", exc_info=True)
     return []
  finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def get_product_by_name(name: str) -> Optional[Dict]:
    """
    Получает продукт из базы данных по названию.
    
    Args:
        name (str): Название продукта.
    
    Returns:
        Optional[Dict]: Словарь с информацией о продукте или None, если не найден.
    """
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_product_by_name: Не удалось подключиться к базе данных.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name, description, image FROM products WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            images = row[2].split(',') if row[2] else []
            return {
                "name": row[0],
                "description": row[1],
                "images": images  # Список путей к изображениям
            }
        else:
            logging.warning(f"get_product_by_name: Продукт '{name}' не найден.")
            return None
    except sqlite3.Error as e:
        logging.error(f"get_product_by_name: Ошибка при получении продукта: {e}")
        return None
    finally:
        if cursor:
           cursor.close()
        db_manager.release_connection(conn)

def get_all_products():
    """Получает все продукты из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_all_products: Не удалось получить соединение из пула.")
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, category_id, price, description, image, name_en FROM products")
        products = cursor.fetchall()
        logging.info(f"database.py - get_all_products: Получены все продукты из БД")
        return [
            {
                "id": item[0], "name": item[1],
                "category_id": item[2], "price": item[3],
                "description": item[4],
                "image": item[5].split(',') if item[5] else None,
                "name_en": item[6],  # Добавлено
                "locations": get_product_locations(item[0])  # Добавили получение локаций
            }
            for item in products
        ]
    except sqlite3.Error as e:
        logging.error(f"database.py - get_all_products: Ошибка при получении всех продуктов: {e}")
        return []
    finally:
        if cursor:
          cursor.close()
        db_manager.release_connection(conn)


def get_product_locations(product_id):
    """Получает локации продукта из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_product_locations: Не удалось получить соединение из пула.")
         return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT l.city, l.district
            FROM product_locations pl
            JOIN locations l ON pl.location_id = l.id
            WHERE pl.product_id = ?
        """, (product_id,))
        locations = cursor.fetchall()
        logging.info(f"database.py - get_product_locations: Получены локации для продукта с ID {product_id}")
        return [{"city": loc[0], "district": loc[1]} for loc in locations]
    except sqlite3.Error as e:
        logging.error(f"database.py - get_product_locations: Ошибка при получении локаций продукта: {e}")
        return []
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)


def get_product_category(product_name):
    """Получает категорию продукта из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_product_category: Не удалось получить соединение из пула.")
         return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.name
            FROM categories c
            JOIN products p ON c.id = p.category_id
            WHERE p.name = ?
        """, (product_name,))
        category = cursor.fetchone()
        if category and category[0]:
            logging.info(f"database.py - get_product_category: Категория продукта '{product_name}' = '{category[0]}'")
            return category[0]
        else:
            logging.warning(f"database.py - get_product_category: Категория продукта '{product_name}' не найдена.")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_product_category: Ошибка при получении категории продукта: {e}")
        return None
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)

def get_wallet_address(wallet_name):
    """Получает адрес кошелька из базы данных по имени."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_wallet_address: Не удалось получить соединение из пула.")
         return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT address FROM wallets WHERE name=?", (wallet_name,))
        result = cursor.fetchone()
        if result:
            logging.info(f"database.py - get_wallet_address: Адрес кошелька '{wallet_name}' = '{result[0]}'")
            return result[0]  # Возвращаем адрес кошелька
        else:
            logging.warning(f"database.py - get_wallet_address: Кошелек '{wallet_name}' не найден.")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_wallet_address: Ошибка при получении адреса кошелька: {e}")
        return None
    finally:
        if cursor:
          cursor.close()
        db_manager.release_connection(conn)

def get_product_price(product_id):
    """Получает цену продукта из таблицы 'products'."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_product_price: ERROR: Не удалось подключиться к базе данных.")
        return None
    cursor = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT price FROM products WHERE id=?", (product_id,))
        price_info = cur.fetchone()
        if price_info:
            return price_info[0]
        else:
            logging.warning(f"database.py - get_product_price: WARNING: цена для продукта с ID {product_id} не найдена")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_product_price: ERROR: {e}", exc_info=True)
    finally:
        if cursor:
           cursor.close()
        db_manager.release_connection(conn)


def get_available_products(city, district, product_id):
    """Получает список доступных товаров (названий) по городу и району с учетом product_id."""
    conn = db_manager.get_connection()
    available_products = []
    
    if not conn:
        logging.error("database.py - get_available_products: ERROR: Не удалось подключиться к базе данных.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        
        # 1. Проверяем таблицы с граммами
        gram_products = [1, 3, 4, 5, 6, 7, 12, 13, 14, 15]
        if product_id in gram_products:
            for gram in [1, 2, 5, 10]:
                table_name = f"gr_{gram}_paid_products"
                query = f"""
                    SELECT product_name, price 
                    FROM {table_name} 
                    WHERE city=? AND district=? AND product_name LIKE (SELECT name || '%' FROM products WHERE id=?)
                    """
                cursor.execute(query, (city, district, product_id))
                products = cursor.fetchall()
                if products:
                    for product in products:
                       available_products.append(
                         {
                          "product_name":product[0],
                            "price":product[1]
                          }
                       )
                    logging.info(f"database.py - get_available_products: Found gram products in table {table_name} for city={city}, district={district}, product_id={product_id}")

        # 2. Проверяем таблицы с штуками
        item_products = [2, 8, 9, 10, 11]
        if product_id in item_products:
             for item in [1, 2, 5, 10, 20, 50]:
                table_name = f"item_{item}_paid_products"
                query = f"""
                     SELECT product_name, price 
                    FROM {table_name} 
                    WHERE city=? AND district=? AND product_name LIKE (SELECT name || '%' FROM products WHERE id=?)
                    """
                cursor.execute(query, (city, district, product_id))
                products = cursor.fetchall()
                if products:
                    for product in products:
                         available_products.append(
                            {
                             "product_name":product[0],
                               "price":product[1]
                             }
                            )
                    logging.info(f"database.py - get_available_products: Found item products in table {table_name} for city={city}, district={district}, product_id={product_id}")
        if available_products:
           logging.info(f"database.py - get_available_products: Товары для города={city}, района={district}, product_id={product_id}: {', '.join([prod['product_name'] for prod in available_products])}")
        else:
           logging.warning(f"database.py - get_available_products: Не найдены товары для города={city}, района={district}, product_id={product_id}")

        return available_products
    
    except sqlite3.Error as e:
        logging.error(f"database.py - get_available_products: Ошибка при получении списка товаров: {e}")
        return None
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)
            
def get_location_info_from_paid_products(product_name, city, district, role=None, user_id=None):
    """
    Ищет товар по product_name, city и district сразу во ВСЕХ таблицах.
    Возвращает список словарей (или None), если не найдено.
    """
    conn = db_manager.get_connection()
    if not conn:
        logging.error("get_location_info_from_paid_products: не удалось подключиться к базе данных.")
        return None

    # Все таблицы, где может лежать товар
    table_names = [
        "paid_products",
        "gr_1_paid_products",
        "gr_2_paid_products",
        "gr_5_paid_products",
        "gr_10_paid_products",
        "item_1_paid_products",
        "item_2_paid_products",
        "item_5_paid_products",
        "item_10_paid_products",
        "item_20_paid_products",
        "item_50_paid_products"
    ]

    results = []
    cursor = None
    try:
        cursor = conn.cursor()
        query = f"""
            SELECT  id, product_name, instruction, city, district, price, category_name, images, employee_id, created_at,
             CASE 
                WHEN product_name LIKE (SELECT name || '%гр' FROM products WHERE name=?) THEN 'gram'
                WHEN product_name LIKE (SELECT name || '%шт' FROM products WHERE name=?) THEN 'item'
                ELSE 'paid_products' 
                END AS table_name,
             CASE
                WHEN product_name LIKE (SELECT name || '% гр' FROM products WHERE name=?) THEN SUBSTR(product_name, INSTR(product_name, ' ') + 1)
                WHEN product_name LIKE (SELECT name || '% шт' FROM products WHERE name=?) THEN SUBSTR(product_name, INSTR(product_name, ' ') + 1)
                ELSE ''
            END AS selected_value
            FROM
            (
                SELECT * FROM paid_products
                UNION ALL
                SELECT * FROM gr_1_paid_products
                UNION ALL
                SELECT * FROM gr_2_paid_products
                UNION ALL
                SELECT * FROM gr_5_paid_products
                UNION ALL
                SELECT * FROM gr_10_paid_products
                UNION ALL
                 SELECT * FROM item_1_paid_products
                 UNION ALL
                 SELECT * FROM item_2_paid_products
                 UNION ALL
                SELECT * FROM item_5_paid_products
                UNION ALL
                SELECT * FROM item_10_paid_products
                UNION ALL
                SELECT * FROM item_20_paid_products
                 UNION ALL
                SELECT * FROM item_50_paid_products
            ) AS combined
            WHERE 
            city LIKE ?
            AND district LIKE ?
            AND product_name LIKE ?  COLLATE NOCASE
        """
        params = (product_name,product_name,product_name,product_name,f'%{city}%', f'%{district}%', f"%{product_name.split(' ')[0]}%")

        if role != 'admin' and user_id:
             query += "AND employee_id = ?"
             params = (product_name,product_name,product_name,product_name,f'%{city}%', f'%{district}%', f"%{product_name.split(' ')[0]}%", user_id)
        logging.debug(f"get_location_info_from_paid_products: SQL запрос: {query}, params = {params}")
        cursor.execute(query, params)
        rows = cursor.fetchall()

        if rows:
             logging.info(f"Найдены товары для {product_name}, city={city}, district={district} во множественных таблицах.")
             for row in rows:
                columns = ["id", "product_name", "instruction", "city", "district", "price", "category_name", "images", "employee_id", "created_at", "table_name", "selected_value"]
                result_dict = dict(zip(columns, row))
                results.append(result_dict)
             return results
        else:
             logging.warning(f"Не найдены товары для {product_name}, город={city}, район={district} во всех таблицах.")
             return None
    except sqlite3.Error as e:
        logging.error(f"get_location_info_from_paid_products: Ошибка при поиске: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)
        
def check_password(employee, password):
    """Проверяет хешированный пароль."""
    return check_password_hash(employee['password'], password)        

def move_paid_product_to_sold_products(product_name, city, district, username, paid_product_id, table_name):
    """Перемещает один конкретный товар из paid_products в sold_products по product_name, city, district и id."""
    conn = db_manager.get_connection()
    cursor = None
    if not conn:
        logging.error("database.py - move_paid_product_to_sold_products: Не удалось получить соединение из пула.")
        return False
    try:
        cursor = conn.cursor()
        # 1. Получаем данные из paid_products, включая id, выбираем один рандомно
        cursor.execute(
             f"SELECT id, product_name, instruction, city, district, price, category_name, images, employee_id, created_at FROM {table_name} WHERE id=?",
            (paid_product_id,)
        )
        paid_product_data = cursor.fetchone()
        if not paid_product_data:
            logging.warning(
                f"database.py - move_paid_product_to_sold_products: Запись в {table_name} не найдена для id: {paid_product_id}")
            return False

        product_id, product_name, instruction, city, district, price, category_name, images, employee_id, created_at = paid_product_data
        # 2. Записываем данные в sold_products
        cursor.execute("""
                INSERT INTO sold_products (product_name, instruction, city, district, username, price, category_name, images, sale_date, employee_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
            product_name,
            instruction,
            city,
            district,
            username,
            price,
            category_name,
            images,
            created_at,
            employee_id if employee_id else None, # Проверка employee_id == None
        ))

        # 3. Удаляем данные из paid_products по id
        cursor.execute(f"DELETE FROM {table_name} WHERE id=?", (paid_product_id,))
        conn.commit()
        logging.info(
            f"database.py - move_paid_product_to_sold_products: переместили запись из {table_name} в sold_products для продукта {product_name}, город={city}, район={district}, id = {paid_product_id}")
        return True
    except sqlite3.Error as e:
        logging.error(f"database.py - move_paid_product_to_sold_products: Ошибка при перемещении записи: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)

def get_employee_expenses(employee_id):
    """Получает все расходы сотрудника из базы данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_employee_expenses: Не удалось получить соединение из пула.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        query = """
            SELECT expense_date, expense_description, expense_amount, created_at FROM employee_expenses
            WHERE employee_id = ?
            ORDER BY expense_date DESC, created_at DESC
        """
        cursor.execute(query, (employee_id,))
        expenses = cursor.fetchall()
        if expenses:
            logging.info(f"database.py - get_employee_expenses: Получены расходы сотрудника с ID: {employee_id}")
            # Преобразуем результаты в список словарей
            columns = [col[0] for col in cursor.description]
            expenses_list = [dict(zip(columns, row)) for row in expenses]
            return expenses_list
        else:
            logging.info(f"database.py - get_employee_expenses: Не найдены расходы сотрудника с ID: {employee_id}")
            return []
    except Exception as e:
        logging.error(f"database.py - get_employee_expenses: Ошибка при получении расходов: {e}")
        return None
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)


def add_employee_expense(employee_id, expense_date, expense_description, expense_amount):
    """Добавляет запись о затратах сотрудника."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - add_employee_expense: Не удалось получить соединение из пула.")
        return False
    cursor = None
    try:
        query = """
            INSERT INTO employee_expenses (employee_id, expense_date, expense_description, expense_amount)
            VALUES (?, ?, ?, ?)
        """
        cursor = execute_query(query, (employee_id, expense_date, expense_description, expense_amount))
        
        if cursor:
            logging.info(f"database.py - add_employee_expense: Запись о затрате добавлена в базу данных. employee_id:{employee_id}")
            return True
        else:
            logging.error(f"database.py - add_employee_expense: Ошибка при добавлении затрат сотрудника. employee_id:{employee_id}")
            return False

    except Exception as e:
        logging.error(f"database.py - add_employee_expense: Ошибка: {e}")
        return False
    finally:
        if cursor:
           cursor.close()
        db_manager.release_connection(conn)

def get_paid_product_by_location(product_name, city, district, user_id):
    """Получает запись из paid_products по имени продукта, городу и району."""
    conn = db_manager.get_connection()
    if not conn:
         logging.error("database.py - get_paid_product_by_location: Не удалось получить соединение из пула.")
         return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM paid_products WHERE product_name=? AND city=? AND district=?",
            (product_name, city, district)
        )
        paid_product_data = cursor.fetchone()
        if paid_product_data:
            logging.info(
                f"database.py - get_paid_product_by_location: найден товар {product_name}, city={city}, district={district}")
            return dict(zip([column[0] for column in cursor.description], paid_product_data))
        else:
            logging.warning(
                f"database.py - get_paid_product_by_location: товар {product_name}, city={city}, district={district} не найден")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_paid_product_by_location: Ошибка при получении записи из paid_products: {e}")
        return None
    finally:
        if cursor:
          cursor.close()
        db_manager.release_connection(conn)

def update_order_status(order_id, status):
    """Обновляет статус заказа в таблице orders."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - update_order_status: Не удалось получить соединение из пула.")
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        conn.commit()
        # Если реально обновлена хотя бы 1 строка
        if cursor.rowcount > 0:
            logging.info(f"database.py - update_order_status: Статус заказа с ID {order_id} обновлен на '{status}'.")
            return True
        else:
            # Если заказы с таким ID не найдены
            logging.error(f"database.py - update_order_status: Не удалось обновить статус заказа {order_id}")
            return False
    except sqlite3.Error as e:
        logging.error(f"database.py - update_order_status: Ошибка при обновлении статуса заказа: {e}")
        return False
    finally:
      if cursor:
        cursor.close()
      db_manager.release_connection(conn)

def get_order_status(order_id):
    """Получает статус заказа из таблицы orders."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - get_order_status: Не удалось получить соединение из пула.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM orders WHERE id=?", (order_id,))
        result = cursor.fetchone()
        if result:
            status = result[0]
            logging.info(f"database.py - get_order_status: Статус заказа с ID {order_id} = '{status}'.")
            return status
        else:
            logging.warning(f"database.py - get_order_status: Заказ с ID {order_id} не найден.")
            return None
    except sqlite3.Error as e:
        logging.error(f"database.py - get_order_status: Ошибка при получении статуса заказа: {e}")
        return None
    finally:
      if cursor:
          cursor.close()
      db_manager.release_connection(conn)      

def get_all_base_product_names(city, district):
    """
    Возвращает множество (set) всех «коротких» названий товаров для указанного города и района.
    Например, если в таблице есть «КЕТАМИН 1гр», «КЕТАМИН 2гр», вернётся «{'КЕТАМИН'}».
    """
    conn = db_manager.get_connection()
    if not conn:
        logging.error("Не удалось подключиться к базе данных.")
        return set()

    table_names = [
        "gr_1_paid_products", "gr_2_paid_products", "gr_5_paid_products", "gr_10_paid_products",
        "item_1_paid_products", "item_2_paid_products", "item_5_paid_products", 
        "item_10_paid_products", "item_20_paid_products", "item_50_paid_products"
    ]
    
    base_names = set()
    cursor = None
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
                full_name = row[0]  # например, «КЕТАМИН 2гр»
                # «Обрезаем» последний блок (например, «2гр»), чтобы получить «КЕТАМИН»
                # Предполагаем, что всегда есть пробел перед «2гр», «1гр» и т.д.
                # Если знаете, что название вида «КЕТАМИН 2гр», то:
                short_name = full_name.rsplit(' ', 1)[0]  # Возьмёт всё до последнего пробела

                base_names.add(short_name)

        return base_names
    except sqlite3.Error as e:
        logging.error(f"Ошибка при получении коротких названий товаров: {e}")
        return set()
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)


def table_exists(table_name):
    """Проверяет существование таблицы в базе данных."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - table_exists: Не удалось получить соединение из пула.")
        return False
    try:
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?;"
        result = execute_query(query, (table_name,), fetch=True, fetch_one_flag=True)
        return result is not None
    except sqlite3.Error as e:
        logging.error(f"database.py - table_exists: Ошибка при проверке таблицы: {e}")
        return False
    finally:
        db_manager.release_connection(conn)
    

def get_paid_products_table_name(selected_type, selectedValue):
    if selected_type == "gram":
        return f"gr_{str(selectedValue)}_paid_products"  # Например, "gr_10_paid_products"
    elif selected_type == "item":
        return f"item_{str(selectedValue)}_paid_products"  # Например, "item_2_paid_products"
    else:
        raise ValueError("Invalid gram/item type")


def execute_query(query, params=(), fetch=False, fetch_one_flag=False):
    """Выполняет SQL-запрос. Может возвращать результат."""
    conn = db_manager.get_connection()
    if not conn:
        logging.error("database.py - execute_query: Соединение с БД не установлено.")
        return None
    cursor = None
    try:
        cursor = conn.cursor()

        cursor.execute(query, params)

        if fetch:
            if fetch_one_flag:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()
            logging.debug(
                f"database.py - execute_query: Выполнен запрос: {query}, с параметрами {params}, результат: {len(result) if isinstance(result, list) else result }.")
            return result
        else:
            conn.commit()
            logging.debug(f"database.py - execute_query: Выполнен запрос: {query}, с параметрами {params}.")
            return cursor
    except sqlite3.Error as e:
        logging.error(f"database.py - execute_query: Ошибка при выполнении запроса: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        db_manager.release_connection(conn)


__all__ = [
    "get_all_users", "get_user", "add_user", "update_username_query", "delete_user",
    "get_user_balance", "get_referral_count", "update_referral_purchases_amount",
    "get_referral_purchases_amount", "get_referral_purchases_count", "get_user_tickets", "add_ticket",
    "execute_query",
    "add_sold_product",
    "add_order",
    "add_paid_product",
    "update_referred_by",
    "add_referral",
    "get_user_sold_products",
    "get_support_channel_id",
    "set_support_channel_id",
    "get_all_locations",
    "get_all_products",
    "get_product_locations",
    "get_product_category",
    "get_wallet_address",
    "move_paid_product_to_sold_products",
    "get_paid_product_by_location",
    "update_order_status",
    "get_order_status",
    "table_exists", 
    "get_available_products",
    "get_paid_products_table_name",
    "update_paid_products_prices",
    "set_paid_products_original_price",
        "db_manager",
       "get_employee_expenses",
       "add_employee_expense"
]