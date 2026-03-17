import os
import logging
import asyncio
import re
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque

# === ИНИЦИАЛИЗАЦИЯ ASYNCIO ===
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Твои локальные модули
from ai_work import start_consilium, stats as consilium_stats, history
from photo_processor import (
    convert_to_sketch, convert_to_anime, convert_to_sepia, 
    convert_to_hard_rock, convert_to_pixel, convert_to_neon, 
    convert_to_oil, convert_to_watercolor, convert_to_cartoon
)

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ТОКЕН БОТА ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# === УТИЛИТЫ ===
def clean_markdown(text):
    """Удаляет из текста MarkDown-символы."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text

# === ПРОСТОЙ HTTP-СЕРВЕР ДЛЯ RENDER ===
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"HTTP-сервер запущен на порту {port}")
    server.serve_forever()

# Запускаем сервер в отдельном потоке
Thread(target=run_http_server, daemon=True).start()

# === ОБРАБОТЧИКИ КОМАНД ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Привет! Я твой AI-консилиум и графический редактор.\n\n"
        "Команды:\n"
        "/menu — выбрать стиль для фото\n"
        "/stats — статистика работы\n"
        "/reset — сбросить историю диалога\n"
        "/help — помощь"
    )

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение с кнопками для выбора стиля."""
    keyboard = [
        [InlineKeyboardButton("✏️ Карандаш", callback_data='sketch'),
         InlineKeyboardButton("🎌 Аниме", callback_data='anime')],
        [InlineKeyboardButton("🟫 Сепия", callback_data='sepia'),
         InlineKeyboardButton("🤘 Хард-рок", callback_data='hardrock')],
        [InlineKeyboardButton("🟩 Пиксель", callback_data='pixel'),
         InlineKeyboardButton("🌈 Неон", callback_data='neon')],
        [InlineKeyboardButton("🖼️ Масло", callback_data='oil'),
         InlineKeyboardButton("💧 Акварель", callback_data='watercolor')],
        [InlineKeyboardButton("🧸 Мультяшный", callback_data='cartoon')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎨 Выбери стиль для фото:", reply_markup=reply_markup)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📊 **Статистика работы:**\n"
    text += f"Всего попыток: {consilium_stats['attempts']}\n"
    text += f"Успешно: {consilium_stats['success']}\n"
    text += f"Ошибок: {consilium_stats['failures']}\n"
    for model, count in consilium_stats['models_used'].items():
        text += f"  {model}: {count}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history.clear()
    await update.message.reply_text("🔄 История диалога очищена.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Доступные команды:**\n\n"
        "🔹 `/start` - Запуск\n"
        "🔹 `/menu` - Выбор эффекта для фото\n"
        "🔹 `/stats` - Статистика\n"
        "🔹 `/reset` - Очистить память ИИ\n"
        "🔹 `/help` - Помощь\n\n"
        "Просто отправь текст, чтобы спросить ИИ, или фото (после выбора стиля в /menu)."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# === ОБРАБОТКА ТЕКСТА И ФОТО ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    await update.message.chat.send_action(action="typing")
    try:
        answer = start_consilium(user_question)
        clean_answer = clean_markdown(answer)
        if len(clean_answer) > 4000:
            for i in range(0, len(clean_answer), 4000):
                await update.message.reply_text(clean_answer[i:i+4000])
        else:
            await update.message.reply_text(clean_answer)
    except Exception as e:
        logger.exception("Ошибка в handle_message")
        await update.message.reply_text("❌ Ошибка при ответе ИИ.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['effect'] = query.data
    
    styles = {
        'sketch': 'карандаш', 'anime': 'аниме', 'sepia': 'сепия',
        'hardrock': 'хард-рок', 'pixel': 'пиксель', 'neon': 'неон',
        'oil': 'масло', 'watercolor': 'акварель', 'cartoon': 'мультяшный'
    }
    name = styles.get(query.data, query.data)
    await query.edit_message_text(f"✅ Выбран стиль: {name}. Теперь отправляй фото!")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'effect' not in context.user_data:
        await update.message.reply_text("Сначала выбери стиль через /menu")
        return

    effect = context.user_data['effect']
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    try:
        await update.message.reply_text("⏳ Обрабатываю фото...")
        
        # Словарь функций для вызова
        processors = {
            'sketch': convert_to_sketch,
            'anime': convert_to_anime,
            'sepia': convert_to_sepia,
            'hardrock': convert_to_hard_rock,
            'pixel': convert_to_pixel,
            'neon': convert_to_neon,
            'oil': convert_to_oil,
            'watercolor': convert_to_watercolor,
            'cartoon': convert_to_cartoon
        }
        
        if effect in processors:
            output = processors[effect](photo_bytes)
            await update.message.reply_photo(photo=output, caption=f"Готово! Стиль: {effect}")
        else:
            await update.message.reply_text("Неизвестный эффект.")
            
    except Exception as e:
        logger.exception("Ошибка в handle_photo")
        await update.message.reply_text("❌ Не удалось обработать фото.")

# === ЗАПУСК ===
def main():
    if not TOKEN:
        raise ValueError("Забыли TELEGRAM_BOT_TOKEN!")

    # Создаём цикл событий asyncio (обязательно для Python 3.14+)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset_command))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
