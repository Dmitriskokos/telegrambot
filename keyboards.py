from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Заказать / Order"),
                KeyboardButton(text="Отзывы / Reviews"),
            ],
            [
                KeyboardButton(text="Саппорт / Support"),
                KeyboardButton(text="Работа / Jobs"),
            ],
            [
                 KeyboardButton(text="Профиль / Account"),
            ],
            [
                KeyboardButton(text="Наш чат / Our Chat")
            ]
        ],
        resize_keyboard=True
    )
    return keyboard