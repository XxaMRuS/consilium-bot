import os
import logging
import asyncio
import re
import json
import shlex
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque
from datetime import datetime

# === ИМПОРТЫ ДЛЯ ТЕЛЕГРАМА И КНОПОК ===
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# === ТВОИ ЛОКАЛЬНЫЕ МОДУЛИ ===
from ai_work import start_consilium, stats as consilium_stats, ENABLED_PROVIDERS
from photo_processor import (
    convert_to_sketch, convert_to_anime, convert_to_sepia, 
    convert_to_hard_rock, convert_to_pixel, convert_to_neon, 
    convert_to_oil, convert_to_watercolor, convert_to_cartoon
)

# === ИМПОРТЫ ДЛЯ БАЗЫ ДАННЫХ И ТРЕНИРОВОК ===
from database import (
    init_db, add_user, get_exercises, add_workout, add_exercise,
    set_exercise_week, get_user_stats, get_leaderboard,
    get_all_exercises, delete_exercise
)
from workout_handlers import (
    workout_start, exercise_choice, result_input, video_input,
    workout_cancel, EXERCISE, RESULT, VIDEO
)

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ТОКЕН БОТА (БЕРЁТСЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ) ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", 0))

# === ИНИЦИАЛИЗАЦИЯ ASYNCIO ===
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# === УТИЛИТЫ ===
def clean_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

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

