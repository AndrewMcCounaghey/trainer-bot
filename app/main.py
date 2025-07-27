from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
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
    c.execute('PRAGMA foreign_keys = ON')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        bot_token TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS muscle_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        UNIQUE(user_id, name)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS exercises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        muscle_group INTEGER,
        name TEXT,
        video TEXT,
        description TEXT,
        UNIQUE(user_id, name),
        FOREIGN KEY(muscle_group) REFERENCES muscle_groups(id) ON DELETE SET NULL
    )''')
    conn.commit()
    conn.close()

def set_user(telegram_id: int, username: str, bot_token: str = None):
    print(f"[DB] Добавление/обновление пользователя: telegram_id={telegram_id}, username={username}, bot_token={bot_token}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO users (telegram_id, username, bot_token) VALUES (?, ?, ?)
                 ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, bot_token=excluded.bot_token''',
              (telegram_id, username, bot_token))
    conn.commit()
    conn.close()

def set_user_token(telegram_id: int, token: str):
    print(f"[DB] Сохранение токена для пользователя {telegram_id}: {token}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET bot_token=? WHERE telegram_id=?', (token, telegram_id))
    if c.rowcount == 0:
        # Если пользователя нет, добавляем с пустым username
        c.execute('INSERT INTO users (telegram_id, username, bot_token) VALUES (?, ?, ?)', (telegram_id, '', token))
        print(f"[DB] Пользователь {telegram_id} не найден, добавлен с пустым username.")
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

class NavStates(StatesGroup):
    main = State()
    exercises = State()
    muscle_groups = State()

class MuscleFSM(StatesGroup):
    add = State()
    delete_select = State()
    delete_confirm = State()
    edit_select = State()
    edit_rename = State()

class ExerciseFSM(StatesGroup):
    add_select_muscle = State()
    add_name = State()
    add_video = State()
    add_desc = State()
    delete_select = State()
    edit_select = State()
    edit_field = State()
    edit_value = State()

# Кнопки
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⚖️ Настроить бота")],
], resize_keyboard=True)

# Кнопка "Назад"
back_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="⬅️ Назад")]
], resize_keyboard=True)

def get_main_menu(user_id):
    user = get_user(user_id)
    if user and user["bot_token"]:
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🤖 Мой клиентский бот")],
            [KeyboardButton(text="💪 Мои упражнения")],
            [KeyboardButton(text="👥 Мои клиенты")],
        ], resize_keyboard=True)
    else:
        return main_menu

@dp.message(lambda message: message.text == "/start")
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    set_user(user_id, username)
    menu = get_main_menu(user_id)
    await message.answer("👋 Привет! Это панель управления твоим фитнес-ботом.", reply_markup=menu)

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
    data = await state.get_data()
    prev = data.get("prev")
    if prev == NavStates.main.state or prev is None:
        await state.clear()
        menu = get_main_menu(message.from_user.id)
        await message.answer("🔙 Возврат в главное меню", reply_markup=menu)
    elif prev == NavStates.exercises.state:
        await my_exercises(message, state)
    elif prev == NavStates.muscle_groups.state:
        await muscle_groups(message, state)
    else:
        await state.clear()
        menu = get_main_menu(message.from_user.id)
        await message.answer("🔙 Возврат в главное меню", reply_markup=menu)

@dp.message(BotSetup.waiting_for_token)
async def save_token(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    token = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    if len(token) < 30 or ":" not in token:
        await message.answer("❌ Похоже, это не валидный токен. Попробуй снова.")
        return
    set_user(user_id, username, token)
    menu = get_main_menu(user_id)
    await message.answer("✅ Отлично! Твой клиентский бот подключён. Скоро появятся настройки.", reply_markup=menu)
    await state.clear()

from aiogram import Bot as AiogramBot

@dp.message(lambda message: message.text == "🤖 Мой клиентский бот")
async def my_client_bot(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user["bot_token"]:
        await message.answer("❌ Сначала добавьте токен клиентского бота через 'Настроить бота'.")
        return
    try:
        client_bot = AiogramBot(token=user["bot_token"])
        me = await client_bot.get_me()
        bot_username = me.username
        await client_bot.session.close()
        if bot_username:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Открыть бота", url=f"https://t.me/{bot_username}")]
            ])
            await message.answer("Ваш клиентский бот", reply_markup=kb)
        else:
            await message.answer("Не удалось получить username клиентского бота.")
    except Exception as e:
        await message.answer(f"Ошибка при получении данных клиентского бота: {e}")

