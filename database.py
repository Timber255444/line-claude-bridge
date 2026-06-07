import os
from datetime import datetime
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_group ON messages(group_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ts ON messages(timestamp)")


def save_message(group_id: str, user_id: str, text: str, timestamp: datetime):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (group_id, user_id, text, timestamp) VALUES (%s, %s, %s, %s)",
                (group_id, user_id, text, timestamp.isoformat()),
            )


def get_recent_messages(limit: int = 50, group_id: str = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if group_id:
                cur.execute(
                    "SELECT * FROM messages WHERE group_id=%s ORDER BY timestamp DESC LIMIT %s",
                    (group_id, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM messages ORDER BY timestamp DESC LIMIT %s",
                    (limit,),
                )
            return [dict(r) for r in cur.fetchall()]


def query_messages(keyword: str, group_id: str = None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if group_id:
                cur.execute(
                    "SELECT * FROM messages WHERE group_id=%s AND text ILIKE %s ORDER BY timestamp DESC LIMIT 100",
                    (group_id, f"%{keyword}%"),
                )
            else:
                cur.execute(
                    "SELECT * FROM messages WHERE text ILIKE %s ORDER BY timestamp DESC LIMIT 100",
                    (f"%{keyword}%",),
                )
            return [dict(r) for r in cur.fetchall()]
