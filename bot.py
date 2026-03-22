import os
import logging
import asyncio
import re
import json
import threading
import shlex
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque
from telegram import ReplyKeyboardMarkup, KeyboardButton
from urllib.parse import urlparse, parse_qs
from database import (
    init_db, add_user, get_exercises, add_workout, add_exercise,
    set_exercise_week, get_user_stats, get_leaderboard,
    get_all_exercises, delete_exercise,
    get_user_level, set_user_level,
    get_user_workouts, get_exercise_by_id,
    backup_database, recalculate_rankings,
    get_user_scoreboard_total, get_leaderboard_from_scoreboard,
    add_complex, add_complex_exercise, get_all_complexes, get_complex_by_id, get_complex_exercises
)

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

# === ИМПОРТЫ ДЛЯ ВОРКАУТ-ХЕНДЛЕРОВ ===
from workout_handlers import (
    workout_start, exercise_choice, result_input, video_input,
    workout_cancel, EXERCISE, RESULT, VIDEO, COMMENT,
    get_current_week, comment_input, comment_skip
)

# Состояния для диалога выполнения комплекса
COMPLEX_RESULT, COMPLEX_VIDEO, COMPLEX_COMMENT = range(10, 13)

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
        if self.path.startswith('/cron'):
            query = parse_qs(urlparse(self.path).query)
            key = query.get('key', [None])[0]
            secret = os.getenv("CRON_SECRET", "default_secret")
            if key == secret:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK - recalc check started")
                threading.Thread(target=self._check_and_recalc).start()
            else:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _check_and_recalc(self):
        from database import get_last_recalc, set_last_recalc, recalculate_rankings
        now = datetime.now()
        last = get_last_recalc()
        if last is None or (now - last).days >= 7:
            logger.info("Запускаю еженедельный пересчёт рейтинга по расписанию")
            recalculate_rankings(period_days=7)
            set_last_recalc(now)
            logger.info("Еженедельный пересчёт рейтинга завершён")
        else:
            logger.info("Еженедельный пересчёт рейтинга не требуется (прошло меньше 7 дней)")

# === ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
init_db()
logger.info("База данных готова к работе.")
backup_database()

# ========== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ КАТАЛОГА (КНОПОЧНАЯ) ==========
async def send_catalog_to_message(message):
    """Отправляет каталог упражнений с кнопками (красивая версия)."""
    current_week = get_current_week()
    exercises = get_all_exercises()
    if not exercises:
        await message.reply_text("Список упражнений пока пуст.")
        return

    permanent = []
    weekly = []
    for ex in exercises:
        if ex[4] == 0:  # week = 0
            permanent.append(ex)
        else:
            weekly.append(ex)

    text = "📋 **КАТАЛОГ УПРАЖНЕНИЙ**\n\n"
    keyboard = []

    if permanent:
        text += "♾️ **Доступны всегда**\n"
        for ex in permanent:
            name, points = ex[1], ex[3]
            icon = get_exercise_icon(name)
            text += f"• {icon} **{name}** – {points} баллов\n"
            keyboard.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"ex_{ex[0]}")])
        text += "\n"

    if weekly:
        text += "📅 **По неделям**\n"
        for ex in weekly:
            name, points, week = ex[1], ex[3], ex[4]
            icon = get_exercise_icon(name)
            if week == current_week:
                status = "✅ доступно сейчас"
            elif week < current_week:
                status = "⏳ прошлая неделя"
            else:
                status = f"🔜 будет на неделе {week}"
            text += f"• {icon} **{name}** – {points} баллов ({status})\n"
            keyboard.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"ex_{ex[0]}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

def get_exercise_icon(name):
    name_lower = name.lower()
    if "присед" in name_lower:
        return "🏋️‍♂️"
    elif "берпи" in name_lower or "бурпи" in name_lower:
        return "💥"
    elif "отжим" in name_lower:
        return "💪"
    elif "подтяг" in name_lower:
        return "🤸"
    elif "бег" in name_lower or "кросс" in name_lower:
        return "🏃"
    elif "тяга" in name_lower or "становая" in name_lower:
        return "🏋️"
    elif "складка" in name_lower or "пресс" in name_lower:
        return "🧘"
    elif "ходьба" in name_lower or "стойка" in name_lower:
        return "🚶"
    else:
        return "📌"

