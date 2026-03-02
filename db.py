import sqlite3
import json

DB_PATH = "dashboard.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dashboards (
        session_id TEXT PRIMARY KEY,
        schema_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traceability (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        requirement_id TEXT,
        description TEXT,
        signal TEXT,
        widget_id TEXT,
        verification_status TEXT
    )
    """)

    conn.commit()
    conn.close()

# -----------------------------
# Session + Messages
# -----------------------------

def create_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
        (session_id,)
    )
    conn.commit()
    conn.close()

def save_message(session_id, role, content):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.commit()
    conn.close()

def get_messages(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

# -----------------------------
# Dashboard + Traceability
# -----------------------------

def save_dashboard(session_id, schema):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO dashboards (session_id, schema_json) VALUES (?, ?)",
        (session_id, json.dumps(schema))
    )
    conn.commit()
    conn.close()

def clear_traceability(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM traceability WHERE session_id=?",
        (session_id,)
    )
    conn.commit()
    conn.close()

def save_traceability(session_id, req_id, description, signal, widget_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO traceability
        (session_id, requirement_id, description, signal, widget_id, verification_status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, req_id, description, signal, widget_id, status))
    conn.commit()
    conn.close()

def get_traceability(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT requirement_id, description, signal, widget_id, verification_status
        FROM traceability
        WHERE session_id=?
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()

    return [{
        "requirement_id": r[0],
        "description": r[1],
        "signal": r[2],
        "widget_id": r[3],
        "verification_status": r[4]
    } for r in rows]