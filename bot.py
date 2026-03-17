import os
import logging
import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from ai_work import start_consilium, stats as consilium_stats, history
import re
from photo_processor import convert_to_sketch, convert_to_anime, convert_to_sepia, convert_to_hard_rock

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
        else:
            await update.message.reply_text("Неизвестный эффект.")
            return

        await update.message.reply_photo(photo=output, caption=caption)
        # del context.user_data['effect']  # если хочешь, чтобы эффект сбрасывался после одного фото
    except Exception as e:
        logger.exception("Ошибка при обработке фото")
        await update.message.reply_text("❌ Не удалось обработать фото. Попробуй другое.")
# ========== КОНЕЦ НОВЫХ ОБРАБОТЧИКОВ ==========
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

    logger.info("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
