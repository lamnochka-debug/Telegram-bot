# main.py
import os
import logging
import threading
import asyncio
from flask import Flask

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Token from env
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in environment")
    raise SystemExit("BOT_TOKEN not set")

# aiogram setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# --- Handlers (add your commands here) ---
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("👋 Привет! Бот запущен и работает!")

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.reply("Список команд: /start /help /echo")

@dp.message_handler(commands=["echo"])
async def cmd_echo(message: types.Message):
    # example: /echo hello -> replies "hello"
    text = message.get_args()
    if not text:
        await message.reply("Usage: /echo <text>")
    else:
        await message.reply(text)

# Debug / catch-all echo handler to ensure messages reach bot
@dp.message_handler()
async def fallback(message: types.Message):
    logger.info("Fallback handler got: %s", message.text)
    # comment out next line if you don't want auto-echo
    await message.reply(f"Эхо (debug): {message.text}")

# --- Polling starter (runs in thread with its own event loop) ---
def start_polling():
    # create & set event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # executor.start_polling is blocking — run it in this thread's loop
    # skip_updates=True to ignore backlog; change if needed
    executor.start_polling(dp, skip_updates=True)

def run_polling_in_thread():
    th = threading.Thread(target=start_polling, name="aiogram-poller", daemon=True)
    th.start()
    logger.info("Started polling thread: %s", th.name)

# --- Flask health server (so Render sees an open port) ---
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    # start polling thread BEFORE Flask, or either order is OK (polling in thread)
    run_polling_in_thread()

    # Run Flask on port from env (Render exposes $PORT)
    port = int(os.environ.get("PORT", 10000))
    # host=0.0.0.0 required for Render
    logger.info("Starting Flask on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port)
