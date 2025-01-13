import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiohttp import ClientSession

# Укажите токены
TELEGRAM_TOKEN = "7537757612:AAEoWw6r90wtEEGF-oHExCK5HP-4VbldZIs"
MOYSKLAD_API_TOKEN = "c09864436c8f3c3d056dd588dc5ffb12c2131db7"  # Замените на ваш токен API МойСклад
ADMIN_ID = 5190704339  # ID администратора

# Создание бота
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Меню кнопок
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Подписаться на рассылку")],
        [KeyboardButton(text="📦 Остатки на складе")]
    ],
    resize_keyboard=True
)


# Функция проверки прав администратора
async def is_admin(message: types.Message):
    return message.from_user.id == ADMIN_ID


MAX_MESSAGE_LENGTH = 4096


async def send_message_in_parts(message, stock_data):
    """Отправка длинного сообщения частями."""
    stock_data_str = str(stock_data)

    # Разбиение на части, если сообщение слишком длинное
    if len(stock_data_str) > MAX_MESSAGE_LENGTH:
        parts = [stock_data_str[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(stock_data_str), MAX_MESSAGE_LENGTH)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(stock_data_str)


# Функция получения категорий
async def get_categories(category_id=None):
    url = "https://api.moysklad.ru/api/remap/1.2/entity/productfolder"  # Эндпоинт категорий
    headers = {
        "Authorization": f"Bearer {MOYSKLAD_API_TOKEN}",
        "Content-Type": "application/json"
    }
    params = {
        "limit": 100,  # Ограничение на количество товаров
    }

    if category_id:
        params["filter"] = f"productFolder.id={category_id}"
        params["withSubFolders"] = "true"

    async with ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    categories = {item["name"]: item["id"] for item in data.get("rows", [])}
                    return categories
                else:
                    logging.error(f"Ошибка при получении категорий: {response.status}")
                    return {}
        except Exception as e:
            logging.error(f"Ошибка при запросе категорий: {e}")
            return {}


# Функция получения остатков по категории
async def get_stock_by_category(category_id):
    url = "https://api.moysklad.ru/api/remap/1.2/report/stock/all"  # Эндпоинт остатков
    headers = {
        "Authorization": f"Bearer {MOYSKLAD_API_TOKEN}",
        "Content-Type": "application/json"
    }

    async with ClientSession() as session:
        try:
            logging.info(f"Получаем остатки для категории с ID: {category_id}")
            async with session.get(url, headers=headers) as response:
                response_data = await response.json()
                logging.info(f"Ответ от API: Статус - {response.status}, Тело - {response_data}")

                if response.status == 200:
                    stock_info = f"📦 Остатки в категории {category_id}:\n"
                    no_category_info = "Товары без категории:\n"

                    # Фильтрация товаров по категории
                    for item in response_data.get("rows", {}):
                        item_name = item.get("name", "Без имени")
                        stock = item.get("stock", 0)  # Остаток товара
                        folder_id = item.get("productfolder", {}).get("id", None)  # Категория товара

                        logging.info(f"Товар: {item_name}, Остаток: {stock}, Категория: {folder_id}")

                        if folder_id == category_id and stock > 0:
                            stock_info += f"🔹 {item_name}: {stock} шт.\n"
                        elif folder_id is None and stock > 0:
                            no_category_info += f"🔹 {item_name}: {stock} шт.\n"

                    # Возвращаем результат
                    if stock_info != f"📦 Остатки в категории {category_id}:\n":
                        stock_info += "\n"
                    if no_category_info != "Товары без категории:\n":
                        no_category_info += "\n"

                    if stock_info != f"📦 Остатки в категории {category_id}:\n":
                        return stock_info
                    elif no_category_info != "Товары без категории:\n":
                        return no_category_info
                    else:
                        return "Нет товаров с остатком."
                else:
                    logging.error(f"Ошибка при получении остатков: {response.status}")
                    return f"Ошибка при получении данных, статус: {response.status}"

        except Exception as e:
            logging.error(f"Ошибка при запросе остатков: {e}")
            return "Ошибка при получении данных"


# Обработчик команды /start
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    if await is_admin(message):
        await message.answer("Привет! Выберите действие:", reply_markup=menu_keyboard)
    else:
        await message.answer("У вас нет прав для использования бота.")


# Обработчик кнопки "📦 Остатки на складе"
@dp.message(lambda message: message.text == "📦 Остатки на складе")
async def send_categories(message: types.Message):
    if not await is_admin(message):
        return
    categories = await get_categories()
    if categories:
        category_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=category)] for category in categories.keys()],
            resize_keyboard=True
        )
        await message.answer("Выберите категорию:", reply_markup=category_keyboard)
    else:
        await message.answer("Не удалось загрузить категории.")


# Обработчик выбора категории
@dp.message()
async def send_stock_by_category(message: types.Message):
    if not await is_admin(message):
        return
    categories = await get_categories()
    category_id = categories.get(message.text)
    if category_id:
        stock_data = await get_stock_by_category(category_id)
        await send_message_in_parts(message, stock_data)
    else:
        await message.answer("Ошибка при получении данных. Возможно, категория не найдена.")


# Обработчик подписки на рассылку
@dp.message(lambda message: message.text == "📢 Подписаться на рассылку")
async def subscribe_newsletter(message: types.Message):
    if not await is_admin(message):
        return
    await message.answer("Вы подписались на рассылку!")


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())