@dp.message(lambda message: message.text == "💪 Мои упражнения")
async def my_exercises(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Группы мышц"), KeyboardButton(text="Упражнения")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)
    await state.set_state(NavStates.exercises)
    await state.update_data(prev=NavStates.main.state)
    await message.answer("Выберите раздел:", reply_markup=keyboard)

@dp.message(lambda message: message.text == "Группы мышц")
async def muscle_groups(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="➖ Удалить"), KeyboardButton(text="♻️ Редактировать")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)
    await state.set_state(NavStates.muscle_groups)
    await state.update_data(prev=NavStates.exercises.state)
    await message.answer(
        "В этом разделе вы можете добавлять, удалять и редактировать части тела, например: Руки, Ноги.",
        reply_markup=keyboard
    )

def get_muscle_groups(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, name FROM muscle_groups WHERE user_id=? ORDER BY name', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows  # [(id, name), ...]

def get_muscle_group_name(user_id, group_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name FROM muscle_groups WHERE user_id=? AND id=?', (user_id, group_id))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def add_muscle_group(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO muscle_groups (user_id, name) VALUES (?, ?)', (user_id, name))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_muscle_group(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM muscle_groups WHERE user_id=? AND name=?', (user_id, name))
    conn.commit()
    conn.close()

def rename_muscle_group(user_id, old_name, new_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('UPDATE muscle_groups SET name=? WHERE user_id=? AND name=?', (new_name, user_id, old_name))
        conn.commit()
        return c.rowcount > 0
    finally:
        conn.close()

# --- Обработчики ---
@dp.message(lambda m: m.text == "➕ Добавить")
async def add_muscle_start(message: Message, state: FSMContext):
    await state.set_state(MuscleFSM.add)
    await state.update_data(prev=NavStates.muscle_groups.state)
    await message.answer("Введите название новой части тела:")

@dp.message(MuscleFSM.add)
async def add_muscle_save(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    if add_muscle_group(user_id, name):
        await message.answer(f"Часть тела '{name}' добавлена.")
    else:
        await message.answer(f"Часть тела '{name}' уже существует.")
    await muscle_groups(message, state)

@dp.message(lambda m: m.text == "➖ Удалить")
async def del_muscle_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    muscles = get_muscle_groups(user_id)
    await state.set_state(MuscleFSM.delete_select)
    await state.update_data(prev=NavStates.muscle_groups.state)
    if not muscles:
        await message.answer("У вас нет существующих частей тела.")
        await muscle_groups(message, state)
        return
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=name)] for _, name in muscles
    ] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Выберите часть тела для удаления:", reply_markup=keyboard)

@dp.message(MuscleFSM.delete_select)
async def del_muscle_confirm(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    muscles = get_muscle_groups(user_id)
    if name == "⬅️ Назад":
        await muscle_groups(message, state)
        return
    if name not in [m[1] for m in muscles]:
        await message.answer("Такой части тела нет. Выберите из списка.")
        return
    delete_muscle_group(user_id, name)
    await message.answer(f"Часть тела '{name}' удалена.")
    await muscle_groups(message, state)

@dp.message(lambda m: m.text == "♻️ Редактировать")
async def edit_muscle_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    muscles = get_muscle_groups(user_id)
    await state.set_state(MuscleFSM.edit_select)
    await state.update_data(prev=NavStates.muscle_groups.state)
    if not muscles:
        await message.answer("У вас нет существующих частей тела.")
        await muscle_groups(message, state)
        return
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=name)] for _, name in muscles
    ] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Выберите часть тела для редактирования:", reply_markup=keyboard)

