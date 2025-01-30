import requests
import logging
from decimal import Decimal, ROUND_HALF_DOWN
import uuid

# Initialize logging for this module
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log',
    filemode='a'
)


class CryptoRates:
    @staticmethod
    async def fetch_crypto_in_usd(api_key=None):
        """
        Fetches cryptocurrency rates in USD for Bitcoin and Litecoin.

        Args:
            api_key: (Optional) API key for CoinGecko, not used in the current implementation.

        Returns:
            A dictionary with cryptocurrency rates in USD or None in case of error.
        """
        try:
            response = requests.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin,litecoin&vs_currencies=usd",
                headers={'accept': 'application/json'}, timeout=10
            )
            response.raise_for_status()
            data = response.json()
            logging.info(f"Ответ от API CoinGecko: {data}")

            crypto_rates = {
                "btc": Decimal(str(data["bitcoin"]["usd"])),
                "eth": Decimal(str(data["ethereum"]["usd"])),  # Изменено на "ethereum" и ключ "eth"
                "ltc": Decimal(str(data["litecoin"]["usd"])),
            }
            return crypto_rates

        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при запросе к API CoinGecko: {e}")
            return None
        except (KeyError, TypeError) as e:
            logging.error(f"Ошибка при обработке данных от API CoinGecko: {e}")
            return None
        except Exception as e:
            logging.exception(f"Непредвиденная ошибка в fetch_crypto_in_usd: {e}")
            return None

    @staticmethod
    async def convert_usd_to_crypto(usd_amount: Decimal, crypto_currency: str) -> dict:
        """Converts USD amount to crypto currency (Bitcoin or Litecoin).
           Adds 8% and limits decimal places to 6.
           Also adds unique payment id

        Args:
            usd_amount: The amount in USD to convert.
            crypto_currency: The target cryptocurrency ('btc' or 'ltc').

        Returns:
            A dict containing the converted crypto amount and the current exchange rate,
            and unique payment id, or empty dict in case of an error.
        """
        try:
            rates = await CryptoRates.fetch_crypto_in_usd()
            logging.info(f"Актуальные курсы валют: {rates}")
            if not rates or crypto_currency.lower() not in rates:  # приводим crypto_currency к нижнему регистру
                logging.error(f"Курс для {crypto_currency} не найден.")
                return {}

            rate = rates[crypto_currency.lower()] # приводим crypto_currency к нижнему регистру
            if rate == Decimal('0'):
                logging.error(f"Курс для {crypto_currency} равен нулю.")
                return {}

            # добавляем 8% к сумме
            usd_amount_with_fee = usd_amount * Decimal("1.08") # Изменил способ добавления комиссии

            crypto_amount = usd_amount_with_fee / rate
            
            # Округляем до 8 знаков после запятой,  используя quantize и ROUND_HALF_DOWN.
            crypto_amount = crypto_amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_DOWN)
           

            payment_id = f"crypto_payment_{uuid.uuid4()}"
            
            logging.info(f"Конвертация: {usd_amount} USD -> {crypto_amount} {crypto_currency} (курс: {rate}), payment_id: {payment_id}")
            logging.info(f"Крипто конвертер: сгенерировал ID = {payment_id}, итоговая сумма {crypto_amount}")
            
            return {
                "crypto_amount": crypto_amount,
                "rate": rate,
                "payment_id": payment_id
            }

        except Exception as e:
            logging.error(f"Error converting USD to crypto: {e}")
            return {}