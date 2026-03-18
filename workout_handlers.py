import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import add_user, get_exercises, add_workout
import re

logger = logging.getLogger(__name__)

# Состояния диалога (импортируем из bot.py или продублируем)
EXERCISE, RESULT, VIDEO = range(3)

# Временное хранилище для данных в рамках одного диалога
# можно хранить в context.user_data, поэтому отдельный словарь не нужен.

async def workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога: показывает список доступных упражнений."""
    # Сохраняем пользователя в базу
    user = update.effective_user
    add_user(user.id, user.first_name, user.last_name, user.username)

    exercises = get_exercises(active_only=True)
    if not exercises:
        await update.message.reply_text("❌ Сейчас нет активных упражнений. Попробуй позже.")
        return ConversationHandler.END

    # Создаём клавиатуру с упражнениями
    keyboard = []
    for ex_id, name, metric in exercises:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"ex_{ex_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏋️ Выбери упражнение, которое выполнил:", reply_markup=reply_markup)
    return EXERCISE

async def exercise_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор упражнения."""
    query = update.callback_query
    await query.answer()
    ex_id = int(query.data.split("_")[1])

    # Сохраняем выбранное упражнение в context.user_data
    context.user_data['exercise_id'] = ex_id

    # Получаем информацию об упражнении, чтобы понять тип (повторения или время)
    exercises = get_exercises(active_only=True)
    ex_metric = None
    for ex in exercises:
        if ex[0] == ex_id:
            ex_metric = ex[2]
            break

    context.user_data['metric'] = ex_metric

    if ex_metric == 'reps':
        prompt = "🔢 Введи количество повторений (только число):"
    else:
        prompt = "⏱️ Введи время в формате ММ:СС (например, 05:30):"

    await query.edit_message_text(prompt)
    return RESULT

async def result_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает результат (повторения или время)."""
    text = update.message.text.strip()
    metric = context.user_data.get('metric')

    if metric == 'reps':
        # Проверяем, что это число
        if not text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введи число (количество повторений).")
            return RESULT
        context.user_data['result_value'] = text
    else:
        # Проверяем формат времени ММ:СС (простейшая проверка)
        if not re.match(r'^\d{1,2}:\d{2}$', text):
            await update.message.reply_text("❌ Неправильный формат. Введи время как ММ:СС (например, 05:30).")
            return RESULT
        context.user_data['result_value'] = text

    await update.message.reply_text("📎 Теперь отправь ссылку на видео с выполнением (Google Drive, YouTube и т.п.)")
    return VIDEO

async def video_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает ссылку на видео и сохраняет результат."""
    video_link = update.message.text.strip()
    # Простейшая проверка, что похоже на ссылку
    if not video_link.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Это не похоже на ссылку. Попробуй ещё раз (должно начинаться с http:// или https://)")
        return VIDEO

    # Всё ок, сохраняем
    user_id = update.effective_user.id
    exercise_id = context.user_data['exercise_id']
    result_value = context.user_data['result_value']

    add_workout(user_id, exercise_id, result_value, video_link)

    await update.message.reply_text(
        "✅ Тренировка успешно записана! Спасибо за честность.\n"
        "Можешь посмотреть результаты командой /stats (скоро добавим)."
    )

    # Очищаем временные данные и завершаем диалог
    context.user_data.clear()
    return ConversationHandler.END

async def workout_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога."""
    await update.message.reply_text("❌ Запись тренировки отменена.")
    context.user_data.clear()
    return ConversationHandler.END
