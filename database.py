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

    # Таблица пользователей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            level TEXT DEFAULT 'beginner',
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if 'level' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN level TEXT DEFAULT 'beginner'")
        logger.info("Колонка 'level' добавлена в users.")

    # Таблица упражнений
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            metric TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            week INTEGER DEFAULT 0,
            difficulty TEXT DEFAULT 'beginner',
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

    # --- НОВОЕ: Таблица комплексов ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complexes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            points INTEGER DEFAULT 0,
            week INTEGER DEFAULT 0,
            difficulty TEXT DEFAULT 'beginner',
            is_active BOOLEAN DEFAULT 1
        )
    """)
    logger.info("Таблица 'complexes' создана (если не существовала).")

    # --- НОВОЕ: Связь комплексов с упражнениями ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complex_exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complex_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            reps INTEGER,  -- количество повторений (если задано)
            weight REAL,   -- вес (если задан)
            time TEXT,     -- время (если задано)
            order_index INTEGER NOT NULL,
            FOREIGN KEY(complex_id) REFERENCES complexes(id),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id)
        )
    """)
    logger.info("Таблица 'complex_exercises' создана.")

    # Таблица результатов тренировок (добавляем поле is_best)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NULL,        -- может быть NULL, если это комплекс
            complex_id INTEGER NULL,          -- может быть NULL, если это упражнение
            result_value TEXT NOT NULL,
            video_link TEXT NOT NULL,
            user_level TEXT NOT NULL,
            is_best BOOLEAN DEFAULT 0,        -- 1 если это лучший результат
            performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id),
            FOREIGN KEY(complex_id) REFERENCES complexes(id)
        )
    """)
    cur.execute("PRAGMA table_info(workouts)")
    columns = [col[1] for col in cur.fetchall()]
    if 'user_level' not in columns:
        cur.execute("ALTER TABLE workouts ADD COLUMN user_level TEXT DEFAULT 'beginner'")
        logger.info("Колонка 'user_level' добавлена в workouts.")
    if 'complex_id' not in columns:
        cur.execute("ALTER TABLE workouts ADD COLUMN complex_id INTEGER DEFAULT NULL")
        logger.info("Колонка 'complex_id' добавлена в workouts.")
    if 'is_best' not in columns:
        cur.execute("ALTER TABLE workouts ADD COLUMN is_best BOOLEAN DEFAULT 0")
        logger.info("Колонка 'is_best' добавлена в workouts.")

    conn.commit()
    conn.close()
    logger.info("База данных инициализирована (с поддержкой комплексов и рекордов).")

    load_exercises_from_json_if_empty()

# ... остальные функции остаются без изменений до add_workout

def add_workout(user_id, exercise_id, result_value, video_link, user_level, complex_id=None):
    """Добавляет тренировку (упражнение или комплекс)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workouts (user_id, exercise_id, complex_id, result_value, video_link, user_level, is_best)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, exercise_id, complex_id, result_value, video_link, user_level, 0))
    conn.commit()
    conn.close()
    # TODO: позже добавим логику обновления is_best

def get_user_workouts(user_id, limit=20):
    """Возвращает последние тренировки пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            w.id,
            COALESCE(e.name, c.name) as name,
            w.result_value,
            w.video_link,
            w.performed_at,
            w.is_best,
            CASE WHEN w.exercise_id IS NOT NULL THEN 'упражнение' ELSE 'комплекс' END as type
        FROM workouts w
        LEFT JOIN exercises e ON w.exercise_id = e.id
        LEFT JOIN complexes c ON w.complex_id = c.id
        WHERE w.user_id = ?
        ORDER BY w.performed_at DESC
        LIMIT ?
    """, (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

# ... остальные функции остаются без изменений
