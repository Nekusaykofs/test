import os
import logging
import requests
import aiohttp
import asyncio
import psycopg2
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.dispatcher.filters import Text

# .env
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DB_URL = os.getenv("DATABASE_URL")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

# Голоса
VOICE_ID_DENIS = "0BcDz9UPwL3MpsnTeUlO"
VOICE_ID_OGE = "MWyJiWDobXN8FX3CJTdE"
VOICE_ID_ANYA = "EDpEYNf6XIeKYRzYcx4I"
VOICE_ID_VIKA = "FZGeNF7bE3syeQOynDKC"

# Бот и логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Кнопки
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add(KeyboardButton("🔊 Озвучить текст"), KeyboardButton("🎙 Заменить голос"))
main_kb.add(KeyboardButton("🗣 Выбрать голос"), KeyboardButton("👤 Профиль"))

voice_kb = ReplyKeyboardMarkup(resize_keyboard=True)
voice_kb.add(KeyboardButton("Денис"), KeyboardButton("Олег"))
voice_kb.add(KeyboardButton("Аня"), KeyboardButton("Вика"))
voice_kb.add(KeyboardButton("Назад"))

# FSM
class VoiceState(StatesGroup):
    waiting_for_text = State()

# Подключение к базе
conn = psycopg2.connect(DB_URL, sslmode='require')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    voice TEXT DEFAULT 'Денис',
    free_messages_used INT DEFAULT 0
)''')
conn.commit()

# Утилиты
async def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    return cursor.fetchone()

def update_user_voice(user_id, voice):
    cursor.execute("UPDATE users SET voice = %s WHERE id = %s", (voice, user_id))
    conn.commit()

async def increment_free_messages(user_id):
    cursor.execute("UPDATE users SET free_messages_used = free_messages_used + 1 WHERE id = %s", (user_id,))
    conn.commit()

def get_free_messages_left(user_id):
    cursor.execute("SELECT free_messages_used FROM users WHERE id = %s", (user_id,))
    used = cursor.fetchone()[0]
    return max(0, 5 - used)

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    if not await get_user(user_id):
        cursor.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
        conn.commit()
    await message.answer("Привет! Я бот для озвучки текста и изменения голоса.", reply_markup=main_kb)

@dp.message_handler(lambda message: message.text == "👤 Профиль")
async def profile(message: types.Message):
    user = await get_user(message.from_user.id)
    free_used = user[2]
    free_left = max(0, 5 - free_used)
    await message.answer(f"Ваш ID: {message.from_user.id}\nБесплатных сообщений использовано: {free_used}/5\nОсталось: {free_left}")

@dp.message_handler(lambda message: message.text == "🗣 Выбрать голос")
async def choose_voice(message: types.Message):
    await message.answer("Выберите голос:", reply_markup=voice_kb)

@dp.message_handler(lambda message: message.text in ["Денис", "Олег", "Аня", "Вика"])
async def set_voice(message: types.Message):
    update_user_voice(message.from_user.id, message.text)
    await message.answer(f"Голос установлен: {message.text}", reply_markup=main_kb)

@dp.message_handler(lambda message: message.text == "🔊 Озвучить текст")
async def start_voice(message: types.Message):
    await message.answer("Введите текст для озвучивания (до 60 символов):")
    await VoiceState.waiting_for_text.set()

@dp.message_handler(state=VoiceState.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if len(text) > 60:
        await message.answer("Текст слишком длинный. Максимум 60 символов.")
        return

    user = await get_user(message.from_user.id)
    if user[2] >= 5:
        await message.answer("Вы использовали все бесплатные сообщения. Платная часть ещё не реализована.")
        await state.finish()
        return

    await increment_free_messages(message.from_user.id)
    voice = user[1]
    voice_id = {
        "Денис": VOICE_ID_DENIS,
        "Олег": VOICE_ID_OGE,
        "Аня": VOICE_ID_ANYA,
        "Вика": VOICE_ID_VIKA
    }[voice]

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        "model_id": "eleven_monolingual_v1"
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                audio = await resp.read()
                with open("voice.ogg", "wb") as f:
                    f.write(audio)
                with open("voice.ogg", "rb") as f:
                    await message.answer_voice(f)
            else:
                await message.answer("Произошла ошибка при озвучке текста.")

    await state.finish()

@dp.message_handler(commands=['users'])
async def users_count(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        await message.answer(f"Всего пользователей: {count}")

@dp.message_handler(commands=['broadcast'])
async def broadcast_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.get_args()
    if not args:
        await message.answer("Введите сообщение после команды /broadcast")
        return
    cursor.execute("SELECT id FROM users")
    user_ids = cursor.fetchall()
    for (uid,) in user_ids:
        try:
            await bot.send_message(uid, args)
        except Exception:
            continue
    await message.answer("Рассылка завершена.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

