# Telegram Vocabulary Bot — spaced repetition with SQLite
# Requirements:
#   python-telegram-bot==21.6
#   python-dotenv==1.0.1  (optional, if you use .env)
#
# Usage:
#   1) Create bot with @BotFather and copy the token.
#   2) Put TOKEN=your_token_here into a .env file (or set env var), or paste directly below.
#   3) pip install -r requirements.txt  (or pip install python-telegram-bot==21.6 python-dotenv==1.0.1)
#   4) python telegram_vocabulary_bot.py
#
# Commands for users (you):
#   /start — help and menu
#   /add <word> ; <translation> — add a pair (use semicolon or dash). Example: /add apple; яблоко
#   /list — show your 20 most recent words
#   /due — show how many cards are due now
#   /quiz — start a review session (due first, then random)
#   /export — export all words as CSV
#
# Notes:
#  - The bot stores data per Telegram user id, so it is safe for multi-user but designed for personal use.
#  - Spaced repetition uses a simplified SM-2 algorithm.
#  - For daily automatic reminders, run the script on a server and use any scheduler (cron/systemd) to send you /quiz.

import asyncio
import csv
import datetime as dt
import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Fix common Windows asyncio issues ---
import sys
import asyncio
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

TOKEN = "7791275922:AAFNCrXQfScPDTVNjt2P1zazgBZxLLLWBbA"  # <-- paste token here if not using .env
DB_PATH = Path("vocab.db")

