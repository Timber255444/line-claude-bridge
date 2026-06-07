import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/tmp/line_messages.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_group ON messages(group_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON messages(timestamp)")


def save_message(group_id: str, user_id: str, text: str, timestamp: datetime):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (group_id, user_id, text, timestamp) VALUES (?, ?, ?, ?)",
            (group_id, user_id, text, timestamp.isoformat()),
        )


def get_recent_messages(limit: int = 50, group_id: str = None) -> list[dict]:
    with get_conn() as conn:
        if group_id:
            rows = conn.execute(
                "SELECT * FROM messages WHERE group_id=? ORDER BY timestamp DESC LIMIT ?",
                (group_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def query_messages(keyword: str, group_id: str = None) -> list[dict]:
    with get_conn() as conn:
        if group_id:
            rows = conn.execute(
                "SELECT * FROM messages WHERE group_id=? AND text LIKE ? ORDER BY timestamp DESC LIMIT 100",
                (group_id, f"%{keyword}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages WHERE text LIKE ? ORDER BY timestamp DESC LIMIT 100",
                (f"%{keyword}%",),
            ).fetchall()
    return [dict(r) for r in rows]
