import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import add_user, get_exercises, add_workout

logger = logging.getLogger(__name__)

EXERCISE, RESULT, VIDEO = range(3)

async def workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.first_name, user.last_name, user.username)

    exercises = get_exercises(active_only=True)
    if not exercises:
        await update.message.reply_text("❌ Сейчас нет активных упражнений. Попробуй позже.")
        return ConversationHandler.END

    keyboard = []
    for ex_id, name, metric in exercises:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"ex_{ex_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏋️ Выбери упражнение, которое выполнил:", reply_markup=reply_markup)
    return EXERCISE

async def exercise_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ex_id = int(query.data.split("_")[1])
    context.user_data['exercise_id'] = ex_id

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
    text = update.message.text.strip()
    metric = context.user_data.get('metric')

    if metric == 'reps':
        if not text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введи число (количество повторений).")
            return RESULT
        context.user_data['result_value'] = text
    else:
        if not re.match(r'^\d{1,2}:\d{2}$', text):
            await update.message.reply_text("❌ Неправильный формат. Введи время как ММ:СС (например, 05:30).")
            return RESULT
        context.user_data['result_value'] = text

    await update.message.reply_text("📎 Теперь отправь ссылку на видео с выполнением (Google Drive, YouTube и т.п.)")
    return VIDEO

async def video_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_link = update.message.text.strip()
    if not video_link.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Это не похоже на ссылку. Попробуй ещё раз (должно начинаться с http:// или https://)")
        return VIDEO

    user_id = update.effective_user.id
    exercise_id = context.user_data['exercise_id']
    result_value = context.user_data['result_value']

    add_workout(user_id, exercise_id, result_value, video_link)

    await update.message.reply_text(
        "✅ Тренировка успешно записана! Спасибо за честность.\n"
        "Можешь посмотреть результаты командой /stats (скоро добавим)."
    )

    context.user_data.clear()
    return ConversationHandler.END

async def workout_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Запись тренировки отменена.")
    context.user_data.clear()
    return ConversationHandler.END
