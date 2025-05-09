import os
import psycopg2
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from urllib.parse import urlparse

# --- Настройки ---
API_KEY = os.getenv("ELEVEN_API_KEY")
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6728899517

VOICE_ID_DENIS = '0BcDz9UPwL3MpsnTeUlO'  # Денис
VOICE_ID_OGE = 'MWyJiWDobXN8FX3CJTdE'    # Олег
VOICE_ID_ANYA = 'rxEz5E7hIAPk7D3bXwf6'   # Аня
VOICE_ID_VIKA = '8M81RK3MD7u4DOJpu2G5'   # Вика

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- База данных PostgreSQL ---
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
        voice_count INTEGER DEFAULT 0
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

# --- Переменные ---
selected_voice = {}

# --- Функция для проверки, использовал ли пользователь лимит ---
def has_reached_limit(user_id):
    cursor.execute("SELECT voice_count FROM users WHERE id = %s", (user_id,))
    result = cursor.fetchone()
    return result[0] >= 5  # Лимит на 5 бесплатных сообщений

# --- Команды ---
@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    cursor.execute('INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING', (user_id,))
    conn.commit()

    welcome = (
        "Добро пожаловать в бот 🎤🎧\n\n"
        "Я умею озвучивать текст разными голосами и менять голос в сообщениях.\n"
        "Выбери действие ниже и попробуй! 😊"
    )
    await message.answer(welcome, reply_markup=main_kb)

@dp.message_handler(lambda msg: msg.text == "🗣 Озвучить текст")
async def tts_request(message: types.Message):
    await message.answer("Выбери голос и отправь текст:", reply_markup=voice_kb)

@dp.message_handler(lambda msg: msg.text == "🎧 Заменить голос")
async def vc_request(message: types.Message):
    await message.answer("Выбери голос для замены и отправь голосовое:", reply_markup=voice_kb)

@dp.message_handler(lambda msg: msg.text == "👤 Профиль")
async def profile(message: types.Message):
    user_id = message.from_user.id
    try:
        cursor.execute("SELECT voice_count FROM users WHERE id = %s", (user_id,))
        result = cursor.fetchone()
        count = result[0] if result else 0
    except Exception as e:
        print(f"Ошибка при получении данных пользователя: {e}")
        await message.answer("Произошла ошибка при получении информации о вашем профиле.")
        return

    text = f"👤 Ваш ID: {user_id}\n🎙 Использовано голосовых сообщений: {count}"
    await message.answer(text, reply_markup=main_kb)

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

    # Проверка, использовал ли пользователь все бесплатные сообщения
    if has_reached_limit(user_id):
        await message.answer("Вы использовали все бесплатные голосовые сообщения. Для продолжения нужно приобрести дополнительные.")
        return

    voice = selected_voice.get(message.from_user.id)
    if not voice:
        await message.answer("Сначала выбери голос.")
        return

    text = message.text
    voice_map = {
        'Денис': VOICE_ID_DENIS,
        'Олег': VOICE_ID_OGE,
        'Аня': VOICE_ID_ANYA,
        'Вика': VOICE_ID_VIKA,
    }

    # Запрос к API ElevenLabs
    headers = {
        'xi-api-key': API_KEY,
        'Content-Type': 'application/json',
    }

    data = {
        "text": text,
    }

    response = requests.post(
        f'https://api.elevenlabs.io/v1/text-to-speech/{voice_map[voice]}',
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        audio_url = response.json().get('audio_url')
        await bot.send_audio(message.chat.id, audio_url)

        # Обновляем количество использованных голосовых сообщений
        cursor.execute("UPDATE users SET voice_count = voice_count + 1 WHERE id = %s", (user_id,))
        conn.commit()
    else:
        await message.answer("Произошла ошибка при озвучивании текста.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)



