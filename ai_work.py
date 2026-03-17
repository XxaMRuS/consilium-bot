import os
import requests
import logging
import google.generativeai as genai
from collections import deque
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# === ФЛАГИ ВКЛЮЧЕНИЯ ПРОВАЙДЕРОВ ===
ENABLED_PROVIDERS = {
    "openrouter": True,
    "groq": True,
    "yandex": True,
    "deepseek_old": False,
    "gemini_old": False,
}

if not all([YANDEX_API_KEY, YANDEX_FOLDER_ID, DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY]):
    raise ValueError("❌ Не все ключи найдены в .env! Проверь файл.")

# ... (весь остальной код, который был у тебя в ai_work.py)
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Импортируем твой консилиум
from ai_work import start_consilium, stats as consilium_stats, history

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен из переменной окружения
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Привет! Я твой AI-консилиум. Задай любой вопрос, и я постараюсь дать наилучший ответ.\n\n"
        "Команды:\n"
        "/stats — статистика работы\n"
        "/reset — сбросить историю диалога"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вывод статистики"""
    text = "📊 **Статистика работы:**\n"
    text += f"Всего попыток запросов: {consilium_stats['attempts']}\n"
    text += f"Успешно: {consilium_stats['success']}\n"
    text += f"Ошибок: {consilium_stats['failures']}\n"
    text += "Использованные модели:\n"
    for model, count in consilium_stats['models_used'].items():
        text += f"  {model}: {count} раз(а)\n"
    await update.message.reply_text(text)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс истории диалога"""
    history.clear()
    await update.message.reply_text("🔄 История диалога очищена.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    logger.info(f"Вопрос от {update.effective_user.id}: {user_question}")

    await update.message.chat.send_action(action="typing")

    try:
        answer = start_consilium(user_question)
        # Разбиваем длинные сообщения
        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                await update.message.reply_text(answer[i:i+4000])
        else:
            await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("Ошибка при обработке вопроса")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

def main():
    if not TOKEN:
        raise ValueError("❌ Нет токена! Добавь TELEGRAM_BOT_TOKEN в .env")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
