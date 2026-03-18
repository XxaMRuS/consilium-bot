import sqlite3
import logging
import json
import os

logger = logging.getLogger(__name__)

DB_NAME = "workouts.db"
EXERCISES_JSON = "exercises.json"  # файл с начальными упражнениями

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
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Таблица упражнений
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            metric TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            week INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    # Проверяем наличие колонок (для старых баз)
    cur.execute("PRAGMA table_info(exercises)")
    columns = [col[1] for col in cur.fetchall()]
    if 'points' not in columns:
        cur.execute("ALTER TABLE exercises ADD COLUMN points INTEGER DEFAULT 0")
        logger.info("Колонка 'points' добавлена в exercises.")
    if 'week' not in columns:
        cur.execute("ALTER TABLE exercises ADD COLUMN week INTEGER DEFAULT 0")
        logger.info("Колонка 'week' добавлена в exercises.")

    # Таблица результатов тренировок
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

def get_exercises(active_only=True, week=None):
    """
    Возвращает список упражнений (id, name, metric, points, week).
    Если week указан, то фильтрует: week = 0 или week = заданный.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    query = "SELECT id, name, metric, points, week FROM exercises"
    conditions = []
    params = []
    if active_only:
        conditions.append("is_active = 1")
    if week is not None:
        conditions.append("(week = 0 OR week = ?)")
        params.append(week)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    cur.execute(query, params)
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

def add_exercise(name, description, metric, points=0, week=0):
    """Добавляет упражнение, если его ещё нет."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO exercises (name, description, metric, points, week)
            VALUES (?, ?, ?, ?, ?)
        """, (name, description, metric, points, week))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    return success

def delete_exercise(exercise_id):
    """Удаляет упражнение по ID."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM exercises WHERE id = ?", (exercise_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_all_exercises():
    """Возвращает список всех упражнений (id, name, metric, points, week)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id, name, metric, points, week FROM exercises ORDER BY name")
    exercises = cur.fetchall()
    conn.close()
    return exercises

def set_exercise_week(exercise_id, week):
    """Устанавливает неделю для упражнения (админ-функция)."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE exercises SET week = ? WHERE id = ?", (week, exercise_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id, period=None):
    """
    Возвращает статистику пользователя: сумма баллов, количество тренировок.
    period может быть 'day', 'week', 'month' – ограничивает дату.
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
    if period:
        if period == 'day':
            query += " AND DATE(w.performed_at) = DATE('now')"
        elif period == 'week':
            query += " AND strftime('%W', w.performed_at) = strftime('%W', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'month':
            query += " AND strftime('%m', w.performed_at) = strftime('%m', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
    cur.execute(query, params)
    result = cur.fetchone()
    conn.close()
    return result  # (total_points, total_workouts)

def get_leaderboard(period=None, limit=10):
    """
    Возвращает топ пользователей по сумме баллов за указанный период.
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
    if period:
        if period == 'day':
            query += " AND DATE(w.performed_at) = DATE('now')"
        elif period == 'week':
            query += " AND strftime('%W', w.performed_at) = strftime('%W', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
        elif period == 'month':
            query += " AND strftime('%m', w.performed_at) = strftime('%m', 'now') AND strftime('%Y', w.performed_at) = strftime('%Y', 'now')"
    query += " GROUP BY u.user_id ORDER BY total DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    results = cur.fetchall()
    conn.close()
    return results

# === АВТОЗАГРУЗКА УПРАЖНЕНИЙ ИЗ JSON ===
def load_initial_exercises():
    """Загружает упражнения из exercises.json, если таблица пуста."""
    if not os.path.exists(EXERCISES_JSON):
        logger.info(f"Файл {EXERCISES_JSON} не найден, пропускаем автозагрузку.")
        return

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exercises")
    count = cur.fetchone()[0]
    if count > 0:
        logger.info("Таблица упражнений не пуста, автозагрузка не требуется.")
        conn.close()
        return

    try:
        with open(EXERCISES_JSON, 'r', encoding='utf-8') as f:
            exercises = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения {EXERCISES_JSON}: {e}")
        conn.close()
        return

    for ex in exercises:
        try:
            cur.execute("""
                INSERT INTO exercises (name, description, metric, points, week)
                VALUES (?, ?, ?, ?, ?)
            """, (ex['name'], ex['description'], ex['metric'], ex['points'], ex.get('week', 0)))
        except sqlite3.IntegrityError:
            logger.warning(f"Упражнение '{ex['name']}' уже существует, пропускаем.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении {ex['name']}: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Автозагрузка завершена: загружено упражнений из {EXERCISES_JSON}.")
