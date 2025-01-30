import logging
from aiogram import Dispatcher, types
from aiogram.types import Message

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)


def register_reviews_handler(dp: Dispatcher):
    @dp.message(lambda message: message.text == "Отзывы / Reviews")
    async def reviews_handler(message: types.Message):
        user_id = message.from_user.id
        logging.info(f"reviews.py - reviews_handler: User {user_id} requested reviews") # User {user_id} requested reviews
        await message.answer(
            "🇷🇺Отзывы о наших товарах вы можете посмотреть тут: https://t.me/+zoNnrD4IbotiMWM1\n"
            "____________________________________\n\n"
             "🇺🇸You can see reviews of our products here: https://t.me/+zoNnrD4IbotiMWM1"
        )