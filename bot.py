import os
import logging
import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from ai_work import start_consilium, stats as consilium_stats, history
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # NEW
from photo_processor import convert_to_sketch, convert_to_anime, convert_to_sepia, convert_to_hard_rock

# ========== МЕНЮ С КНОПКАМИ ==========
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение с кнопками для выбора стиля."""
    keyboard = [
        [InlineKeyboardButton("✏️ Карандаш", callback_data='sketch'),
         InlineKeyboardButton("🎌 Аниме", callback_data='anime')],
        [InlineKeyboardButton("🟫 Сепия", callback_data='sepia'),
         InlineKeyboardButton("🤘 Хард-рок", callback_data='hardrock')],
        [InlineKeyboardButton("🟩 Пиксель (Minecraft)", callback_data='pixel'),
         InlineKeyboardButton("🌈 Неон", callback_data='neon')],
        [InlineKeyboardButton("🖼️ Масло", callback_data='oil'),
         InlineKeyboardButton("💧 Акварель", callback_data='watercolor')],
        [InlineKeyboardButton("🧸 Мультяшный", callback_data='cartoon')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎨 Выбери стиль для фото:", reply_markup=reply_markup)

def clean_markdown(text):
    """
    Удаляет из текста MarkDown-символы: **жирный**, *курсив*, __подчёркнутый__, `код`.
    Оставляет только чистый текст.
    """
    # Убираем **жирный**
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # Убираем *курсив*
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Убираем __подчёркнутый__
    text = re.sub(r'__(.*?)__', r'\1', text)
    # Убираем `код`
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ТОКЕН БОТА ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# === ПРОСТОЙ HTTP-СЕРВЕР ДЛЯ RENDER (ПОРТ 10000) ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Подавляем логи сервера, чтобы не засорять консоль
        pass

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"HTTP-сервер запущен на порту {port} (для Render)")
    server.serve_forever()

# Запускаем HTTP-сервер в отдельном потоке
http_thread = Thread(target=run_http_server, daemon=True)
http_thread.start()

# === ОБРАБОТЧИКИ КОМАНД ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Привет! Я твой AI-консилиум. Задай любой вопрос, и я постараюсь дать наилучший ответ.\n\n"
        "Команды:\n"
        "/stats — статистика работы\n"
        "/reset — сбросить историю диалога"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📊 **Статистика работы:**\n"
    text += f"Всего попыток запросов: {consilium_stats['attempts']}\n"
    text += f"Успешно: {consilium_stats['success']}\n"
    text += f"Ошибок: {consilium_stats['failures']}\n"
    text += "Использованные модели:\n"
    for model, count in consilium_stats['models_used'].items():
        text += f"  {model}: {count} раз(а)\n"
    await update.message.reply_text(text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history.clear()
    await update.message.reply_text("🔄 История диалога очищена.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    logger.info(f"Вопрос от {update.effective_user.id}: {user_question}")

    await update.message.chat.send_action(action="typing")

    try:
        answer = start_consilium(user_question)
        clean_answer = clean_markdown(answer)  # ← очищаем от звёздочек
        # Разбиваем длинные сообщения
        if len(clean_answer) > 4000:
            for i in range(0, len(clean_answer), 4000):
                await update.message.reply_text(clean_answer[i:i+4000])
        else:
            await update.message.reply_text(clean_answer)
    except Exception as e:
        logger.exception("Ошибка при обработке вопроса")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")
        # ========== ОБРАБОТЧИКИ ДЛЯ ФОТО ==========
async def sketch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото, и я сделаю из него карандашный рисунок!")
    context.user_data['effect'] = 'sketch'

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото, и я придам ему аниме-стиль!")
    context.user_data['effect'] = 'anime'

async def sepia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото, и я добавлю тёплый винтажный оттенок!")
    context.user_data['effect'] = 'sepia'

async def hardrock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото, и я сделаю его резким и контрастным!")
    context.user_data['effect'] = 'hardrock'

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'effect' not in context.user_data:
        await update.message.reply_text("Сначала выбери эффект: /sketch, /anime, /sepia или /hardrock")
        return

    effect = context.user_data['effect']
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    try:
        if effect == 'sketch':
            output = convert_to_sketch(photo_bytes)
            caption = "Карандашный рисунок готов!"
        elif effect == 'anime':
            output = convert_to_anime(photo_bytes)
            caption = "Аниме-стиль применён!"
        elif effect == 'sepia':
            output = convert_to_sepia(photo_bytes)
            caption = "Сепия добавлена!"
        elif effect == 'hardrock':
            output = convert_to_hard_rock(photo_bytes)
            caption = "Хард-рок стиль готов!"
        elif effect == 'pixel':
            output = convert_to_pixel(photo_bytes)
            caption = "Пиксельный Minecraft-стиль готов!"
        elif effect == 'neon':
            output = convert_to_neon(photo_bytes)
            caption = "Неоновые цвета!"
        elif effect == 'oil':
            output = convert_to_oil(photo_bytes)
            caption = "Масляная живопись!"
        elif effect == 'watercolor':
            output = convert_to_watercolor(photo_bytes)
            caption = "Акварельный эффект!"
        elif effect == 'cartoon':
            output = convert_to_cartoon(photo_bytes)
            caption = "Мультяшный стиль!"
        else:
            await update.message.reply_text("Неизвестный эффект.")
            return

        await update.message.reply_photo(photo=output, caption=caption)
        # del context.user_data['effect']  # если хочешь, чтобы эффект сбрасывался после одного фото
    except Exception as e:
        logger.exception("Ошибка при обработке фото")
        await update.message.reply_text("❌ Не удалось обработать фото. Попробуй другое.")
# ========== КОНЕЦ НОВЫХ ОБРАБОТЧИКОВ ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    # Сохраняем выбранный эффект в user_data
    context.user_data['effect'] = query.data
    effect_names = {
        'sketch': 'карандашный рисунок',
        'anime': 'аниме',
        'sepia': 'сепия',
        'hardrock': 'хард-рок',
        'pixel': 'пиксельный (Minecraft)',
        'neon': 'неон',
        'oil': 'масло',
        'watercolor': 'акварель',
        'cartoon': 'мультяшный'
    }
    name = effect_names.get(query.data, query.data)
    await query.edit_message_text(f"✅ Выбран стиль: {name}\nТеперь отправь фото!")

async def set_effect(update: Update, context: ContextTypes.DEFAULT_TYPE, effect: str):
    """Устанавливает эффект и просит отправить фото."""
    context.user_data['effect'] = effect
    await update.message.reply_text(f"Отправь фото для обработки в стиле {effect}!")

# === ЗАПУСК БОТА ===
def main():
    if not TOKEN:
        raise ValueError("❌ Нет токена! Добавь TELEGRAM_BOT_TOKEN в переменные окружения.")

    # Создаём цикл событий asyncio для бота
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("sketch", sketch_command))
    app.add_handler(CommandHandler("anime", anime_command))
    app.add_handler(CommandHandler("sepia", sepia_command))
    app.add_handler(CommandHandler("hardrock", hardrock_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("pixel", lambda u,c: set_effect(u,c,'pixel')))
    app.add_handler(CommandHandler("neon", lambda u,c: set_effect(u,c,'neon')))
    app.add_handler(CommandHandler("oil", lambda u,c: set_effect(u,c,'oil')))
    app.add_handler(CommandHandler("watercolor", lambda u,c: set_effect(u,c,'watercolor')))
    app.add_handler(CommandHandler("cartoon", lambda u,c: set_effect(u,c,'cartoon')))
    app.add_handler(CallbackQueryHandler(button_handler))

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех команд и кнопки."""
    help_text = (
        "🤖 **Доступные команды:**\n\n"
        "🔹 `/start` - Приветствие\n"
        "🔹 `/stats` - Статистика работы\n"
        "🔹 `/reset` - Сброс истории\n"
        "🔹 `/menu` - Меню с кнопками для фото\n"
        "🔹 `/help` - Это сообщение\n\n"
        "**Команды для фото:**\n"
        "`/sketch`, `/anime`, `/sepia`, `/hardrock`,\n"
        "`/pixel`, `/neon`, `/oil`, `/watercolor`, `/cartoon`\n\n"
        "🎯 После команды отправь фото, и я обработаю его!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

    logger.info("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
