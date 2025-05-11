import os
import requests
import asyncio
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from urllib.parse import urlparse

# --- Настройки ---
API_KEY = os.getenv("ELEVEN_API_KEY")
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6728899517

VOICE_ID_DENIS = '0BcDz9UPwL3MpsnTeUlO'
VOICE_ID_OGE = 'MWyJiWDobXN8FX3CJTdE'
VOICE_ID_ANYA = 'rxEz5E7hIAPk7D3bXwf6'
VOICE_ID_VIKA = '8M81RK3MD7u4DOJpu2G5'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- База данных ---
DATABASE_URL = os.getenv("DATABASE_URL")
url = urlparse(DATABASE_URL)
conn = psycopg2.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY,
        voice_balance INTEGER DEFAULT 5
    )
''')
conn.commit()

# --- Клавиатуры ---
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add(
    KeyboardButton("🗣 Озвучить текст"),
    KeyboardButton("🎧 Заменить голос"),
    KeyboardButton("📖 Инструкция"),
    KeyboardButton("👤 Профиль")
)

voice_kb = ReplyKeyboardMarkup(resize_keyboard=True)
voice_kb.add(
    KeyboardButton("Денис"),
    KeyboardButton("Олег"),
    KeyboardButton("Аня"),
    KeyboardButton("Вика"),
    KeyboardButton("⬅️ Назад")
)

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add(KeyboardButton("⬅️ Назад"))

instruction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
instruction_kb.add(KeyboardButton("⬅️ Назад"))

selected_voice = {}

def get_emotion_settings(text):
    happy = ['😂', '🤣', '😄']
    sad = ['😢', '😭', '💔']
    angry = ['😡', '🤬']
    warm = ['😊', '❤️', '🥰']

    happy_count = sum(text.count(e) for e in happy)
    sad_count = sum(text.count(e) for e in sad)
    angry_count = sum(text.count(e) for e in angry)
    warm_count = sum(text.count(e) for e in warm)

    if max(happy_count, sad_count, angry_count, warm_count) == 0:
        return 0.5, 0.75

    mood = max([
        (happy_count, (0.3, 0.9)),
        (sad_count, (0.7, 0.5)),
        (angry_count, (0.8, 0.6)),
        (warm_count, (0.4, 0.8))
    ], key=lambda x: x[0])[1]

    return mood

instruction_text = (
    "📖 Инструкция по использованию бота:\n\n"
    "1. 🗣 *Озвучивание текста:*\n"
    "   • Нажми кнопку \"🗣 Озвучить текст\".\n"
    "   • Выбери голос (Олег, Денис, Аня, Вика).\n"
    "   • Отправь текст (до 200 символов).\n"
    "   • Добавляй смайлы для эмоций:\n"
    "     😂🤣😄 — весёлый, 😢😭💔 — грустный, 😡🤬 — злой, 😊❤️🥰 — тёплый.\n\n"
    "2. 🎧 *Замена голоса в голосовом сообщении:*\n"
    "   • Нажми \"🎧 Заменить голос\".\n"
    "   • Выбери голос.\n"
    "   • Отправь голосовое (до 15 секунд).\n\n"
    "❗️Если превысишь лимит, бот сообщит об этом.\n"
)

def is_text_too_long(text):
    return len(text) > 200

def is_voice_too_long(voice_duration):
    return voice_duration > 15

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('INSERT INTO users (id, voice_balance) VALUES (%s, %s) ON CONFLICT DO NOTHING', (user_id, 5))
    conn.commit()

    welcome = (
        "Добро пожаловать в бот 🎤🎧\n\n"
        "Я умею озвучивать текст разными голосами и менять голос в сообщениях.\n"
        "Выбери действие ниже и попробуй! 😊"
    )
    await message.answer(welcome, reply_markup=main_kb)

@dp.message_handler(lambda msg: msg.text == "👤 Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT voice_balance FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    balance = result[0] if result else 0
    await message.answer(f"👤 Ваш ID: `{user_id}`\n💬 Голосовых сообщений осталось: *{balance}*", parse_mode="Markdown")

@dp.message_handler(lambda msg: msg.text == "🗣 Озвучить текст")
async def tts_request(message: types.Message):
    await message.answer("Выбери голос и отправь текст:", reply_markup=voice_kb)

@dp.message_handler(lambda msg: msg.text == "🎧 Заменить голос")
async def vc_request(message: types.Message):
    await message.answer("Выбери голос для замены и отправь голосовое:", reply_markup=voice_kb)

@dp.message_handler(lambda msg: msg.text == "📖 Инструкция")
async def instruction(message: types.Message):
    await message.answer(instruction_text, reply_markup=instruction_kb)

@dp.message_handler(lambda msg: msg.text == "⬅️ Назад")
async def back_to_main(message: types.Message):
    await message.answer("Выбери действие:", reply_markup=main_kb)

@dp.message_handler(lambda msg: msg.text in ["Денис", "Олег", "Аня", "Вика"])
async def handle_voice_choice(message: types.Message):
    selected_voice[message.from_user.id] = message.text
    await message.answer(f"Выбран голос: {message.text}. Отправь текст:", reply_markup=back_kb)

@dp.message_handler(lambda msg: msg.text not in ["🗣 Озвучить текст", "🎧 Заменить голос", "⬅️ Назад", "Денис", "Олег", "Аня", "Вика", "📖 Инструкция", "👤 Профиль"])
async def handle_text(message: types.Message):
    user_id = message.from_user.id

    cursor.execute("SELECT voice_balance FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    balance = result[0] if result else 0
    if balance <= 0:
        await message.answer("❌ У вас закончились голосовые сообщения. Пожалуйста, пополните баланс.")
        return

    if is_text_too_long(message.text):
        await message.answer("Ваш текст слишком длинный! Пожалуйста, уменьшите его до 200 символов.")
        return

    voice = selected_voice.get(user_id)
    if not voice:
        await message.answer("Сначала выбери голос.")
        return

    text = message.text
    stability, similarity = get_emotion_settings(text)

    status = await message.answer("⌛ Озвучиваю...")

    headers = {
        'xi-api-key': API_KEY,
        'Content-Type': 'application/json'
    }

    data = {
        'text': text,
        'model_id': 'eleven_multilingual_v2',
        'voice_settings': {
            'stability': stability,
            'similarity_boost': similarity
        }
    }

    voice_map = {
        "Денис": VOICE_ID_DENIS,
        "Олег": VOICE_ID_OGE,
        "Аня": VOICE_ID_ANYA,
        "Вика": VOICE_ID_VIKA
    }

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_map[voice]}",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        cursor.execute("UPDATE users SET voice_balance = voice_balance - 1 WHERE id = %s", (user_id,))
        conn.commit()

        with open('output.mp3', 'wb') as f:
            f.write(response.content)
        with open('output.mp3', 'rb') as f:
            await bot.send_voice(chat_id=message.chat.id, voice=f)
    else:
        await message.answer(f"Ошибка озвучивания: {response.status_code}")

    await status.delete()

@dp.message_handler(content_types=['voice'])
async def handle_voice(message: types.Message):
    user_id = message.from_user.id

    voice = selected_voice.get(user_id)
    if not voice:
        await message.answer("Сначала выбери голос для замены.")
        return

    if is_voice_too_long(message.voice.duration):
        await message.answer("Ваше голосовое сообщение слишком длинное! Пожалуйста, ограничьте его 15 секундами.")
        return

    cursor.execute("SELECT voice_balance FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    balance = result[0] if result else 0
    if balance <= 0:
        await message.answer("❌ У вас закончились голосовые сообщения. Пожалуйста, пополните баланс.")
        return

    status = await message.answer("⌛ Заменяю голос...")

    file_info = await bot.get_file(message.voice.file_id)
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
    voice_data = requests.get(file_url).content

    headers = {'xi-api-key': API_KEY}
    files = {'audio': ('voice_message.ogg', voice_data, 'audio/ogg')}

    voice_map = {
        "Денис": VOICE_ID_DENIS,
        "Олег": VOICE_ID_OGE,
        "Аня": VOICE_ID_ANYA,
        "Вика": VOICE_ID_VIKA
    }

    response = requests.post(
        f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_map[voice]}",
        headers=headers,
        files=files
    )

    if response.status_code == 200:
        cursor.execute("UPDATE users SET voice_balance = voice_balance - 1 WHERE id = %s", (user_id,))
        conn.commit()

        with open('converted.mp3', 'wb') as f:
            f.write(response.content)
        with open('converted.mp3', 'rb') as f:
            await bot.send_voice(chat_id=message.chat.id, voice=f)
    else:
        await message.answer(f"Ошибка замены: {response.status_code}, {response.text}")

    await status.delete()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