@dp.message(MuscleFSM.edit_select)
async def edit_muscle_ask_new(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    muscles = get_muscle_groups(user_id)
    if name == "⬅️ Назад":
        await muscle_groups(message, state)
        return
    if name not in [m[1] for m in muscles]:
        await message.answer("Такой части тела нет. Выберите из списка.")
        return
    await state.set_state(MuscleFSM.edit_rename)
    await state.update_data(editing=name, prev=NavStates.muscle_groups.state)
    await message.answer(f"Введите новое название для '{name}':")

@dp.message(MuscleFSM.edit_rename)
async def edit_muscle_save(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    old_name = data.get("editing")
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    if old_name == new_name:
        await message.answer("Новое название совпадает с текущим. Введите другое:")
        return
    if not rename_muscle_group(user_id, old_name, new_name):
        await message.answer("Ошибка при переименовании. Возможно, такое название уже есть.")
    else:
        await message.answer(f"Часть тела '{old_name}' переименована в '{new_name}'.")
    await muscle_groups(message, state)

# --- Упражнения ---
def add_exercise(user_id, muscle_group_id, name, video, description):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO exercises (user_id, muscle_group, name, video, description) VALUES (?, ?, ?, ?, ?)',
                  (user_id, muscle_group_id, name, video, description))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_exercises(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name FROM exercises WHERE user_id=? ORDER BY name', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_exercise(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT muscle_group, name, video, description FROM exercises WHERE user_id=? AND name=?', (user_id, name))
    row = c.fetchone()
    conn.close()
    return row

def delete_exercise(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM exercises WHERE user_id=? AND name=?', (user_id, name))
    conn.commit()
    conn.close()

def update_exercise(user_id, old_name, muscle_group=None, name=None, video=None, description=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = []
    values = []
    if muscle_group is not None:
        fields.append('muscle_group=?')
        values.append(muscle_group)
    if name is not None:
        fields.append('name=?')
        values.append(name)
    if video is not None:
        fields.append('video=?')
        values.append(video)
    if description is not None:
        fields.append('description=?')
        values.append(description)
    if not fields:
        conn.close()
        return False
    values.append(user_id)
    values.append(old_name)
    c.execute(f'UPDATE exercises SET {", ".join(fields)} WHERE user_id=? AND name=?', values)
    conn.commit()
    conn.close()
    return True

@dp.message(lambda m: m.text == "Упражнения")
async def exercises_menu(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить"), KeyboardButton(text="➖ Удалить"), KeyboardButton(text="♻️ Редактировать")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)
    await state.set_state(NavStates.exercises)
    await state.update_data(prev=NavStates.exercises.state)
    await message.answer(
        "В этом разделе вы можете добавлять, удалять и редактировать упражнения, например: Подъем на бицепс.",
        reply_markup=keyboard
    )

# --- Добавление упражнения ---
@dp.message(lambda m: m.text == "➕ Добавить" and (state := FSMContext.get_current()) and state.state in [NavStates.exercises.state])
async def add_exercise_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    muscles = get_muscle_groups(user_id)
    if not muscles:
        await message.answer("Сначала добавьте хотя бы одну группу мышц.")
        await exercises_menu(message, state)
        return
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=f"{name} (id:{mid})")] for mid, name in muscles] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await state.set_state(ExerciseFSM.add_select_muscle)
    await state.update_data(prev=NavStates.exercises.state, muscle_map={f"{name} (id:{mid})": mid for mid, name in muscles})
    await message.answer("Выберите группу мышц для упражнения:", reply_markup=keyboard)

@dp.message(ExerciseFSM.add_select_muscle)
async def add_exercise_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    muscle_map = data.get("muscle_map", {})
    muscle_key = message.text.strip()
    if muscle_key == "⬅️ Назад":
        await exercises_menu(message, state)
        return
    if muscle_key not in muscle_map:
        await message.answer("Выберите группу мышц из списка.")
        return
    muscle_id = muscle_map[muscle_key]
    await state.set_state(ExerciseFSM.add_name)
    await state.update_data(muscle=muscle_id, prev=NavStates.exercises.state)
    await message.answer("Введите название упражнения:")

@dp.message(ExerciseFSM.add_name)
async def add_exercise_video(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Введите ещё раз:")
        return
    await state.set_state(ExerciseFSM.add_video)
    await state.update_data(name=name)
    await message.answer("Отправьте ссылку на видео (или напишите 'Пропустить'):")

@dp.message(ExerciseFSM.add_video)
async def add_exercise_desc(message: Message, state: FSMContext):
    video = message.text.strip()
    if video.lower() == "пропустить":
        video = ""
    await state.set_state(ExerciseFSM.add_desc)
    await state.update_data(video=video)
    await message.answer("Введите описание упражнения (или напишите 'Пропустить'):")

@dp.message(ExerciseFSM.add_desc)
async def add_exercise_save(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc.lower() == "пропустить":
        desc = ""
    data = await state.get_data()
    user_id = message.from_user.id
    ok = add_exercise(user_id, data["muscle"], data["name"], data["video"], desc)
    if ok:
        await message.answer(f"Упражнение '{data['name']}' добавлено.")
    else:
        await message.answer(f"Упражнение с таким названием уже существует.")
    await exercises_menu(message, state)

# --- Удаление упражнения ---
@dp.message(lambda m: m.text == "➖ Удалить" and (state := FSMContext.get_current()) and state.state in [NavStates.exercises.state])
async def del_exercise_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    exercises = get_exercises(user_id)
    await state.set_state(ExerciseFSM.delete_select)
    await state.update_data(prev=NavStates.exercises.state)
    if not exercises:
        await message.answer("У вас нет существующих упражнений.")
        await exercises_menu(message, state)
        return
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=e)] for e in exercises] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Выберите упражнение для удаления:", reply_markup=keyboard)

