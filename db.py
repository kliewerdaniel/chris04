import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Optional

DB_FILE = Path("companion.db")


def init_db():
    """Initialize the database and create conversations table if not exists."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                session_id TEXT NOT NULL DEFAULT 'default'
            )
        """)
        conn.commit()


def save_message(role: str, content: str, session_id: str = 'default'):
    """Save a message to the database."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT INTO conversations (role, content, timestamp, session_id) VALUES (?, ?, ?, ?)",
            (role, content, time.time(), session_id)
        )
        conn.commit()


def get_messages(n: int = 50, session_id: str = 'default') -> List[Dict]:
    """Get the last n messages for a session, ordered chronologically."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT role, content, timestamp FROM conversations 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (session_id, n)
        )
        rows = cursor.fetchall()
        # Reverse to get chronological order
        messages = [dict(row) for row in reversed(rows)]
        return messages


def clear_messages(session_id: str = 'default'):
    """Clear all messages for a session."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "DELETE FROM conversations WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()


def get_message_count(session_id: str = 'default') -> int:
    """Get the total number of messages for a session."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id = ?",
            (session_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0