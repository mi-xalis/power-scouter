import sqlite3
import pandas as pd
from datetime import date

DB_PATH = "workout_tracker.db"

# ---------- Database Initialization ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS exercises
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  description TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_categories
                 (exercise_id INTEGER,
                  category_id INTEGER,
                  FOREIGN KEY(exercise_id) REFERENCES exercises(id),
                  FOREIGN KEY(category_id) REFERENCES categories(id),
                  PRIMARY KEY (exercise_id, category_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS workout_sets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  exercise_id INTEGER,
                  date TEXT,
                  weight REAL,
                  reps INTEGER,
                  set_number INTEGER,
                  rp_rating INTEGER,
                  FOREIGN KEY(user_id) REFERENCES users(id),
                  FOREIGN KEY(exercise_id) REFERENCES exercises(id))''')
    
    conn.commit()
    conn.close()

# ---------- Helper Functions ----------
def get_user_id(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    if result:
        user_id = result[0]
    else:
        c.execute("INSERT INTO users (username) VALUES (?)", (username,))
        user_id = c.lastrowid
        conn.commit()
    conn.close()
    return user_id

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT id, name FROM categories ORDER BY name", conn)
    conn.close()
    return df

def add_category(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_exercises(category_ids=None, search_term=""):
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT DISTINCT e.id, e.name, e.description
        FROM exercises e
        LEFT JOIN exercise_categories ec ON e.id = ec.exercise_id
        WHERE 1=1
    """
    params = []
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        query += f" AND ec.category_id IN ({placeholders})"
        params.extend(category_ids)
    if search_term:
        query += " AND e.name LIKE ?"
        params.append(f"%{search_term}%")
    query += " ORDER BY e.name"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_exercise(name, description, category_ids):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO exercises (name, description) VALUES (?, ?)", (name, description))
        exercise_id = c.lastrowid
        for cat_id in category_ids:
            c.execute("INSERT INTO exercise_categories (exercise_id, category_id) VALUES (?, ?)",
                      (exercise_id, cat_id))
        conn.commit()
    except sqlite3.IntegrityError:
        print("Exercise with this name already exists.")
    conn.close()

def log_set(user_id, exercise_id, date_val, weight, reps, set_number, rp_rating):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO workout_sets 
                 (user_id, exercise_id, date, weight, reps, set_number, rp_rating)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (user_id, exercise_id, date_val.isoformat(), weight, reps, set_number, rp_rating))
    conn.commit()
    conn.close()

def get_user_workout_sets(user_id, exercise_id=None):
    conn = sqlite3.connect(DB_PATH)
    if exercise_id:
        df = pd.read_sql_query('''SELECT * FROM workout_sets 
                                   WHERE user_id = ? AND exercise_id = ? 
                                   ORDER BY date, set_number''',
                               conn, params=(user_id, exercise_id))
    else:
        df = pd.read_sql_query('''SELECT ws.*, e.name as exercise_name 
                                   FROM workout_sets ws
                                   JOIN exercises e ON ws.exercise_id = e.id
                                   WHERE user_id = ? 
                                   ORDER BY date, exercise_name, set_number''',
                               conn, params=(user_id,))
    conn.close()
    return df