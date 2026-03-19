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
from telegram import ReplyKeyboardMarkup, KeyboardButton

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
    get_all_exercises, delete_exercise,
    get_user_level, set_user_level,
    get_user_workouts
)
from workout_handlers import (
    workout_start, exercise_choice, result_input, video_input,
    workout_cancel, EXERCISE, RESULT, VIDEO, get_current_week  # добавили get_current_week
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
    """Главное меню с кнопками."""
    # Создаём клавиатуру
    keyboard = [
        ["🏋️ Спорт", "📸 Фото"],
        ["🤖 Задать вопрос", "📊 Моя статистика"],
        ["🏆 Рейтинг", "⚙️ Админ"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🔥 Привет! Я твой фитнес-помощник и AI-консилиум.\n"
        "Выбери, что хочешь сделать:",
        reply_markup=reply_markup
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
        "🔹 `/catalog` - Каталог упражнений\n"
        "🔹 `/mystats [day|week|month|year]` - Моя статистика\n"
        "🔹 `/top [day|week|month|year] [beginner|pro]` - Таблица лидеров\n"
        "🔹 `/setlevel <beginner|pro>` - Сменить уровень\n"
        "🔹 `/listexercises` - Список упражнений (админ)\n"
        "🔹 `/delexercise <id>` - Удалить упражнение (админ)\n"
        "🔹 `/addexercise` - Добавить упражнение (админ)\n"
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

async def sport_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DEBUG: sport_menu opened")  # отладку потом уберёшь
    keyboard = [
        [InlineKeyboardButton("📋 Каталог упражнений", callback_data='sport_catalog')],
        [InlineKeyboardButton("✍️ Записать тренировку", callback_data='sport_wod')],
        [InlineKeyboardButton("📊 Моя статистика", callback_data='sport_mystats')],
        [InlineKeyboardButton("🔄 Сменить уровень", callback_data='sport_setlevel')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏋️ Раздел «Спорт». Выбери действие:",
        reply_markup=reply_markup
    )

async def sport_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("DEBUG: callback received")
    data = query.data
    logger.info(f"sport_callback_handler called with data = {data}")  # лог вместо print

    try:
        if data == 'sport_catalog':
            await query.message.reply_text("Вот каталог упражнений (используй команду /catalog):")
        elif data == 'sport_wod':
            await query.message.reply_text("Отправь команду /wod, чтобы записать тренировку.")
        elif data == 'sport_mystats':
            await query.message.reply_text("Твоя статистика (используй команду /mystats):")
        elif data == 'sport_setlevel':
            await query.message.reply_text("Чтобы сменить уровень, используй /setlevel beginner или /setlevel pro.")
        elif data == 'back_to_main':
            keyboard = [
                ["🏋️ Спорт", "📸 Фото"],
                ["🤖 Задать вопрос", "📊 Моя статистика"],
                ["🏆 Рейтинг", "⚙️ Админ"],
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await query.message.reply_text("Главное меню:", reply_markup=reply_markup)
            await query.message.delete()
    except Exception as e:
        logger.exception(f"Ошибка в sport_callback_handler: {e}")
        await query.message.reply_text("❌ Произошла ошибка. Попробуй позже.")

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки главного меню."""
    text = update.message.text
    if text == "🏋️ Спорт":
        await sport_menu(update, context)
    elif text == "📸 Фото":
        await show_menu(update, context)  # или send photo instructions
    elif text == "🤖 Задать вопрос":
        await update.message.reply_text("Напиши свой вопрос — я отвечу.")
    elif text == "📊 Моя статистика":
        await mystats_command(update, context)
    elif text == "🏆 Рейтинг":
        await top_command(update, context)
    elif text == "⚙️ Админ":
        if is_admin(update):
            await update.message.reply_text("Админ-панель:\n/config — настройки AI\n/addexercise — добавить упражнение\n/listexercises — список упражнений\n/load_exercises — загрузить из JSON")
        else:
            await update.message.reply_text("⛔ У вас нет прав на это.")
    else:
        # Если не кнопка, передаём в обычный обработчик сообщений
        await handle_message(update, context)

# ========== КАТАЛОГ УПРАЖНЕНИЙ (НОВОЕ) ==========
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает каталог упражнений с пометками о доступности."""
    user_id = update.effective_user.id
    current_week = get_current_week()
    exercises = get_all_exercises()  # получаем все упражнения с деталями

    if not exercises:
        await update.message.reply_text("Список упражнений пока пуст.")
        return

    permanent = []
    weekly = []
    for ex in exercises:
        if ex[4] == 0:  # week = 0
            permanent.append(ex)
        else:
            weekly.append(ex)

    text = "📋 **Каталог упражнений**\n\n"
    if permanent:
        text += "♾️ **Доступны всегда:**\n"
        for ex in permanent:
            name, metric, points, difficulty = ex[1], ex[2], ex[3], ex[5]
            metric_icon = "🔢" if metric == 'reps' else "⏱️"
            text += f"{metric_icon} {name} — {points} баллов, уровень: {difficulty}\n"
        text += "\n"

    if weekly:
        text += "📅 **По неделям:**\n"
        for ex in weekly:
            name, metric, points, week, difficulty = ex[1], ex[2], ex[3], ex[4], ex[5]
            metric_icon = "🔢" if metric == 'reps' else "⏱️"
            if week == current_week:
                status = "✅ доступно сейчас"
            elif week < current_week:
                status = "⏳ прошлая неделя"
            else:
                status = f"🔜 будет на неделе {week}"
            text += f"{metric_icon} {name} — {points} баллов, уровень: {difficulty} ({status})\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def myhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние тренировки пользователя."""
    user_id = update.effective_user.id
    limit = 20
    if context.args and context.args[0].isdigit():
        limit = int(context.args[0])
        if limit > 50:
            limit = 50

    workouts = get_user_workouts(user_id, limit)
    if not workouts:
        await update.message.reply_text("У тебя пока нет записанных тренировок.")
        return

    text = f"📋 **Твои последние {len(workouts)} тренировок:**\n\n"
    for w in workouts:
        wid, name, result, video, date, is_best, typ = w
        date_str = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
        best_mark = " 🏆" if is_best else ""
        text += f"• {date_str} — **{name}** ({typ}): {result} [ссылка]({video}){best_mark}\n"
        if len(text) > 3500:  # Telegram лимит 4096, оставим запас
            text += "\n...и ещё"
            break

    await update.message.reply_text(text, parse_mode='Markdown', disable_web_page_preview=True)

# ========== АДМИН-КОМАНДЫ ДЛЯ УПРАЖНЕНИЙ ==========
async def add_exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return

    full_text = update.message.text
    if ' ' not in full_text:
        await update.message.reply_text(
            "Использование: /addexercise <название> <reps|time> <описание> <баллы> [неделя] [difficulty]\n"
            "difficulty: beginner или pro (по умолчанию beginner)\n"
            "Пример: /addexercise \"Берпочки 50 штук\" reps \"Берпочки любимые\" 10 15 pro"
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
        if len(args) == 4:
            points = int(args[3])
            week = 0
            difficulty = 'beginner'
            description = " ".join(args[2:3])
        elif len(args) == 5:
            if args[4].isdigit():
                week = int(args[4])
                points = int(args[3])
                difficulty = 'beginner'
                description = " ".join(args[2:3])
            else:
                if args[4] not in ('beginner', 'pro'):
                    await update.message.reply_text("❌ Уровень сложности должен быть 'beginner' или 'pro'.")
                    return
                week = 0
                points = int(args[3])
                difficulty = args[4]
                description = " ".join(args[2:3])
        elif len(args) == 6:
            points = int(args[3])
            week = int(args[4])
            difficulty = args[5]
            if difficulty not in ('beginner', 'pro'):
                await update.message.reply_text("❌ Уровень сложности должен быть 'beginner' или 'pro'.")
                return
            description = " ".join(args[2:3])
        else:
            await update.message.reply_text("❌ Неправильное количество аргументов.")
            return
    except ValueError:
        await update.message.reply_text("❌ Баллы и неделя должны быть числами.")
        return

    if add_exercise(name, description, metric, points, week, difficulty):
        week_text = f", неделя: {week}" if week != 0 else ""
        await update.message.reply_text(f"✅ Упражнение '{name}' добавлено (баллы: {points}{week_text}, уровень: {difficulty}).")
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
        ex_id, name, metric, points, week, difficulty = ex
        week_text = f" (неделя {week})" if week != 0 else ""
        text += f"🔹 ID: {ex_id} — {name} — {points} баллов, уровень: {difficulty}{week_text}\n"
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
        name = ex.get('name')
        metric = ex.get('metric')
        description = ex.get('description', '')
        points = ex.get('points', 0)
        week = ex.get('week', 0)
        difficulty = ex.get('difficulty', 'beginner')
        if add_exercise(name, description, metric, points, week, difficulty):
            added += 1
        else:
            skipped += 1
    await update.message.reply_text(f"✅ Загружено: {added} упражнений, пропущено (уже есть): {skipped}.")

# ========== КОМАНДЫ ДЛЯ РАБОТЫ С УРОВНЕМ ПОЛЬЗОВАТЕЛЯ ==========
async def setlevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1 or context.args[0] not in ('beginner', 'pro'):
        await update.message.reply_text(
            "❌ Использование: /setlevel beginner  или  /setlevel pro\n"
            "Предупреждение: при смене уровня твой счёт в новой лиге начнётся с нуля, "
            "но общий счёт сохранится."
        )
        return
    new_level = context.args[0]
    if set_user_level(user_id, new_level):
        await update.message.reply_text(f"✅ Твой уровень изменён на «{new_level}». Теперь твои тренировки будут учитываться в этой лиге.")
    else:
        await update.message.reply_text("❌ Ошибка при смене уровня.")

# ========== СТАТИСТИКА ==========
async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    period = context.args[0] if context.args else None
    if period and period not in ('day', 'week', 'month', 'year'):
        await update.message.reply_text("❌ Неверный период. Используй: day, week, month, year")
        return

    total_points, total_workouts = get_user_stats(user_id, period, level=None)
    level_points, level_workouts = get_user_stats(user_id, period, level=get_user_level(user_id))

    period_text = f" за {period}" if period else " за всё время"
    text = f"📊 **Твоя статистика{period_text}:**\n"
    text += f"🏋️ Всего тренировок: {total_workouts or 0}\n"
    text += f"⭐ Всего баллов: {total_points or 0}\n\n"
    text += f"**В текущей лиге:**\n"
    text += f"🏋️ Тренировок: {level_workouts or 0}\n"
    text += f"⭐ Баллов: {level_points or 0}"
    await update.message.reply_text(text, parse_mode='Markdown')

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    period = None
    level = get_user_level(update.effective_user.id)

    for arg in args:
        if arg in ('day', 'week', 'month', 'year'):
            period = arg
        elif arg in ('beginner', 'pro'):
            level = arg

    limit = 10
    leaderboard = get_leaderboard(period, level, limit)
    if not leaderboard:
        await update.message.reply_text("Пока нет данных для таблицы лидеров.")
        return

    period_text = f" за {period}" if period else " за всё время"
    level_text = "Новички" if level == 'beginner' else "Профи"
    text = f"🏆 **Топ-{limit} {level_text}{period_text}:**\n"
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
    app.add_handler(CommandHandler("setlevel", setlevel_command))
    app.add_handler(CommandHandler("catalog", catalog_command))  # новая команда
    app.add_handler(CommandHandler("myhistory", myhistory_command))

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

async def log_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Callback received: {update.callback_query.data}")
    # Не отправляем сообщение, просто логируем

app.add_handler(CallbackQueryHandler(log_all_callbacks))

    # --- Обработчики колбэков ---
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(sketch|anime|sepia|hardrock|pixel|neon|oil|watercolor|cartoon)$'))
    app.add_handler(CallbackQueryHandler(config_callback_handler, pattern="^toggle_"))
    app.add_handler(CallbackQueryHandler(sport_callback_handler, pattern='^(sport_|back_to_main)$'))

    # --- Обработчики сообщений ---
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))  # ← сначала проверяем меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))  # потом всё остальное
    
    logger.info("🚀 Бот запущен...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Критическая ошибка в main: %s", e)
        raise
