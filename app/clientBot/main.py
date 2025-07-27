from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
import asyncio

# Токен бота
TOKEN = "8259271597:AAE4tAwidRXXYW2DC2ISsjYjZpuIl6poGv8"

# Кнопки
# Кнопка "Упражнения"
exercises_button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💪 Упражнения")]
], resize_keyboard=True)

# Кнопка "Связаться"
contact_button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="❓ Связаться")]
], resize_keyboard=True)

# Кнопка "Выход"
exit_button = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚪 Выход")]
], resize_keyboard=True)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()


# /start
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я TrainerBot. Выберите команду ниже:", reply_markup=keyboard)


# Обработка кнопок
@dp.message()
async def handle_buttons(message: types.Message):
    text = message.text

    if text == "💪 Упражнения":
        await message.answer("Привет! Чем могу помочь?")
    elif text == "❓ Связаться":
        await message.answer("Доступные команды:\n- Привет\n- Помощь\n- Выход")
    elif text == "🚪 Выход":
        await message.answer("Бот завершает работу. Пока 👋")
    else:
        await message.answer("Я не понимаю эту команду. Пожалуйста, нажмите кнопку.")


# Запуск
async def main():
    print("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
