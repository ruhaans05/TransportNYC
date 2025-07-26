import sqlite3

def init_db():
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            chat_count INTEGER DEFAULT 0,
            ai_count INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def create_user(username, hashed_pw):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
    conn.commit()
    conn.close()

def get_user(username):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute("SELECT username, password, chat_count, ai_count FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    return user

def increment_count(username, column):
    conn = sqlite3.connect("app_data.db")
    c = conn.cursor()
    c.execute(f"UPDATE users SET {column} = {column} + 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()
