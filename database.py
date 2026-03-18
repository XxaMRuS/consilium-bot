import sqlite3
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_NAME = "workouts.db"
EXERCISES_JSON = "exercises.json"

def init_db():
    """Создаёт таблицы и добавляет недостающие колонки."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Таблица пользователей (добавлен уровень)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            level TEXT DEFAULT 'beginner',  -- beginner / pro
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Проверяем наличие колонки level
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if 'level' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN level TEXT DEFAULT 'beginner'")
        logger.info("Колонка 'level' добавлена в users.")

    # Таблица упражнений (добавлен уровень сложности)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            metric TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            week INTEGER DEFAULT 0,
            difficulty TEXT DEFAULT 'beginner',  -- beginner / pro
            is_active BOOLEAN DEFAULT 1
        )
    """)

    cur.execute("PRAGMA table_info(exercises)")
    columns = [col[1] for col in cur.fetchall()]
    if 'points' not in columns:
        cur.execute("ALTER TABLE exercises ADD COLUMN points INTEGER DEFAULT 0")
        logger.info("Колонка 'points' добавлена в exercises.")
    if 'week' not in columns:
        cur.execute("ALTER TABLE exercises ADD COLUMN week INTEGER DEFAULT 0")
        logger.info("Колонка 'week' добавлена в exercises.")
    if 'difficulty' not in columns:
        cur.execute("ALTER TABLE exercises ADD COLUMN difficulty TEXT DEFAULT 'beginner'")
        logger.info("Колонка 'difficulty' добавлена в exercises.")

    # Таблица результатов тренировок (добавлен уровень пользователя на момент тренировки)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            result_value TEXT NOT NULL,
            video_link TEXT NOT NULL,
            user_level TEXT NOT NULL,  -- уровень на момент тренировки
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id)
        )
    """)

    cur.execute("PRAGMA table_info(workouts)")
    columns = [col[1] for col in cur.fetchall()]
    if 'user_level' not in columns:
        cur.execute("ALTER TABLE workouts ADD COLUMN user_level TEXT DEFAULT 'beginner'")
        logger.info("Колонка 'user_level' добавлена в workouts.")

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

    # Автоматическая загрузка упражнений из JSON, если база пуста
    load_exercises_from_json_if_empty()

def load_exercises_from_json_if_empty():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exercises")
    count = cur.fetchone()[0]
    conn.close()

    if count == 0:
        if not os.path.exists(EXERCISES_JSON):
            logger.warning(f"Файл {EXERCISES_JSON} не найден, пропускаем автозагрузку.")
            return
        try:
            with open(EXERCISES_JSON, 'r', encoding='utf-8') as f:
                exercises = json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения {EXERCISES_JSON}: {e}")
            return

        added = 0
        for ex in exercises:
            name = ex.get('name')
            metric = ex.get('metric')
            description = ex.get('description', '')
            points = ex.get('points', 0)
            week = ex.get('week', 0)
            difficulty = ex.get('difficulty', 'beginner')
            if add_exercise(name, description, metric, points, week, difficulty):
                added += 1
        logger.info(f"Автозагрузка: добавлено {added} упражнений из {EXERCISES_JSON}.")
    else:
        logger.info("В базе уже есть упражнения, автозагрузка пропущена.")

def add_user(user_id, first_name, last_name, username, level='beginner'):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, last_name, username, level)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, first_name, last_name, username, level))
    conn.commit()
    conn.close()

def get_user_level(user_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT level FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 'beginner'

def set_user_level(user_id, new_level):
    if new_level not in ('beginner', 'pro'):
        return False
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))
    conn.commit()
    conn.close()
    return True

def get_exercises(active_only=True, week=None, difficulty=None):
    """
    Возвращает список упражнений (id, name, metric, points, week, difficulty).
    Можно фильтровать по difficulty.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    query = "SELECT id, name, metric, points, week, difficulty FROM exercises"
    conditions = []
    params = []
    if active_only:
        conditions.append("is_active = 1")
    if week is not None:
        conditions.append("(week = 0 OR week = ?)")
        params.append(week)
    if difficulty is not None:
        conditions.append("difficulty = ?")
        params.append(difficulty)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    cur.execute(query, params)
    exercises = cur.fetchall()
    conn.close()
    return exercises

def get_all_exercises():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name, metric, points, week, difficulty FROM exercises ORDER BY name")
    exercises = cur.fetchall()
    conn.close()
    return exercises

def add_workout(user_id, exercise_id, result_value, video_link, user_level):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workouts (user_id, exercise_id, result_value, video_link, user_level)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, exercise_id, result_value, video_link, user_level))
    conn.commit()
    conn.close()

def add_exercise(name, description, metric, points=0, week=0, difficulty='beginner'):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO exercises (name, description, metric, points, week, difficulty)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, description, metric, points, week, difficulty))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_exercise(exercise_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM exercises WHERE id = ?", (exercise_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def set_exercise_week(exercise_id, week):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE exercises SET week = ? WHERE id = ?", (week, exercise_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id, period=None, level=None):
    """
    Возвращает (total_points, total_workouts) для пользователя.
    Если level указан, учитываются только тренировки с этим уровнем.
    period может быть 'day','week','month','year'.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    query = """
        SELECT SUM(e.points), COUNT(w.id)
        FROM workouts w
        JOIN exercises e ON w.exercise_id = e.id
        WHERE w.user_id = ?
    """
    params = [user_id]
    if level is not None:
        query += " AND w.user_level = ?"
        params.append(level)
    if period:
        if period == 'day':
            query += " AND DATE(w.performed_at) = DATE('now')"
        elif period == 'week':
            query += " AND strftime('%W', w.performed_at) = strftime('%W', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'month':
            query += " AND strftime('%m', w.performed_at) = strftime('%m', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'year':
            query += " AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
    cur.execute(query, params)
    result = cur.fetchone()
    conn.close()
    return result  # (total_points, total_workouts)

def get_leaderboard(period=None, level=None, limit=10):
    """
    Возвращает топ пользователей по сумме баллов.
    Если level указан, учитываются только тренировки этого уровня.
    period может быть 'day','week','month','year'.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    query = """
        SELECT u.user_id, u.first_name, u.username, SUM(e.points) as total
        FROM workouts w
        JOIN users u ON w.user_id = u.user_id
        JOIN exercises e ON w.exercise_id = e.id
        WHERE 1=1
    """
    params = []
    if level is not None:
        query += " AND w.user_level = ?"
        params.append(level)
    if period:
        if period == 'day':
            query += " AND DATE(w.performed_at) = DATE('now')"
        elif period == 'week':
            query += " AND strftime('%W', w.performed_at) = strftime('%W', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'month':
            query += " AND strftime('%m', w.performed_at) = strftime('%m', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'year':
            query += " AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
    query += " GROUP BY u.user_id ORDER BY total DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    results = cur.fetchall()
    conn.close()
    return results