Thread(target=run_http_server, daemon=True).start()

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
init_db()
logger.info("База данных готова к работе.")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Привет! Я твой AI-консилиум и фитнес-трекер.\n\n"
        "Команды:\n"
        "/menu — выбрать стиль для фото\n"
        "/stats — статистика AI\n"
        "/reset — сбросить историю диалога\n"
        "/help — помощь\n"
        "/wod — записать тренировку\n"
        "/mystats — моя статистика\n"
        "/top — таблица лидеров"
    )

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    text = "📊 **Статистика работы AI:**\n"
    text += f"Всего попыток: {consilium_stats['attempts']}\n"
    text += f"Успешно: {consilium_stats['success']}\n"
    text += f"Ошибок: {consilium_stats['failures']}\n"
    for model, count in consilium_stats['models_used'].items():
        text += f"  {model}: {count}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'user_history' in context.user_data:
        context.user_data['user_history'].clear()
    await update.message.reply_text("🔄 Твоя личная история диалога очищена.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Доступные команды:**\n\n"
        "🔹 `/start` - Запуск\n"
        "🔹 `/menu` - Выбор эффекта для фото\n"
        "🔹 `/stats` - Статистика AI\n"
        "🔹 `/reset` - Очистить свою историю диалога\n"
        "🔹 `/help` - Помощь\n"
        "🔹 `/config` - Настройки AI (только админ)\n"
        "🔹 `/wod` - Записать тренировку\n"
        "🔹 `/mystats [day|week|month]` - Моя статистика\n"
        "🔹 `/top [day|week|month]` - Таблица лидеров\n"
        "🔹 `/listexercises` - Список упражнений (админ)\n"
        "🔹 `/delexercise <id>` - Удалить упражнение (админ)\n"
        "🔹 `/load_exercises` - Загрузить из JSON (админ)\n\n"
        "Просто отправь текст, чтобы спросить ИИ, или фото (после выбора стиля в /menu)."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ========== КОНФИГУРАЦИЯ КОНСИЛИУМА (ТОЛЬКО ДЛЯ АДМИНА) ==========
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return
    keyboard = []
    for provider, enabled in ENABLED_PROVIDERS.items():
        status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
        keyboard.append([InlineKeyboardButton(f"{provider} {status}", callback_data=f"toggle_{provider}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ **Настройки консилиума**\n"
        "Нажми на кнопку, чтобы включить/выключить участника:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def config_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Недоступно.")
        return
    callback_data = query.data
    if callback_data.startswith("toggle_"):
        provider = callback_data.replace("toggle_", "")
        if provider in ENABLED_PROVIDERS:
            ENABLED_PROVIDERS[provider] = not ENABLED_PROVIDERS[provider]
            keyboard = []
            for p, enabled in ENABLED_PROVIDERS.items():
                status = "✅ ВКЛ" if enabled else "❌ ВЫКЛ"
                keyboard.append([InlineKeyboardButton(f"{p} {status}", callback_data=f"toggle_{p}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "⚙️ **Настройки консилиума**\n"
                "Нажми на кнопку, чтобы включить/выключить участника:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

# ========== ОБРАБОТКА ТЕКСТА И ФОТО ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    await update.message.chat.send_action(action="typing")
    try:
        if 'user_history' not in context.user_data:
            context.user_data['user_history'] = deque(maxlen=5)
        answer = start_consilium(user_question, context.user_data['user_history'])
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

# ========== АДМИН-КОМАНДЫ ДЛЯ УПРАЖНЕНИЙ ==========
async def add_exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет упражнение с поддержкой кавычек (исправленная версия)."""
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return

    full_text = update.message.text
    if ' ' not in full_text:
        await update.message.reply_text(
            "Использование: /addexercise <название> <reps|time> <описание> <баллы> [неделя]\n"
            "Пример: /addexercise \"Берпочки 50 штук\" reps \"Берпочки любимые\" 10"
        )
        return

    args_part = full_text.split(maxsplit=1)[1]
    try:
        args = shlex.split(args_part)
    except ValueError as e:
        await update.message.reply_text(f"❌ Ошибка в кавычках: {e}")
        return

    if len(args) < 4:
        await update.message.reply_text("❌ Нужно минимум 4 аргумента: название тип описание баллы")
        return

    name = args[0]
    metric = args[1]
    if metric not in ('reps', 'time'):
        await update.message.reply_text("❌ Тип упражнения должен быть 'reps' или 'time'.")
        return

    try:
        if len(args) == 5:
            week = int(args[-1])
            points = int(args[-2])
            description = " ".join(args[2:-2])
        elif len(args) == 4:
            week = 0
            points = int(args[-1])
            description = " ".join(args[2:-1])
        else:
            await update.message.reply_text("❌ Неправильное количество аргументов.")
            return
    except ValueError:
        await update.message.reply_text("❌ Баллы должны быть числом.")
        return

    if add_exercise(name, description, metric, points, week):
        week_text = f", неделя: {week}" if week != 0 else ""
        await update.message.reply_text(f"✅ Упражнение '{name}' добавлено (баллы: {points}{week_text}).")
    else:
        await update.message.reply_text(f"❌ Упражнение с таким именем уже существует.")

async def delete_exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /delexercise <id_упражнения>")
        return
    try:
        ex_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    if delete_exercise(ex_id):
        await update.message.reply_text(f"✅ Упражнение с ID {ex_id} удалено.")
    else:
        await update.message.reply_text(f"❌ Упражнение с ID {ex_id} не найдено.")

async def list_exercises_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    exercises = get_all_exercises()
    if not exercises:
        await update.message.reply_text("Список упражнений пуст.")
        return
    text = "📋 **Список упражнений:**\n\n"
    for ex in exercises:
        ex_id, name, metric, points, week = ex
        week_text = f" (неделя {week})" if week != 0 else ""
        text += f"🔹 ID: {ex_id} — {name} — {points} баллов{week_text}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def load_exercises_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    try:
        with open('exercises.json', 'r', encoding='utf-8') as f:
            exercises = json.load(f)
    except FileNotFoundError:
        await update.message.reply_text("❌ Файл exercises.json не найден.")
        return
    except json.JSONDecodeError:
        await update.message.reply_text("❌ Ошибка в JSON-файле.")
        return
    added = 0
    skipped = 0
    for ex in exercises:
        if add_exercise(ex['name'], ex['description'], ex['metric'], ex.get('points', 0), ex.get('week', 0)):
            added += 1
        else:
            skipped += 1
    await update.message.reply_text(f"✅ Загружено: {added} упражнений, пропущено (уже есть): {skipped}.")

# ========== СТАТИСТИКА ==========
async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    period = context.args[0] if context.args else None
    if period and period not in ('day', 'week', 'month'):
        await update.message.reply_text("❌ Неверный период. Используй: day, week, month")
        return
    total_points, total_workouts = get_user_stats(user_id, period)
    period_text = f" за {period}" if period else " за всё время"
    text = f"📊 **Твоя статистика{period_text}:**\n"
    text += f"🏋️ Тренировок: {total_workouts or 0}\n"
    text += f"⭐ Баллов: {total_points or 0}"
    await update.message.reply_text(text, parse_mode='Markdown')

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    period = context.args[0] if context.args else None
    if period and period not in ('day', 'week', 'month'):
        await update.message.reply_text("❌ Неверный период. Используй: day, week, month")
        return
    limit = 10
    leaderboard = get_leaderboard(period, limit)
    if not leaderboard:
        await update.message.reply_text("Пока нет данных для таблицы лидеров.")
        return
    period_text = f" за {period}" if period else " за всё время"
    text = f"🏆 **Топ-{limit}{period_text}:**\n"
    for i, (uid, first_name, username, total) in enumerate(leaderboard, 1):
        name = first_name or username or f"User{uid}"
        text += f"{i}. {name} — {total} баллов\n"
    await update.message.reply_text(text, parse_mode='Markdown')

# ========== ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ==========
def main():
    if not TOKEN:
        raise ValueError("Забыли TELEGRAM_BOT_TOKEN!")

    app = Application.builder().token(TOKEN).build()

    # --- Обычные команды ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CommandHandler("addexercise", add_exercise_command))
    app.add_handler(CommandHandler("delexercise", delete_exercise_command))
    app.add_handler(CommandHandler("listexercises", list_exercises_command))
    app.add_handler(CommandHandler("load_exercises", load_exercises_command))
    app.add_handler(CommandHandler("mystats", mystats_command))
    app.add_handler(CommandHandler("top", top_command))

    # --- ДИАЛОГ ТРЕНИРОВОК ---
    workout_conv = ConversationHandler(
        entry_points=[CommandHandler('wod', workout_start)],
        states={
            EXERCISE: [CallbackQueryHandler(exercise_choice, pattern='^ex_|^cancel$')],
            RESULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, result_input)],
            VIDEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, video_input)],
        },
        fallbacks=[CommandHandler('cancel', workout_cancel)],
    )
    app.add_handler(workout_conv)

    # --- Обработчики колбэков ---
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(sketch|anime|sepia|hardrock|pixel|neon|oil|watercolor|cartoon)$'))
    app.add_handler(CallbackQueryHandler(config_callback_handler, pattern="^toggle_"))

    # --- Обработчики сообщений ---
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Бот запущен...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Критическая ошибка в main: %s", e)
        raise
