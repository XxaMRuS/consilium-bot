import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Название файла базы данных
DB_NAME = "workouts.db"

def init_db():
    """Создаёт таблицы, если их ещё нет."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Таблица пользователей (чтобы не спамить повторяющейся информацией)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Таблица упражнений (список доступных упражнений)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            metric TEXT NOT NULL,  -- 'reps' или 'time'
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # Таблица результатов тренировок
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            result_value TEXT NOT NULL,   -- число повторений или время (например, "50" или "03:20")
            video_link TEXT NOT NULL,
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

def add_user(user_id, first_name, last_name, username):
    """Добавляет пользователя в таблицу users (если его ещё нет)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
        VALUES (?, ?, ?, ?)
    """, (user_id, first_name, last_name, username))
    conn.commit()
    conn.close()

def get_exercises(active_only=True):
    """Возвращает список упражнений (id, name, metric)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if active_only:
        cur.execute("SELECT id, name, metric FROM exercises WHERE is_active = 1")
    else:
        cur.execute("SELECT id, name, metric FROM exercises")
    exercises = cur.fetchall()
    conn.close()
    return exercises

def add_workout(user_id, exercise_id, result_value, video_link):
    """Сохраняет результат тренировки."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workouts (user_id, exercise_id, result_value, video_link)
        VALUES (?, ?, ?, ?)
    """, (user_id, exercise_id, result_value, video_link))
    conn.commit()
    conn.close()

def add_exercise(name, description, metric):
    """Добавляет новое упражнение (для админа)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO exercises (name, description, metric)
            VALUES (?, ?, ?)
        """, (name, description, metric))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

# Можно добавить функции для получения статистики позже
