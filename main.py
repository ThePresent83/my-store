import logging
import asyncio
import os
import aiohttp
import aiofiles
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, FSInputFile, InputMediaPhoto
from aiohttp import ClientSession
from config import categories

# Конфигурация токенов
TELEGRAM_TOKEN = "7537757612:AAEoWw6r90wtEEGF-oHExCK5HP-4VbldZIs"
MOYSKLAD_API_TOKEN = "0a553d37e279a0c9c6dda0b1b19ff3837d4a6247"
ADMIN_ID = 5190704339
BASE_URL = "https://api.moysklad.ru/api/remap/1.2"
TEMP_FOLDER = "C:\\Users\\BugBuster\\Documents\\my-store\\IMG_SOURCE\\"

# Настройка Telegram-бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Проверка существования папки для временных файлов
os.makedirs(TEMP_FOLDER, exist_ok=True)

HEADERS = {
    "Authorization": f"Bearer {MOYSKLAD_API_TOKEN}",
    "Content-Type": "application/json"
}

# Настройка клавиатуры
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Подписаться на рассылку"), KeyboardButton(text="📦 Остатки на складе")],
        [KeyboardButton(text="🔍 Найти товар по коду")]
    ],
    resize_keyboard=True
)

MAX_MESSAGE_LENGTH = 4096

async def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID

async def send_message_in_parts(message, text):
    """Отправка длинного сообщения частями."""
    if len(text) > MAX_MESSAGE_LENGTH:
        parts = [text[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)

async def get_product_info_and_stock(category_pathname):
    product_url = f'{BASE_URL}/entity/product?filter=pathName={category_pathname}'
    stock_url = f'{BASE_URL}/report/stock/bystore/current'

    async with ClientSession() as session:
        try:
            async with session.get(product_url, headers=HEADERS) as response:
                response_data = await response.json()
                if response.status != 200:
                    return f"Ошибка при получении товаров: {response_data}"

                products = response_data.get('rows', [])
                if not products:
                    return "Нет товаров в выбранной категории."

                product_info = ""
                for product in products:
                    product_name = product.get('name', 'Без названия')
                    stock_params = {'filter': f"assortmentId={product.get('id')}", 'withRecalculate': 'true'}
                    async with session.get(stock_url, headers=HEADERS, params=stock_params) as stock_response:
                        stock_data = await stock_response.json()
                        stock_quantity = stock_data[0].get('stock', 0) if stock_data else 0
                    if stock_quantity <= 0:
                        continue
                    sale_prices = product.get('salePrices', [])
                    valid_price = next((price.get('value', 0) / 100 for price in sale_prices if price.get('value')), None)
                    product_info += f"Товар: {product_name}\nЦена: {valid_price} тг\nОстатки: {stock_quantity} шт\n\n"

                return product_info if product_info else "Нет товаров с положительным остатком."
        except Exception as e:
            logging.error(f"Ошибка при запросе: {e}")
            return "Ошибка при получении данных."

async def find_product_by_code(code_part):
    url = f"{BASE_URL}/entity/product?filter=code~{code_part}&limit=1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    rows = data.get("rows", [])
                    if rows:
                        return rows[0]
    except Exception as e:
        logging.exception(f"Ошибка поиска товара: {e}")
    return None

async def get_product_images(product):
    url_product = f"{product['meta']['href']}?expand=images&limit=100"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_product, headers=HEADERS) as response:
                if response.status == 200:
                    product_data = await response.json()
                    return [img["meta"]["downloadHref"] for img in product_data.get("images", {}).get("rows", [])]
    except Exception as e:
        logging.exception(f"Ошибка при получении изображений: {e}")
    return []

async def download_image(url, filename):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as response:
                if response.status == 200:
                    filepath = os.path.join(TEMP_FOLDER, filename)
                    async with aiofiles.open(filepath, "wb") as file:
                        await file.write(await response.read())
                    return filepath
    except Exception as e:
        logging.exception(f"Ошибка загрузки изображения: {e}")
    return None

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if await is_admin(message):
        await message.answer("Привет! Выберите действие:", reply_markup=menu_keyboard)
    else:
        await message.answer("У вас нет прав для использования бота.")

@dp.message(lambda message: message.text == "📦 Остатки на складе")
async def send_categories(message: types.Message):
    if not await is_admin(message):
        return
    category_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=category)] for category in categories.keys()],
        resize_keyboard=True
    )
    await message.answer("Выберите категорию:", reply_markup=category_keyboard)

@dp.message(lambda message: message.text in categories.keys())
async def send_stock_by_category(message: types.Message):
    if not await is_admin(message):
        return
    category_pathname = message.text.strip()
    product_info = await get_product_info_and_stock(category_pathname)
    await send_message_in_parts(message, product_info)

@dp.message(lambda message: message.text == "🔍 Найти товар по коду")
async def find_product(message: types.Message):
    await message.answer("Введите часть кода товара:")

@dp.message()
async def handle_product_search(message: types.Message):
    code_part = message.text.strip()
    product = await find_product_by_code(code_part)
    if not product:
        await message.answer("Товар с таким кодом не найден.")
        return

    product_name = product.get("name", "Без названия")
    product_pathname = product.get("pathName", "Путь не указан")
    product_info_text = f"🛒 <b>{product_name}</b>\n📂 Категория: {product_pathname}"

    images = await get_product_images(product)
    if images:
        tasks = [download_image(url, f"product_{code_part}_{idx}.jpg") for idx, url in enumerate(images)]
        downloaded_files = await asyncio.gather(*tasks)
        media_group = [InputMediaPhoto(media=FSInputFile(filepath)) for filepath in downloaded_files if filepath]
        if media_group:
            await message.answer(product_info_text, parse_mode="HTML")
            await bot.send_media_group(message.chat.id, media=media_group)
        for filepath in downloaded_files:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
    else:
        await message.answer(f"Изображений для товара '{product_name}' не найдено.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
