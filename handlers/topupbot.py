import logging
import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp
from database import get_user_balance, add_to_user_balance, get_wallet_address
from handlers.shared_context import user_context
import random

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)

CHECK_INTERVAL = 60  # Интервал проверки в секундах - ИЗМЕНЕНО на 60 секунд
PAYMENT_CHECK_TIMEOUT = 30 * 60 # Время ожидания платежа 30 минут в секундах - добавлено

async def get_transactions(tron_wallet_address, limit=20, only_confirmed=True, start_timestamp=None):
    """Получает транзакции для указанного адреса через Trongrid API."""
    tron_grid_url = f"https://api.trongrid.io/v1/accounts/{tron_wallet_address}/transactions/trc20"
    params = {
        'only_confirmed': str(only_confirmed).lower(),
        'limit': limit,
        'only_to': str(True).lower()
    }
    if start_timestamp:
        params['min_timestamp'] = int(start_timestamp.timestamp() * 1000)

    headers = {"accept": "application/json"}

    transactions = []
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(tron_grid_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            response_json = await response.json()
            transactions = response_json.get('data', [])

            while 'fingerprint' in response_json.get('meta', {}):
                params['fingerprint'] = response_json['meta']['fingerprint']
                response = await session.get(tron_grid_url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                response_json = await response.json()
                transactions.extend(response_json.get('data', []))
                if len(transactions) >= limit:
                    break

    except aiohttp.ClientError as e:
        logging.error(f"topupbot - get_transactions: ERROR: Ошибка при запросе к Trongrid API: {e}", exc_info=True)  # Error when requesting to Trongrid API: {e} # ИЗМЕНЕНО название функции в логах
    except Exception as e:
         logging.error(f"topupbot - get_transactions: ERROR: Произошла непредвиденная ошибка: {e}", exc_info=True)  # An unexpected error occurred: {e} # ИЗМЕНЕНО название функции в логах
    return transactions

async def check_topup_payment(message: types.Message, bot: Bot, topup_data, last_hour: datetime):
    """Проверяет поступление оплаты."""
    log_id = uuid.uuid4()
    topup_id = topup_data.get("topup_id")
    amount_without_cents = Decimal(str(topup_data.get("amount_without_cents")))  # передаем в Decimal
    user_id = topup_data.get("user_id")

    logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Начало проверки платежа {topup_id} для пользователя {user_id}, с суммой {amount_without_cents}") # Start payment verification {topup_id} for user {user_id}, with amount {amount_without_cents}
    start_time = time.time()
    tron_wallet_address = get_wallet_address('USDT_TRC20') # Получаем адрес кошелька вне цикла для оптимизации
    if not tron_wallet_address:
        logging.error(f"{log_id} - topupbot - check_topup_payment: ERROR: USDT_TRC20 wallet address not found in database")  # USDT_TRC20 wallet address not found in database
        await bot.send_message(user_id, "❌ Ошибка при пополнении баланса, попробуйте позже. \n\n ❌ Error when topping up balance, please try again later.")
        return False

    while time.time() - start_time < PAYMENT_CHECK_TIMEOUT:  # Проверяем 30 минут - ИЗМЕНЕНО на PAYMENT_CHECK_TIMEOUT
        try:
            transactions = await get_transactions(tron_wallet_address, start_timestamp=last_hour)  # ИЗМЕНЕНО название функции get_topup_transactions -> get_transactions # передаем адрес кошелька
            logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Получено транзакций: {len(transactions)}")  # Received transactions: {len(transactions)}
            if not transactions:
                logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Нет транзакций для проверки")  # No transactions to check
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            for tr in transactions:
                token_symbol = tr.get('token_info', {}).get('symbol')
                logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Проверяем транзакцию: symbol={token_symbol}") # Checking transaction: symbol={token_symbol}
                if token_symbol == "USDT":
                    value = tr.get('value')
                    decimals = tr.get('token_info', {}).get('decimals')
                    if value is None or decimals is None:
                        logging.warning(
                            f"{log_id} - topupbot - check_topup_payment: WARNING: Пропущена транзакция {tr}. Не хватает данных: value или decimals")  # Skipped transaction {tr}. Missing data: value or decimals
                        continue
                    try:
                        value = Decimal(value)
                        decimals = int(decimals)
                        amount_received = value / (10 ** decimals)
                    except (ValueError, TypeError) as e:
                        logging.error(
                            f"{log_id} - topupbot - check_topup_payment: ERROR: Ошибка при конвертации value или decimals: {e}, transaction: {tr}", exc_info=True)  # Error when converting value or decimals: {e}, transaction: {tr}
                        continue

                    to_address = tr.get('to')
                    from_address = tr.get('from')

                    logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Проверка платежа {topup_id}: Сумма к оплате = {amount_without_cents}, Получено = {amount_received}, Адрес получателя = {to_address}, Ожидаемый адрес = {tron_wallet_address}") # Payment verification {topup_id}: Amount to pay = {amount_without_cents}, Received = {amount_received}, Recipient address = {to_address}, Expected address = {tron_wallet_address}

                    if amount_received == amount_without_cents:
                        if to_address == tron_wallet_address:
                            logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Платеж на сумму {amount_received} USDT от {from_address} на адрес {to_address} подтвержден.")  # Payment of {amount_received} USDT from {from_address} to address {to_address} confirmed.
                            # Пополняем баланс пользователя в БД и контексте
                            add_to_user_balance(user_id, float(amount_without_cents))
                            if user_id in user_context:
                                user_context[user_id]["balance"] = get_user_balance(user_id)  # Обновляем баланс в контексте
                            await bot.send_message(user_id, f"💰 Ваш баланс пополнен на {amount_without_cents:.2f} USDT. \n\n 💰 Your balance has been topped up by {amount_without_cents:.2f} USDT.")
                            return True  # Прерываем цикл
                        else:
                            logging.info(
                                f"{log_id} - topupbot - check_topup_payment: INFO: Адрес получателя транзакции {to_address} не совпадает с ожидаемым адресом {tron_wallet_address}.")  # Transaction recipient address {to_address} does not match the expected address {tron_wallet_address}.
                    else:
                        logging.info(
                            f"{log_id} - topupbot - check_topup_payment: INFO: Сумма транзакции {amount_received} не соответствует ожидаемой сумме {amount_without_cents} для платежа {topup_id}.")  # Transaction amount {amount_received} does not match the expected amount {amount_without_cents} for payment {topup_id}.
                else:
                    logging.info(
                        f"{log_id} - topupbot - check_topup_payment: INFO: Символ токена транзакции {token_symbol} не равен USDT, пропускаем")  # Transaction token symbol {token_symbol} is not equal to USDT, skipping
        except Exception as e:
            logging.error(f"{log_id} - topupbot - check_topup_payment: ERROR: Неизвестная ошибка в цикле проверки платежа: {e}", exc_info=True)  # Unknown error in payment verification loop: {e}
        await asyncio.sleep(CHECK_INTERVAL)
    # Если прошло 30 минут и оплата не найдена - ИЗМЕНЕНО на 30 минут
    logging.info(f"{log_id} - topupbot - check_topup_payment: INFO: Платеж {topup_id} не был получен в течение 30 минут.")  # Payment {topup_id} was not received within 30 minutes.
    await bot.send_message(user_id,
                           "❌ Платеж от вас не поступил, пополнение баланса бота не было выполнено. \n\n ❌ Your payment has not been received, topping up the bot balance was not completed.")
    if user_id in user_context and "pending_topup" in user_context[user_id]:
        del user_context[user_id]["pending_topup"]  # Удаляем из контекста при отмене платежа
    return False

async def start_topup_check(message, bot, topup_data):
    """Запускает проверку пополнения."""
    log_id = uuid.uuid4()
    topup_id = topup_data.get("topup_id")
    amount_without_cents = topup_data.get("amount_without_cents")
    user_id = topup_data.get("user_id")
    logging.info(
        f"{log_id} - topupbot - start_topup_check: INFO: Пользователь {user_id}, Topup ID: {topup_id}, сумма без центов {amount_without_cents}") # User {user_id}, Topup ID: {topup_id}, amount without cents {amount_without_cents}

    now = datetime.now()
    last_hour = now - timedelta(hours=1)
    asyncio.create_task(check_topup_payment(message, bot, topup_data, last_hour))

async def topup_payment_made_handler(callback: types.CallbackQuery, bot:Bot):
    user_id = callback.from_user.id
    log_id = uuid.uuid4()
    logging.info(f"{log_id} - topupbot - topup_payment_made_handler: INFO: Пользователь {user_id} нажал 'Оплатил'")

    if user_id not in user_context or "pending_topup" not in user_context[user_id]:
        logging.warning(
            f"{log_id} - topupbot - topup_payment_made_handler: WARNING: Информация о пополнении для пользователя {user_id} не найдена.")
        await callback.answer("Ошибка: Информация о пополнении не найдена, попробуйте еще раз \n\n Error: Top up information not found, please try again.", show_alert=True)
        return

    topup_info = user_context[user_id]["pending_topup"]
    total_amount_str = topup_info.get("amount_with_cents") # Get the amount_with_cents that was already generated
    if not total_amount_str:
        logging.error(f"{log_id} - topupbot - topup_payment_made_handler: ERROR: amount_with_cents not found in user_context")
        await callback.answer("Ошибка: Сумма пополнения не найдена, попробуйте еще раз \n\n Error: Top up amount not found, please try again.", show_alert=True)
        return

    try:
        total_amount = Decimal(str(total_amount_str)) # Convert to Decimal
    except Exception as e:
        logging.error(f"{log_id} - topupbot - topup_payment_made_handler: ERROR: Could not convert amount_with_cents to Decimal: {e}", exc_info=True)
        await callback.answer("Ошибка: Неверный формат суммы пополнения, попробуйте еще раз \n\n Error: Invalid top up amount format, please try again.", show_alert=True)
        return


    amount_without_cents = total_amount # Use the amount_with_cents as amount_without_cents for check - it's actually the total amount now.
    logging.info(
        f"{log_id} - topupbot - topup_payment_made_handler: INFO: Пользователь {user_id}, сумма к оплате: {total_amount}")


    await callback.answer("Ожидайте подтверждения платежа \n\n Please wait for payment confirmation")

    await callback.message.edit_text(
        "⏳ Мы проверяем ваш платеж, как только деньги поступят - ваш баланс будет пополнен!\n\nЕсли в течении 30-ти минут мы не получим от вас оплату, платеж будет отменен.\n\n" # ИЗМЕНЕНО на 30 минут
        "English:\n"
        "⏳ We are verifying your payment, as soon as the money arrives, your balance will be replenished!\n\n"
        "If we do not receive payment from you within 30 minutes, the payment will be canceled.", # ИЗМЕНЕНО на 30 минут
        parse_mode="HTML"
    )

    await start_topup_check(callback.message, bot, {
        "topup_id": log_id,
        "amount_without_cents": total_amount,  # передаем Decimal - now total_amount
        "user_id": user_id
    })

def register_topup_handler(dp: Dispatcher, bot: Bot): # Добавил bot
   dp.callback_query.register(
        topup_payment_made_handler,
        lambda callback: callback.data == "payment_made"
    )