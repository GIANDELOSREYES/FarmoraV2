"""
database.py - Farmora's chat storage (SQLite)

Stores chats and their messages in a local file, farmora.db, so the
chat history survives page refreshes and server restarts.

Tables:
    chats     (id, title, created_at, updated_at)
    messages  (id, chat_id, role, content, stopped, created_at)

SQLite comes with Python, so no extra package is needed.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "farmora.db"

DEFAULT_TITLE = "New chat"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    """Open a connection, commit on success, and always close it."""

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    """Create the tables if they don't exist yet."""

    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL
                            REFERENCES chats(id) ON DELETE CASCADE,
                role        TEXT    NOT NULL
                            CHECK (role IN ('user', 'assistant')),
                content     TEXT    NOT NULL,
                stopped     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_chat
                ON messages (chat_id, id);
        """)


# ---------------------------------------------------------------
# Chats (Create, Read, Update, Delete)
# ---------------------------------------------------------------

def create_chat(title=DEFAULT_TITLE):

    timestamp = now()

    with connect() as db:
        cursor = db.execute(
            "INSERT INTO chats (title, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            (title, timestamp, timestamp)
        )
        chat_id = cursor.lastrowid

    return get_chat(chat_id)


def list_chats():
    """All chats, most recently used first."""

    with connect() as db:
        rows = db.execute(
            "SELECT id, title, created_at, updated_at FROM chats "
            "ORDER BY updated_at DESC, id DESC"
        ).fetchall()

    return [dict(row) for row in rows]


def get_chat(chat_id):

    with connect() as db:
        row = db.execute(
            "SELECT id, title, created_at, updated_at FROM chats "
            "WHERE id = ?",
            (chat_id,)
        ).fetchone()

    return dict(row) if row else None


def rename_chat(chat_id, title):

    with connect() as db:
        db.execute(
            "UPDATE chats SET title = ? WHERE id = ?",
            (title, chat_id)
        )

    return get_chat(chat_id)


def touch_chat(chat_id):
    """Move a chat to the top of the sidebar."""

    with connect() as db:
        db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now(), chat_id)
        )


def delete_chat(chat_id):
    """Delete a chat. Its messages are deleted too (ON DELETE CASCADE)."""

    with connect() as db:
        db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


def delete_all_chats():

    with connect() as db:
        db.execute("DELETE FROM chats")


# ---------------------------------------------------------------
# Messages
# ---------------------------------------------------------------

def add_message(chat_id, role, content, stopped=False):

    with connect() as db:
        cursor = db.execute(
            "INSERT INTO messages "
            "(chat_id, role, content, stopped, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, int(stopped), now())
        )

    return cursor.lastrowid


def get_messages(chat_id):

    with connect() as db:
        rows = db.execute(
            "SELECT id, role, content, stopped, created_at "
            "FROM messages WHERE chat_id = ? ORDER BY id",
            (chat_id,)
        ).fetchall()

    return [
        {**dict(row), "stopped": bool(row["stopped"])}
        for row in rows
    ]


def get_message(chat_id, message_id):

    with connect() as db:
        row = db.execute(
            "SELECT id, role, content, stopped, created_at "
            "FROM messages WHERE chat_id = ? AND id = ?",
            (chat_id, message_id)
        ).fetchone()

    return dict(row) if row else None


def update_message(chat_id, message_id, content):

    with connect() as db:
        db.execute(
            "UPDATE messages SET content = ? "
            "WHERE chat_id = ? AND id = ?",
            (content, chat_id, message_id)
        )


def delete_messages_after(chat_id, message_id):
    """Delete every message that comes after the given message."""

    with connect() as db:
        db.execute(
            "DELETE FROM messages WHERE chat_id = ? AND id > ?",
            (chat_id, message_id)
        )


def get_last_user_message(chat_id):

    with connect() as db:
        row = db.execute(
            "SELECT id, role, content, stopped, created_at "
            "FROM messages WHERE chat_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT 1",
            (chat_id,)
        ).fetchone()

    return dict(row) if row else None


def get_history_before(chat_id, message_id, limit):
    """The last `limit` messages before the given message, oldest first."""

    with connect() as db:
        rows = db.execute(
            "SELECT role, content FROM messages "
            "WHERE chat_id = ? AND id < ? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, message_id, limit)
        ).fetchall()

    return [dict(row) for row in reversed(rows)]
