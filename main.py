# main.py
import os
import threading
import logging
import asyncio

from flask import Flask

from aiogram import Bot, Dispatcher, types, executor

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

# aiogram setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# --- handlers (пример) ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.reply("👋 Привет! Бот запущен и работает!")

# тут добавь свои остальные хендлеры (команды/обработчики)
# например:
@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    await message.reply("Список команд: /start /help ...")

# ------------------------------------------------

def start_polling():
    """
    Функция запуска polling в отдельном потоке.
    Важно: создать event loop для этого потока, иначе aiogram упадёт.
    """
    # создаём и устанавливаем loop для текущего потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # start_polling блокирует текущий поток, поэтому вызываем прямо его
    executor.start_polling(dp, skip_updates=True)

# Flask health server (Render требует, чтобы был открыт порт)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

if __name__ == "__main__":
    # Запускаем polling в фоне (отдельный поток)
    t = threading.Thread(target=start_polling, name="aiogram-polling", daemon=True)
    t.start()

    # Запускаем Flask (главный поток) на порту, который отдаёт Render (env PORT)
    port = int(os.environ.get("PORT", 10000))
    # host 0.0.0.0 чтобы Render мог пробросить трафик
    app.run(host="0.0.0.0", port=port)
