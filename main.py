# main.py
import os
import logging
import threading
from flask import Flask, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# --- Handlers (пример: /start и ещё команды) ---
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("👋 Привет! Бот запущен и работает!")

@dp.message_handler(commands=["ping"])
async def cmd_ping(message: types.Message):
    await message.reply("pong")

@dp.message_handler()
async def echo_all(message: types.Message):
    # Для теста — отвечаем на текст
    text = message.text or ""
    # не отвечаем на команды (они обрабатываются выше)
    if text.startswith("/"):
        return
    await message.reply(f"Ты написал: {text}")

# --- функция, которая запускает polling (в потоке) ---
def start_polling():
    # skip_updates=True чтобы бот не обрабатывал старые апдейты после рестарта
    executor.start_polling(dp, skip_updates=True)

# --- Flask health server ---
app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"status": "ok", "bot": "running"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    # 1) запустить polling в отдельном потоке
    t = threading.Thread(target=start_polling, daemon=True)
    t.start()

    # 2) запустить Flask — Render требует биндинг на PORT
    port = int(os.environ.get("PORT", 8000))
    # host 0.0.0.0 чтобы Render мог сканить порт
    app.run(host="0.0.0.0", port=port)
