import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import add_user, get_exercises, add_workout, get_user_level, get_exercise_by_id

logger = logging.getLogger(__name__)

EXERCISE, RESULT, VIDEO, COMMENT = range(4)  # добавили состояние COMMENT

def get_current_week():
    from datetime import datetime
    return datetime.now().isocalendar()[1]

async def workout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.first_name, user.last_name, user.username, get_user_level(user.id))

    # Если есть предварительно выбранное упражнение (из каталога)
    if 'pending_exercise' in context.user_data:
        ex_id = context.user_data.pop('pending_exercise')
        ex = get_exercise_by_id(ex_id)
        if ex:
            context.user_data['exercise_id'] = ex_id
            metric = ex[3]
            context.user_data['metric'] = metric
            if metric == 'reps':
                await update.message.reply_text("🔢 Введи количество повторений (только число):")
            else:
                await update.message.reply_text("⏱️ Введи время в формате ММ:СС (например, 05:30):")
            return RESULT
        # если не нашлось, идём по обычному пути

    current_week = get_current_week()
    exercises = get_exercises(active_only=True, week=current_week, difficulty=get_user_level(user.id))
    if not exercises:
        await update.message.reply_text("❌ На этой неделе нет активных упражнений. Загляни позже!")
        return ConversationHandler.END

    keyboard = []
    for ex in exercises:
        ex_id, name, metric, points, week, difficulty = ex
        btn_text = f"{name} ({points} баллов)" if points else name
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"ex_{ex_id}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏋️ Выбери упражнение, которое выполнил:", reply_markup=reply_markup)
    return EXERCISE

async def exercise_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("❌ Запись тренировки отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    ex_id = int(query.data.split("_")[1])
    context.user_data['exercise_id'] = ex_id

    exercises = get_exercises(active_only=True, week=get_current_week(), difficulty=get_user_level(update.effective_user.id))
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

    context.user_data['video_link'] = video_link
    await update.message.reply_text("💬 Добавь комментарий к тренировке (можно пропустить, нажми /skip или просто отправь сообщение):")
    return COMMENT

async def comment_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    exercise_id = context.user_data['exercise_id']
    result_value = context.user_data['result_value']
    video_link = context.user_data['video_link']
    user_level = get_user_level(user_id)
    metric = context.user_data.get('metric')
    add_workout(user_id, exercise_id, result_value, video_link, user_level, None, metric)
    await update.message.reply_text(
        "✅ Тренировка успешно записана! Спасибо за честность.\n"
        "Можешь посмотреть свои результаты командой /mystats, а таблицу лидеров — /top."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text
    if comment == '/skip':
        comment = None

    user_id = update.effective_user.id
    exercise_id = context.user_data['exercise_id']
    result_value = context.user_data['result_value']
    video_link = context.user_data['video_link']
    user_level = get_user_level(user_id)
    metric = context.user_data.get('metric')

    add_workout(user_id, exercise_id, result_value, video_link, user_level, comment, metric)

    await update.message.reply_text(
        "✅ Тренировка успешно записана! Спасибо за честность.\n"
        "Можешь посмотреть свои результаты командой /mystats, а таблицу лидеров — /top."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def workout_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Запись тренировки отменена.")
    context.user_data.clear()
    return ConversationHandler.END