# ========== ОБРАБОТЧИК ДЛЯ ВЫБОРА УРОВНЯ ==========
async def setlevel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    level = query.data.split('_')[1]
    user_id = update.effective_user.id
    if set_user_level(user_id, level):
        await query.edit_message_text(f"✅ Уровень изменён на «{level}».")
    else:
        await query.edit_message_text("❌ Ошибка при смене уровня.")

# ========== ОБРАБОТЧИК ДЛЯ ВЫБОРА УПРАЖНЕНИЯ ИЗ КАТАЛОГА ==========
async def exercise_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ex_id = int(query.data.split('_')[1])
    ex = get_exercise_by_id(ex_id)
    if not ex:
        await query.edit_message_text("Упражнение не найдено.")
        return

    _, name, description, metric, points, week, difficulty = ex
    text = f"**{name}**\n"
    if description:
        text += f"{description}\n"
    text += f"🏅 Баллы: {points}\n"
    text += f"📏 Тип: {'повторения' if metric == 'reps' else 'время'}\n"
    text += f"🎯 Уровень: {'Новички' if difficulty == 'beginner' else 'Профи'}\n"
    if week != 0:
        text += f"🗓️ Активно: неделя {week}\n"

    keyboard = [[InlineKeyboardButton("✍️ Записать тренировку", callback_data=f"record_{ex_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def record_from_catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ex_id = int(query.data.split('_')[1])
    context.user_data['pending_exercise'] = ex_id
    await query.edit_message_text("Теперь отправь команду /wod, чтобы записать это упражнение.")

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🏋️ Спорт", "📸 Фото"],
        ["🤖 Задать вопрос", "❌ Отмена"],
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
    keyboard = [
        [InlineKeyboardButton("🏋️ Спорт", callback_data='help_sport')],
        [InlineKeyboardButton("📸 Фото", callback_data='help_photo')],
        [InlineKeyboardButton("📊 Статистика", callback_data='help_stats')],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data='help_top')],
    ]
    if is_admin(update):
        keyboard.append([InlineKeyboardButton("⚙️ Админ", callback_data='help_admin')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 **Помощь**\nВыбери раздел, чтобы узнать подробнее:",
        parse_mode='Markdown', reply_markup=reply_markup
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'help_sport':
        text = "🏋️ **Спорт**\n"
        text += "/wod — записать тренировку\n"
        text += "/catalog — каталог упражнений\n"
        text += "/mystats — моя статистика\n"
        text += "/setlevel — сменить уровень (новичок/профи)"
    elif data == 'help_photo':
        text = "📸 **Фото**\n"
        text += "/menu — выбрать стиль и отправить фото.\n"
        text += "Доступны стили: карандаш, аниме, сепия, хард-рок, пиксель, неон, масло, акварель, мультяшный."
    elif data == 'help_stats':
        text = "📊 **Статистика**\n"
        text += "/mystats [day|week|month|year] — твоя статистика\n"
        text += "/top [day|week|month|year] [beginner|pro] — таблица лидеров"
    elif data == 'help_top':
        text = "🏆 **Рейтинг**\n"
        text += "/top — топ за всё время в твоей лиге\n"
        text += "Можно добавить период (day, week, month, year) и лигу (beginner, pro)."
    elif data == 'help_admin':
        text = "⚙️ **Админ**\n"
        text += "/config — настройка AI\n"
        text += "/addexercise — добавить упражнение\n"
        text += "/delexercise — удалить упражнение\n"
        text += "/listexercises — список упражнений\n"
        text += "/load_exercises — загрузить из JSON"
    else:
        text = "Информация не найдена."
    await query.edit_message_text(text, parse_mode='Markdown')

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

# ========== СПОРТИВНОЕ МЕНЮ И КОЛБЭКИ ==========
async def sport_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    data = query.data
    try:
        if data == 'sport_catalog':
            await send_catalog_to_message(query.message)
        elif data == 'sport_wod':
            await query.message.reply_text("Отправь команду /wod, чтобы записать тренировку.")
        elif data == 'sport_mystats':
            await mystats_command(query.message, context)
        elif data == 'sport_setlevel':
            keyboard = [
                [InlineKeyboardButton("Новичок (beginner)", callback_data="setlevel_beginner")],
                [InlineKeyboardButton("Профи (pro)", callback_data="setlevel_pro")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Выбери уровень:", reply_markup=reply_markup)
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
    text = update.message.text
    if "Спорт" in text:
        await sport_menu(update, context)
    elif "Фото" in text:
        await show_menu(update, context)
    elif "Отмена" in text:
        context.user_data.clear()
        await update.message.reply_text("Все активные действия отменены. Можете начать заново.")
    elif "Задать вопрос" in text:
        await update.message.reply_text("Напиши свой вопрос — я отвечу.")
    elif "Рейтинг" in text:
        await top_command(update, context)
    elif "Админ" in text:
        if is_admin(update):
            await update.message.reply_text("Админ-панель:\n/config — настройки AI\n/addexercise — добавить упражнение\n/listexercises — список упражнений\n/load_exercises — загрузить из JSON")
        else:
            await update.message.reply_text("⛔ У вас нет прав на это.")
    else:
        await handle_message(update, context)

# ========== КАТАЛОГ УПРАЖНЕНИЙ ==========
async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_catalog_to_message(update.message)

async def myhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        wid, name, result, video, date, is_best, typ, comment = w
        date_str = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
        best_mark = " 🏆" if is_best else ""
        line = f"• {date_str} — **{name}** ({typ}): {result} [ссылка]({video}){best_mark}"
        if comment:
            line += f"\n   💬 {comment}"
        text += line + "\n"
        if len(text) > 3500:
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
        await update.message.reply_text("Использование: /addexercise <название> <reps|time> <описание> <баллы> [неделя] [difficulty]")
        return
    args_part = full_text.split(maxsplit=1)[1]
    try:
        args = shlex.split(args_part)
        if len(args) < 4:
            await update.message.reply_text("❌ Нужно минимум 4 аргумента.")
            return
        name, metric, desc, points = args[0], args[1], args[2], int(args[3])
        week = int(args[4]) if len(args) > 4 and args[4].isdigit() else 0
        diff = args[5] if len(args) > 5 else 'beginner'
        if add_exercise(name, desc, metric, points, week, diff):
            await update.message.reply_text(f"✅ Упражнение '{name}' добавлено.")
        else:
            await update.message.reply_text("❌ Ошибка добавления.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсинга: {e}")

async def delete_exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not context.args: return
    if delete_exercise(int(context.args[0])):
        await update.message.reply_text("✅ Удалено.")
    else:
        await update.message.reply_text("❌ Не найдено.")

async def list_exercises_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    exercises = get_all_exercises()
    text = "📋 **Список упражнений:**\n\n"
    for ex in exercises:
        text += f"🔹 ID: {ex[0]} — {ex[1]} ({ex[5]})\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def load_exercises_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    try:
        with open('exercises.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for ex in data:
                add_exercise(ex['name'], ex.get('description',''), ex['metric'], ex['points'], ex.get('week',0), ex.get('difficulty','beginner'))
        await update.message.reply_text("✅ Загружено.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def recalc_rankings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    await update.message.reply_text("⏳ Начинаю пересчёт рейтинга...")
    recalculate_rankings(period_days=7)
    await update.message.reply_text("✅ Рейтинг пересчитан. Баллы начислены.")

async def setlevel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args and context.args[0] in ('beginner', 'pro'):
        if set_user_level(user_id, context.args[0]):
            await update.message.reply_text(f"✅ Уровень изменён на {context.args[0]}.")
        else:
            await update.message.reply_text("❌ Ошибка при смене уровня.")
    else:
        keyboard = [
            [InlineKeyboardButton("Новичок (beginner)", callback_data="setlevel_beginner")],
            [InlineKeyboardButton("Профи (pro)", callback_data="setlevel_pro")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выбери уровень:", reply_markup=reply_markup)

# ========== СТАТИСТИКА И РЕЙТИНГ ==========
async def mystats_command(message, context: ContextTypes.DEFAULT_TYPE):
    user_id = message.chat.id
    total = get_user_scoreboard_total(user_id)
    workouts = get_user_workouts(user_id, limit=1000)
    workout_count = len(workouts)
    target = 100
    bar_len = int(20 * total / target) if target > 0 else 0
    bar = "▰" * bar_len + "▱" * (20 - bar_len)
    text = f"🏆 **Твоя статистика**\n\n"
    text += f"🏋️ Тренировок: {workout_count}\n"
    text += f"⭐ Баллов: {total}\n"
    text += f"📈 Прогресс до следующего уровня: {bar} {total}/{target}"
    await message.reply_text(text, parse_mode='Markdown')

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaderboard = get_leaderboard_from_scoreboard()
    if not leaderboard:
        await update.message.reply_text("Нет данных.")
        return

    max_points = leaderboard[0][3] if leaderboard else 1
    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, fname, uname, total) in enumerate(leaderboard[:10], 1):
        name = fname or uname or f"User{uid}"
        if i <= 3:
            medal = medals[i-1]
        else:
            medal = f"{i}."
        bar_len = int(20 * total / max_points) if max_points > 0 else 0
        bar = "▰" * bar_len + "▱" * (20 - bar_len)
        text += f"{medal} **{name}** — {total} баллов\n   {bar} {total}\n\n"
    await update.message.reply_text(text, parse_mode='Markdown')

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def stats_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"DEBUG: stats_period_callback вызван с data = {query.data}")
    period = query.data.split('_')[1] if query.data != 'stats_all' else None
    user_id = update.effective_user.id
    pts, wods = get_user_stats(user_id, period)
    period_text = f" за {period}" if period else " за всё время"
    await query.message.reply_text(f"📊 Твоя статистика{period_text}:\n🏋️ Тренировок: {wods or 0}\n⭐ Баллов: {pts or 0}")

async def top_league_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    league = query.data.split('_')[1]
    user_id = update.effective_user.id
    leaderboard = get_leaderboard(None, league)
    if not leaderboard:
        await query.message.reply_text("Нет данных.")
        return
    text = f"🏆 **Топ игроков ({'Новички' if league == 'beginner' else 'Профи'}):**\n"
    for i, (uid, fname, uname, total) in enumerate(leaderboard, 1):
        text += f"{i}. {fname or uname} — {total}\n"
    await query.message.reply_text(text, parse_mode='Markdown')

# ========== КОМАНДЫ ДЛЯ КОМПЛЕКСОВ ==========
async def add_complex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    try:
        text = update.message.text.split(maxsplit=1)[1]
        args = shlex.split(text)
        if len(args) < 4:
            await update.message.reply_text("Использование: /addcomplex <название> <описание> <тип> <баллы>\nТип: for_time или for_reps")
            return
        name, description, type_, points = args[0], args[1], args[2], int(args[3])
        if type_ not in ('for_time', 'for_reps'):
            await update.message.reply_text("Тип должен быть for_time или for_reps")
            return
        complex_id = add_complex(name, description, type_, points)
        await update.message.reply_text(f"✅ Комплекс «{name}» создан с ID {complex_id}.\nТеперь добавь упражнения командой /addcomplexexercise {complex_id} <id_упражнения> <повторения>")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def add_complex_exercise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Нет прав.")
        return
    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text("Использование: /addcomplexexercise <complex_id> <exercise_id> <reps>")
            return
        complex_id = int(args[0])
        exercise_id = int(args[1])
        reps = int(args[2])
        complex_data = get_complex_by_id(complex_id)
        if not complex_data:
            await update.message.reply_text("Комплекс не найден.")
            return
        ex = get_exercise_by_id(exercise_id)
        if not ex:
            await update.message.reply_text("Упражнение не найдено.")
            return
        add_complex_exercise(complex_id, exercise_id, reps)
        await update.message.reply_text(f"✅ Упражнение «{ex[1]}» добавлено в комплекс {complex_data[1]} с {reps} повторениями.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def complexes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    complexes = get_all_complexes()
    if not complexes:
        await update.message.reply_text("Комплексов пока нет.")
        return
    text = "🏋️ **Доступные комплексы:**\n\n"
    for c in complexes:
        text += f"ID: {c[0]} — **{c[1]}**\n"
        text += f"   Тип: {'Время' if c[3] == 'for_time' else 'Повторения'}\n"
        text += f"   Баллы: {c[4]}\n\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def complex_detail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        complex_id = int(context.args[0])
    except:
        await update.message.reply_text("Использование: /complex <id>")
        return
    complex_data = get_complex_by_id(complex_id)
    if not complex_data:
        await update.message.reply_text("Комплекс не найден.")
        return
    exercises = get_complex_exercises(complex_id)
    if not exercises:
        await update.message.reply_text("В комплексе нет упражнений.")
        return
    text = f"**{complex_data[1]}**\n{complex_data[2]}\n\n"
    text += f"Тип: {'Время' if complex_data[3] == 'for_time' else 'Повторения'}\n"
    text += f"Баллы: {complex_data[4]}\n\n"
    text += "**Упражнения:**\n"
    for ex in exercises:
        text += f"• {ex[3]} — {ex[4]} повторений\n"
    keyboard = [[InlineKeyboardButton("✅ Выполнить комплекс", callback_data=f"do_complex_{complex_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

# ========== ДИАЛОГ ВЫПОЛНЕНИЯ КОМПЛЕКСА ==========
async def do_complex_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    complex_id = int(query.data.split('_')[2])
    context.user_data['current_complex_id'] = complex_id
    complex_data = get_complex_by_id(complex_id)
    if not complex_data:
        await query.edit_message_text("Комплекс не найден.")
        return ConversationHandler.END
    context.user_data['complex_name'] = complex_data[1]
    context.user_data['complex_points'] = complex_data[4]
    await query.edit_message_text(f"Выполняем комплекс **{complex_data[1]}**.\nВведите результат:\n- Если тип 'время', укажи в формате ММ:СС (например, 03:45)\n- Если тип 'повторения', введи количество.")
    return COMPLEX_RESULT

async def complex_result_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result_text = update.message.text.strip()
    complex_id = context.user_data['current_complex_id']
    complex_data = get_complex_by_id(complex_id)
    complex_type = complex_data[3]
    if complex_type == 'for_time':
        try:
            parts = result_text.split(':')
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                total_seconds = minutes * 60 + seconds
                context.user_data['complex_result_value'] = result_text
                context.user_data['complex_result_seconds'] = total_seconds
            else:
                raise ValueError
        except:
            await update.message.reply_text("Неверный формат. Используй ММ:СС, например 05:30")
            return COMPLEX_RESULT
    else:
        try:
            reps = int(result_text)
            context.user_data['complex_result_value'] = str(reps)
            context.user_data['complex_result_reps'] = reps
        except:
            await update.message.reply_text("Введи целое число повторений.")
            return COMPLEX_RESULT
    await update.message.reply_text("Отлично! Теперь отправь ссылку на видео (YouTube, Vimeo, или любой URL) подтверждения выполнения.\nИли нажми /skip, чтобы пропустить.")
    return COMPLEX_VIDEO

async def complex_video_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_url = update.message.text.strip()
    context.user_data['complex_video'] = video_url
    await update.message.reply_text("Можешь добавить комментарий к тренировке (необязательно).\nИли нажми /skip, чтобы пропустить.")
    return COMPLEX_COMMENT

async def complex_comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip()
    context.user_data['complex_comment'] = comment
    await save_complex_workout(update, context)
    return ConversationHandler.END

async def complex_comment_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['complex_comment'] = None
    await save_complex_workout(update, context)
    return ConversationHandler.END

async def save_complex_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    complex_id = context.user_data['current_complex_id']
    complex_name = context.user_data['complex_name']
    points = context.user_data['complex_points']
    result = context.user_data['complex_result_value']
    video = context.user_data.get('complex_video', '')
    comment = context.user_data.get('complex_comment')
    user_level = get_user_level(user_id)

    # Сохраняем тренировку (передаём complex_id, exercise_id = None)
    add_workout(user_id, exercise_id=None, complex_id=complex_id, result_value=result, video_link=video, user_level=user_level, comment=comment)
    await update.message.reply_text(f"✅ Тренировка «{complex_name}» засчитана! +{points} баллов.")
    # Очистка
    for key in ['current_complex_id', 'complex_name', 'complex_points', 'complex_result_value', 'complex_result_seconds', 'complex_result_reps', 'complex_video', 'complex_comment']:
        context.user_data.pop(key, None)

# ========== ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ==========
def main():
    logger.info("MAIN: started")
    if not TOKEN:
        raise ValueError("Забыли TELEGRAM_BOT_TOKEN!")

    # --- Запуск HTTP-сервера в фоне ---
    def start_http():
        port = int(os.environ.get('PORT', 10000))
        httpd = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"✅ HTTP сервер запущен на порту {port}")
        httpd.serve_forever()

    http_thread = threading.Thread(target=start_http, daemon=True)
    http_thread.start()

    # --- Инициализация бота ---
    app = Application.builder().token(TOKEN).build()

    # --- Команды ---
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
    app.add_handler(CommandHandler("mystats", lambda u,c: mystats_command(u.message, c)))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("setlevel", setlevel_command))
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("myhistory", myhistory_command))
    app.add_handler(CommandHandler("recalc_rankings", recalc_rankings_command))
    app.add_handler(CommandHandler("addcomplex", add_complex_command))
    app.add_handler(CommandHandler("addcomplexexercise", add_complex_exercise_command))
    app.add_handler(CommandHandler("complexes", complexes_command))
    app.add_handler(CommandHandler("complex", complex_detail_command))

    # --- Диалог выполнения комплекса ---
    complex_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(do_complex_start, pattern='^do_complex_\\d+$')],
        states={
            COMPLEX_RESULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, complex_result_input)],
            COMPLEX_VIDEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, complex_video_input),
                            CommandHandler('skip', complex_comment_skip)],
            COMPLEX_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, complex_comment_input),
                              CommandHandler('skip', complex_comment_skip)],
        },
        fallbacks=[CommandHandler('cancel', workout_cancel)],
    )
    app.add_handler(complex_conv)

    # --- Диалог тренировок ---
    workout_conv = ConversationHandler(
        entry_points=[CommandHandler('wod', workout_start)],
        states={
            EXERCISE: [CallbackQueryHandler(exercise_choice, pattern='^ex_|^cancel$')],
            RESULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, result_input)],
            VIDEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, video_input)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, comment_input),
                      CommandHandler('skip', comment_skip)],
        },
        fallbacks=[CommandHandler('cancel', workout_cancel)],
    )
    app.add_handler(workout_conv)

    # --- Колбэки ---
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(sketch|anime|sepia|hardrock|pixel|neon|oil|watercolor|cartoon)$'))
    app.add_handler(CallbackQueryHandler(config_callback_handler, pattern="^toggle_"))
    # app.add_handler(CallbackQueryHandler(stats_period_callback, pattern='^stats_'))
    app.add_handler(CallbackQueryHandler(setlevel_callback, pattern='^setlevel_'))
    app.add_handler(CallbackQueryHandler(sport_callback_handler, pattern='^sport_|^back_to_main$'))
    app.add_handler(CallbackQueryHandler(help_callback, pattern='^help_'))
    app.add_handler(CallbackQueryHandler(exercise_callback, pattern='^ex_'))
    app.add_handler(CallbackQueryHandler(record_from_catalog_callback, pattern='^record_'))

    # --- Сообщения ---
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Критическая ошибка: %s", e)
