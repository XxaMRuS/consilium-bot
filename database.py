import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_NAME = "workouts.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            metric TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise_id INTEGER NOT NULL,
            result_value TEXT NOT NULL,
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
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
        VALUES (?, ?, ?, ?)
    """, (user_id, first_name, last_name, username))
    conn.commit()
    conn.close()

def get_exercises(active_only=True):
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
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workouts (user_id, exercise_id, result_value, video_link)
        VALUES (?, ?, ?, ?)
    """, (user_id, exercise_id, result_value, video_link))
    conn.commit()
    conn.close()

def add_exercise(name, description, metric):
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
    import json
import os

def load_exercises_from_json(json_file='exercises.json'):
    """Загружает упражнения из JSON-файла в базу, если таблица пуста."""
    # Проверяем, есть ли уже упражнения
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exercises")
    count = cur.fetchone()[0]
    conn.close()

    if count > 0:
        logger.info("В базе уже есть упражнения, пропускаем загрузку из JSON.")
        return

    # Если файл не существует, выходим
    if not os.path.exists(json_file):
        logger.warning(f"Файл {json_file} не найден. Упражнения не загружены.")
        return

    # Загружаем данные из JSON
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            exercises = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при чтении {json_file}: {e}")
        return

    # Добавляем каждое упражнение в базу
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    added = 0
    for ex in exercises:
        try:
            cur.execute("""
                INSERT INTO exercises (name, description, metric)
                VALUES (?, ?, ?)
            """, (ex['name'], ex.get('description', ''), ex['metric']))
            added += 1
        except sqlite3.IntegrityError:
            logger.warning(f"Упражнение '{ex['name']}' уже существует, пропускаем.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении упражнения {ex.get('name')}: {e}")
    conn.commit()
    conn.close()
    logger.info(f"Загружено {added} новых упражнений из {json_file}.")