@dp.message(ExerciseFSM.delete_select)
async def del_exercise_confirm(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    exercises = get_exercises(user_id)
    if name == "⬅️ Назад":
        await exercises_menu(message, state)
        return
    if name not in exercises:
        await message.answer("Такого упражнения нет. Выберите из списка.")
        return
    delete_exercise(user_id, name)
    await message.answer(f"Упражнение '{name}' удалено.")
    await exercises_menu(message, state)

# --- Редактирование упражнения ---
@dp.message(lambda m: m.text == "♻️ Редактировать" and (state := FSMContext.get_current()) and state.state in [NavStates.exercises.state])
async def edit_exercise_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    exercises = get_exercises(user_id)
    await state.set_state(ExerciseFSM.edit_select)
    await state.update_data(prev=NavStates.exercises.state)
    if not exercises:
        await message.answer("У вас нет существующих упражнений.")
        await exercises_menu(message, state)
        return
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=e)] for e in exercises] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
    await message.answer("Выберите упражнение для редактирования:", reply_markup=keyboard)

@dp.message(ExerciseFSM.edit_select)
async def edit_exercise_field(message: Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text.strip()
    exercises = get_exercises(user_id)
    if name == "⬅️ Назад":
        await exercises_menu(message, state)
        return
    if name not in exercises:
        await message.answer("Такого упражнения нет. Выберите из списка.")
        return
    await state.set_state(ExerciseFSM.edit_field)
    await state.update_data(editing=name, prev=NavStates.exercises.state)
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Группа мышц"), KeyboardButton(text="Название")],
        [KeyboardButton(text="Видео"), KeyboardButton(text="Описание")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)
    await message.answer("Что хотите изменить?", reply_markup=keyboard)

@dp.message(ExerciseFSM.edit_field)
async def edit_exercise_value(message: Message, state: FSMContext):
    field = message.text.strip()
    data = await state.get_data()
    user_id = message.from_user.id
    if field == "⬅️ Назад":
        await edit_exercise_start(message, state)
        return
    if field not in ["Группа мышц", "Название", "Видео", "Описание"]:
        await message.answer("Выберите поле из списка.")
        return
    await state.set_state(ExerciseFSM.edit_value)
    await state.update_data(edit_field=field, prev=NavStates.exercises.state)
    if field == "Группа мышц":
        muscles = get_muscle_groups(user_id)
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=f"{name} (id:{mid})")] for mid, name in muscles] + [[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)
        await state.update_data(muscle_map={f"{name} (id:{mid})": mid for mid, name in muscles})
        await message.answer("Выберите новую группу мышц:", reply_markup=keyboard)
    else:
        await message.answer(f"Введите новое значение для поля '{field}':")

@dp.message(ExerciseFSM.edit_value)
async def edit_exercise_save(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    old_name = data.get("editing")
    field = data.get("edit_field")
    value = message.text.strip()
    if value == "⬅️ Назад":
        await edit_exercise_field(message, state)
        return
    if field == "Группа мышц":
        muscle_map = data.get("muscle_map", {})
        if value not in muscle_map:
            await message.answer("Выберите группу мышц из списка.")
            return
        update_exercise(user_id, old_name, muscle_group=muscle_map[value])
        await message.answer(f"Группа мышц для '{old_name}' изменена.")
    elif field == "Название":
        if not value:
            await message.answer("Название не может быть пустым.")
            return
        update_exercise(user_id, old_name, name=value)
        await message.answer(f"Название упражнения изменено на '{value}'.")
    elif field == "Видео":
        update_exercise(user_id, old_name, video=value)
        await message.answer(f"Видео для '{old_name}' изменено.")
    elif field == "Описание":
        update_exercise(user_id, old_name, description=value)
        await message.answer(f"Описание для '{old_name}' изменено.")
    await exercises_menu(message, state)

if __name__ == "__main__":
    init_db()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(dp.start_polling(bot))
