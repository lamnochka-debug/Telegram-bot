import logging
from aiogram import Bot, Dispatcher, types, executor
import os

# Читаем токен из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply("👋 Привет! Бот запущен и работает!")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