# ------------------------- Database -------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    translation TEXT NOT NULL,
    ease REAL NOT NULL DEFAULT 2.5,
    interval INTEGER NOT NULL DEFAULT 1,    -- in days
    reps INTEGER NOT NULL DEFAULT 0,        -- successful reviews in a row
    next_review TEXT NOT NULL               -- ISO datetime
);
CREATE INDEX IF NOT EXISTS idx_cards_user_next ON cards(user_id, next_review);
"""


def now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)


def to_iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).isoformat()


def from_iso(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript(SCHEMA)
        con.commit()


# --------------------- Spaced Repetition ---------------------
# Simplified SM-2 update. quality: 1 (forgot) or 5 (knew it)

def sm2_update(ease: float, interval: int, reps: int, quality: int) -> Tuple[float, int, int]:
    # Update ease factor
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if ease < 1.3:
        ease = 1.3

    if quality < 3:
        reps = 0
        interval = 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = int(round(interval * ease))

    return ease, interval, reps


# ---------------------- Helper queries ----------------------

def add_card(user_id: int, term: str, translation: str):
    term = term.strip()
    translation = translation.strip()
    with db() as con:
        cur = con.execute(
            "INSERT INTO cards(user_id, term, translation, next_review) VALUES(?,?,?,?)",
            (user_id, term, translation, to_iso(now_utc())),
        )
        con.commit()
        return cur.lastrowid


def list_recent(user_id: int, limit: int = 20) -> List[sqlite3.Row]:
    with db() as con:
        cur = con.execute(
            "SELECT * FROM cards WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return cur.fetchall()


def get_due(user_id: int, limit: int = 50) -> List[sqlite3.Row]:
    now = to_iso(now_utc())
    with db() as con:
        cur = con.execute(
            "SELECT * FROM cards WHERE user_id = ? AND next_review <= ? ORDER BY next_review ASC LIMIT ?",
            (user_id, now, limit),
        )
        return cur.fetchall()


def get_random(user_id: int, limit: int = 20) -> List[sqlite3.Row]:
    with db() as con:
        cur = con.execute(
            "SELECT * FROM cards WHERE user_id = ? ORDER BY RANDOM() LIMIT ?",
            (user_id, limit),
        )
        return cur.fetchall()


def update_card_review(card_id: int, quality: int):
    with db() as con:
        row = con.execute("SELECT ease, interval, reps FROM cards WHERE id = ?", (card_id,)).fetchone()
        if not row:
            return
        ease, interval, reps = row["ease"], row["interval"], row["reps"]
        ease, interval, reps = sm2_update(ease, interval, reps, quality)
        next_date = now_utc() + dt.timedelta(days=interval)
        con.execute(
            "UPDATE cards SET ease=?, interval=?, reps=?, next_review=? WHERE id=?",
            (ease, interval, reps, to_iso(next_date), card_id),
        )
        con.commit()


# -------------------------- Bot -----------------------------
WELCOME = (
    "Привет! Я помогу тебе учить английские слова по системе интервальных повторений.\n\n"
    "Команды:\n"
    "• /add <слово> ; <перевод> — добавить пару (пример: /add apple; яблоко)\n"
    "• /list — последние 20 слов\n"
    "• /due — сколько карточек к повторению сейчас\n"
    "• /quiz — начать тренировку\n"
    "• /export — выгрузить все слова в CSV"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)


def parse_add(text: str) -> Optional[Tuple[str, str]]:
    text = text.strip()
    # Try patterns: "word ; translation" or "word - translation"
    if ";" in text:
        parts = text.split(";", maxsplit=1)
    elif " - " in text:
        parts = text.split(" - ", maxsplit=1)
    elif " — " in text:
        parts = text.split(" — ", maxsplit=1)
    else:
        return None
    term, trans = parts[0].strip(), parts[1].strip()
    if not term or not trans:
        return None
    return term, trans


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args_text = update.message.text[len("/add"):].strip()
    parsed = parse_add(args_text)
    if not parsed:
        await update.message.reply_text("Формат: /add слово ; перевод  (пример: /add apple; яблоко)")
        return
    term, translation = parsed
    card_id = add_card(user_id, term, translation)
    await update.message.reply_text(f"Добавил: <b>{term}</b> — {translation} (id {card_id})", parse_mode=ParseMode.HTML)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = list_recent(user_id)
    if not rows:
        await update.message.reply_text("Список пуст. Добавь слова через /add.")
        return
    lines = [f"{r['id']}. <b>{r['term']}</b> — {r['translation']} (повт: {from_iso(r['next_review']).date()})" for r in rows]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def due_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = len(get_due(user_id))
    await update.message.reply_text(f"К повторению карточек: {count}")


# ---- Quiz flow ----
ACTIVE_QUIZ: dict[int, List[sqlite3.Row]] = {}


def build_quiz_queue(user_id: int) -> List[sqlite3.Row]:
    due = get_due(user_id, limit=100)
    if len(due) < 10:
        due += [r for r in get_random(user_id, limit=10) if r not in due]
    return due


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    queue = build_quiz_queue(user_id)
    if not queue:
        await update.message.reply_text("Нет карточек. Добавь слова через /add.")
        return
    ACTIVE_QUIZ[user_id] = queue
    await send_next_card(update, context, user_id)


async def send_next_card(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    queue = ACTIVE_QUIZ.get(user_id, [])
    if not queue:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Готово! Сессия завершена. /quiz — новая сессия")
        return
    card = queue[0]
    # Ask with the term first, hide translation under a button
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Показать перевод", callback_data=f"show:{card['id']}")]
    ])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Что значит: <b>{card['term']}</b>?", parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("show:"):
        card_id = int(data.split(":", 1)[1])
        with db() as con:
            row = con.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            await query.edit_message_text("Карточка не найдена")
            return
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Знал", callback_data=f"grade:5:{card_id}"),
                InlineKeyboardButton("Забыл", callback_data=f"grade:1:{card_id}"),
            ]
        ])
        await query.edit_message_text(
            f"<b>{row['term']}</b> — {row['translation']}\nОтметь ответ:",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    if data.startswith("grade:"):
        _, q, cid = data.split(":", 2)
        quality = int(q)
        card_id = int(cid)
        update_card_review(card_id, quality)
        # pop current card from queue
        queue = ACTIVE_QUIZ.get(user_id, [])
        if queue and queue[0]["id"] == card_id:
            queue.pop(0)
        ACTIVE_QUIZ[user_id] = queue
        await query.edit_message_text("Сохранено. Следующая карточка →")
        # send next
        class Dummy:
            effective_chat = query.message.chat
        await send_next_card(Dummy(), context, user_id)
        return


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with db() as con:
        rows = con.execute(
            "SELECT term, translation, ease, interval, reps, next_review FROM cards WHERE user_id=? ORDER BY id",
            (user_id,),
        ).fetchall()
    if not rows:
        await update.message.reply_text("Нет данных для экспорта.")
        return
    export_path = Path(f"export_{user_id}.csv")
    with export_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["term", "translation", "ease", "interval", "reps", "next_review_iso"])
        for r in rows:
            w.writerow([r["term"], r["translation"], r["ease"], r["interval"], r["reps"], r["next_review"]])
    await update.message.reply_document(document=export_path.open("rb"), filename=export_path.name)


async def fallback_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Allow sending just "word; перевод" without /add
    if not update.message or not update.message.text:
        return
    maybe = parse_add(update.message.text)
    if maybe:
        user_id = update.effective_user.id
        term, translation = maybe
        add_card(user_id, term, translation)
        await update.message.reply_text(f"Ок, добавил: <b>{term}</b> — {translation}", parse_mode=ParseMode.HTML)


def main():
    init_db()
    if not TOKEN or TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise RuntimeError("Set TOKEN env var or paste it into the script.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("due", due_cmd))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_add))

    print("Bot is running... Press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
