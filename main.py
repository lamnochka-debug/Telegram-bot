import os
import logging
from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage # Не обязательно, если не используете FSM
import sqlite3  # Пример для хранения данных
import csv
from io import StringIO
import asyncio
from aiogram import Bot as aiogram_Bot # Импортируем Bot под другим именем, чтобы избежать конфликта с нашим экземпляром

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get token from environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in environment")
    raise SystemExit("BOT_TOKEN not set")

# aiogram setup
bot = Bot(token=BOT_TOKEN)
# Используем MemoryStorage для FSM, если планируете использовать состояния
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Database setup (example with SQLite) ---
DATABASE = 'words.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS words
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  word TEXT NOT NULL,
                  translation TEXT NOT NULL,
                  added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  due_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def add_word_to_db(user_id, word, translation):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # Устанавливаем due_date на текущее время (или через определенный интервал для повторения)
    # Здесь упрощённый пример - сразу доступно для повторения
    c.execute("INSERT INTO words (user_id, word, translation, due_date) VALUES (?, ?, ?, datetime('now'))",
              (user_id, word, translation))
    conn.commit()
    conn.close()

def get_last_words(user_id, limit=20):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT word, translation, added_date FROM words WHERE user_id = ? ORDER BY added_date DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_due_count(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM words WHERE user_id = ? AND due_date <= datetime('now')", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_words_for_export(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT word, translation, added_date FROM words WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_word_from_db(user_id, word_to_delete):
    """Функция для удаления слова из базы данных для конкретного пользователя."""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # Удаляем только одну конкретную запись, соответствующую user_id и слову
    c.execute("DELETE FROM words WHERE user_id = ? AND word = ?", (user_id, word_to_delete))
    changes = c.rowcount # Количество изменённых строк
    conn.commit()
    conn.close()
    return changes > 0 # Возвращаем True, если что-то удалили

def edit_word_in_db(user_id, old_word, new_word, new_translation):
    """Функция для редактирования слова и перевода в базе данных для конкретного пользователя."""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    # Обновляем слово и перевод, если найдено старое слово для пользователя
    c.execute("UPDATE words SET word = ?, translation = ? WHERE user_id = ? AND word = ?",
              (new_word, new_translation, user_id, old_word))
    changes = c.rowcount
    conn.commit()
    conn.close()
    return changes > 0

# Initialize database
init_db()

# --- Handlers ---
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply("👋 Привет! Бот запущен и работает! Используйте /help для списка команд.")

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    help_text = """
Список команд:
/add <слово> ; <перевод> — добавить пару (пример: /add apple; яблоко)
/list — последние 20 слов
/due — сколько карточек к повторению сейчас
/quiz — начать тренировку
/export — выгрузить все слова в CSV
/delete <слово> — удалить слово (пример: /delete apple)
/edit <старое_слово> ; <новое_слово> ; <новый_перевод> — изменить слово и перевод (пример: /edit aple; apple; яблоко)
    """
    await message.reply(help_text)

@dp.message_handler(commands=["list"])
async def cmd_list(message: types.Message):
    user_id = message.from_user.id
    words = get_last_words(user_id)
    if words:
        response_lines = ["Ваши последние слова:"]
        for word, translation, date in words:
            response_lines.append(f"{word} - {translation} (добавлено: {date})")
        response = "\n".join(response_lines)
    else:
        response = "У вас пока нет сохраненных слов."
    await message.reply(response)

@dp.message_handler(commands=["add"])
async def cmd_add(message: types.Message):
    args = message.get_args()
    if not args or ';' not in args:
        await message.reply("Неправильный формат. Используйте: /add <слово> ; <перевод>")
        return

    parts = args.split(';', 1)  # Разделить только по первому ';'
    word = parts[0].strip()
    translation = parts[1].strip()

    if not word or not translation:
        await message.reply("Слово и перевод не могут быть пустыми.")
        return

    user_id = message.from_user.id
    add_word_to_db(user_id, word, translation)
    await message.reply(f"Слово '{word}' с переводом '{translation}' добавлено!")

@dp.message_handler(commands=["due"])
async def cmd_due(message: types.Message):
    user_id = message.from_user.id
    count = get_due_count(user_id)
    await message.reply(f"Количество карточек к повторению: {count}")

@dp.message_handler(commands=["quiz"])
async def cmd_quiz(message: types.Message):
    # Заглушка для функции викторины
    await message.reply("Функция викторины пока не реализована.")

@dp.message_handler(commands=["export"])
async def cmd_export(message: types.Message):
    user_id = message.from_user.id
    words = get_all_words_for_export(user_id)

    if not words:
        await message.reply("Нет слов для экспорта.")
        return

    # Создаем CSV в памяти
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Слово", "Перевод", "Дата добавления"])  # Заголовки
    writer.writerows(words)

    # Получаем строку CSV
    csv_content = output.getvalue()
    output.close()

    # Отправляем CSV-файл
    from io import BytesIO
    csv_bytes = BytesIO(csv_content.encode('utf-8'))
    csv_bytes.name = 'export.csv'

    await message.reply_document(document=types.InputFile(csv_bytes, filename='export.csv'))
    csv_bytes.close()

@dp.message_handler(commands=["delete"])
async def cmd_delete(message: types.Message):
    args = message.get_args()
    if not args:
        await message.reply("Неправильный формат. Используйте: /delete <слово>")
        return

    word_to_delete = args.strip()

    user_id = message.from_user.id
    if delete_word_from_db(user_id, word_to_delete):
        await message.reply(f"Слово '{word_to_delete}' удалено.")
    else:
        await message.reply(f"Слово '{word_to_delete}' не найдено или не принадлежит вам.")

@dp.message_handler(commands=["edit"])
async def cmd_edit(message: types.Message):
    args = message.get_args()
    if not args or args.count(';') < 2:
        await message.reply("Неправильный формат. Используйте: /edit <старое_слово> ; <новое_слово> ; <новый_перевод>")
        return

    parts = args.split(';', 2)  # Разделить только по первым двум ';'
    old_word = parts[0].strip()
    new_word = parts[1].strip()
    new_translation = parts[2].strip()

    if not old_word or not new_word or not new_translation:
        await message.reply("Старое слово, новое слово и новый перевод не могут быть пустыми.")
        return

    user_id = message.from_user.id
    if edit_word_in_db(user_id, old_word, new_word, new_translation):
        await message.reply(f"Слово '{old_word}' обновлено до '{new_word}' с переводом '{new_translation}'.")
    else:
        await message.reply(f"Старое слово '{old_word}' не найдено или не принадлежит вам.")

@dp.message_handler(commands=["echo"])
async def cmd_echo(message: types.Message):
    # example: /echo hello -> replies "hello"
    text = message.get_args()
    if not text:
        await message.reply("Usage: /echo <text>")
    else:
        await message.reply(text)

# Debug / catch-all echo handler (remove or modify once all commands are implemented)
@dp.message_handler()
async def fallback(message: types.Message):
    # logger.info("Fallback handler got: %s", message.text) # Логирование можно отключить, если оно мешает
    # Убираем echo, чтобы не мешало командам
    # await message.reply(f"Эхо (debug): {message.text}")
    pass # Или добавьте логику для обработки неизвестных команд

# --- Flask app for webhooks ---
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200

# Webhook endpoint
@app.route(f"/bot{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        # Create an Update object from the request data
        update_data = request.get_json()
        update = types.Update(**update_data)

        # Set the current bot instance for aiogram context
        aiogram_Bot.set_current(bot)

        # Process the update
        # Use asyncio to run the async handler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(dp.process_update(update))
        loop.close()

        return {"status": "ok"}, 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return {"error": "Failed to process update"}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info("Starting Flask on 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port)