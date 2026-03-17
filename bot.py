import os
import logging
import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from ai_work import start_consilium, stats as consilium_stats, history
import re

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

    logger.info("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
