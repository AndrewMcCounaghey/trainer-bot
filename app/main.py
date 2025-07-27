from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
import os
from dotenv import load_dotenv
import sqlite3

load_dotenv()

API_TOKEN = os.getenv("TRAINER_BOT_TOKEN")  # Токен управляющего бота

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- Инициализация БД ---
DB_PATH = "trainerbot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        bot_token TEXT
    )''')
    conn.commit()
    conn.close()

def set_user(telegram_id: int, username: str, bot_token: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO users (telegram_id, username, bot_token) VALUES (?, ?, ?)
                 ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, bot_token=excluded.bot_token''',
              (telegram_id, username, bot_token))
    conn.commit()
    conn.close()

def set_user_token(telegram_id: int, token: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET bot_token=? WHERE telegram_id=?', (token, telegram_id))
    conn.commit()
    conn.close()

def get_user(telegram_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, bot_token FROM users WHERE telegram_id=?', (telegram_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"username": row[0], "bot_token": row[1]}
    return None

# FSM
class BotSetup(StatesGroup):
    waiting_for_token = State()

# Кнопки
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚖️ Настроить бота")],
], resize_keyboard=True)

# Кнопка "Назад"
back_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⬅️ Назад")]
], resize_keyboard=True)

@dp.message(lambda message: message.text == "/start")
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    set_user(user_id, username)
    await message.answer("👋 Привет! Это панель управления твоим фитнес-ботом.", reply_markup=main_menu)

@dp.message(lambda message: message.text == "⚖️ Настроить бота")
async def ask_token(message: Message, state: FSMContext):
    instruction = (
        "🔐 Вставь сюда токен от нового бота, которого ты создал в @BotFather.\n\n"
        "<b>Как получить токен:</b>\n"
        "1. Открой Telegram и найди @BotFather.\n"
        "2. Нажми /start и выбери <b>New Bot</b> или команду /newbot.\n"
        "3. Придумай имя и username для бота.\n"
        "4. После создания @BotFather пришлёт тебе токен — скопируй его сюда.\n\n"
        "<i>Токен выглядит примерно так:</i> <code>123456789:AA...xyz</code>"
    )
    await message.answer(instruction, reply_markup=back_menu, parse_mode=ParseMode.HTML)
    await state.set_state(BotSetup.waiting_for_token)

@dp.message(lambda message: message.text == "⬅️ Назад")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔙 Возврат в главное меню", reply_markup=main_menu)

@dp.message(BotSetup.waiting_for_token)
async def save_token(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    token = message.text.strip()
    user_id = message.from_user.id
    if len(token) < 30 or ":" not in token:
        await message.answer("❌ Похоже, это не валидный токен. Попробуй снова.")
        return
    set_user_token(user_id, token)
    await message.answer("✅ Отлично! Твой клиентский бот подключён. Скоро появятся настройки.", reply_markup=main_menu)
    await state.clear()

if __name__ == "__main__":
    init_db()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
