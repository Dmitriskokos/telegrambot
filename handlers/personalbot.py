import logging
import uuid

from aiogram import Bot, Dispatcher, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_personal_bot_info


async def personal_bot_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - personalbot.py - personal_bot_handler: User {user_id} pressed 'Персональный бот'") # User {user_id} pressed 'Personal bot'

    # Получаем информацию о персональном боте из БД
    user_bot_info = get_personal_bot_info(user_id)
    if user_bot_info and user_bot_info.get("personal_bot_username"):
        bot_username = user_bot_info.get("personal_bot_username")
        await callback.message.answer(
        f"У вас уже есть персональный бот @{bot_username}\n\n"
        "Если вы хотите переподключить нового - воспользуйтесь инструкцией:\n\n"
        "1. Перейдите в бот - https://t.me/BotFather\n"
        "2. Нажмите кнопку \"START\"\n"
        "3. Введите команду \"/newbot\"\n"
        "4. Придумайте и введите название бота, название подойдет любое\n"
        "5. Придумайте и введите юзернейм (username) бота, подойдут любые латинские буквы, главное чтобы юзернейм оканчивался на \"bot\"\n"
        "6. Если Вы все сделали верно, Вам придет сообщение, которое начинается на:\n\n"
        "Done! Congratulations on your new bot.\n\n"
        "В данном сообщении будет набор букв и цифр в формате:\n\n"
        "<code>1111111111:AAAAAAAAAAAAAA_GchLGbMkBdSBRIEspy11</code>\n\n"
        "7. Нажмите на данный текст, он скопируется и зайдите на этот бот и пишите вот так \n"
        "Вы должны сначала написать /bot, затем вставить выданный вам токен, и для вас будет создан специальный бот.\n\n"
        "Пример команды :\n\n"
        "<code>/bot 1111111111:AAAAAAAAAA_GchLGbMkBdSBRIEspy11</code>\n\n"
        "бот вышлет ссылку на ваш бот - покупайте через него\n", parse_mode="HTML", disable_web_page_preview=True)
    else:
      text = (
            "🤖 <b>Подключение собственного бота</b>\n\n"
            "Бонус на баланс за подключение: 20 $ единоразово\n"
            "Собственный бот позволит Вам всегда оставаться \"в зоне покупок\", при блокировке основного бота у Вас будет возможность приобрести товар в нем, таким образом - мы никогда не потеряем с Вами связь!\n\n"
            "Инструкция по созданию и подключению бота:\n\n"
            "1. Перейдите в бот - https://t.me/BotFather\n"
            "2. Нажмите кнопку \"START\"\n"
            "3. Введите команду \"/newbot\"\n"
            "4. Придумайте и введите название бота, название подойдет любое\n"
            "5. Придумайте и введите юзернейм (username) бота, подойдут любые латинские буквы, главное чтобы юзернейм оканчивался на \"bot\"\n"
            "6. Если Вы все сделали верно, Вам придет сообщение, которое начинается на:\n\n"
            "Done! Congratulations on your new bot.\n\n"
            "В данном сообщении будет набор букв и цифр в формате:\n\n"
            "<code>1111111111:AAAAAAAAAAAAAA_GchLGbMkBdSBRIEspy11</code>\n\n"
            "7. Нажмите на данный текст, он скопируется и зайдите на этот бот и пишите вот так \n"
            "Вы должны сначала написать /bot, затем вставить выданный вам токен, и для вас будет создан специальный бот.\n\n"
            "Пример команды :\n\n"
            "<code>/bot 1111111111:AAAAAAAAAA_GchLGbMkBdSBRIEspy11</code>\n\n"
            "бот вышлет ссылку на ваш бот - покупайте через него\n"
        )
      await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()