# database.py
# Saves Farmora's chats and messages in a file called farmora.db
# so the chat history is kept after a refresh or restart.
#
# It uses SQLite, which comes with Python (nothing to install).

import sqlite3
from datetime import datetime

DATABASE_FILE = "farmora.db"
DEFAULT_TITLE = "New chat"


# ---------------------------------------------------------------
# Helper functions
# Every other function in this file uses these three.
# ---------------------------------------------------------------

def get_connection():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row          # rows act like dictionaries
    connection.execute("PRAGMA foreign_keys = ON")  # needed for ON DELETE CASCADE
    return connection


def run(sql, values=()):
    """Run an INSERT, UPDATE or DELETE. Returns the new row's id."""
    connection = get_connection()
    cursor = connection.execute(sql, values)
    connection.commit()
    new_id = cursor.lastrowid
    connection.close()
    return new_id


def fetch_one(sql, values=()):
    """Run a SELECT and return one row as a dictionary (or None)."""
    connection = get_connection()
    row = connection.execute(sql, values).fetchone()
    connection.close()

    if row is None:
        return None
    return dict(row)


def fetch_all(sql, values=()):
    """Run a SELECT and return all rows as a list of dictionaries."""
    connection = get_connection()
    rows = connection.execute(sql, values).fetchall()
    connection.close()

    results = []
    for row in rows:
        results.append(dict(row))
    return results


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------
# Create the tables (runs once when app.py starts)
# ---------------------------------------------------------------

def init_db():
    run("""
        CREATE TABLE IF NOT EXISTS chats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)

    run("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            stopped     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        )
    """)


# ---------------------------------------------------------------
# Chats: Create, Read, Update, Delete
# ---------------------------------------------------------------

def create_chat(title=DEFAULT_TITLE):
    chat_id = run(
        "INSERT INTO chats (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now(), now())
    )
    return get_chat(chat_id)


def list_chats():
    # Most recently used chats first
    return fetch_all("SELECT * FROM chats ORDER BY updated_at DESC, id DESC")


def get_chat(chat_id):
    return fetch_one("SELECT * FROM chats WHERE id = ?", (chat_id,))


def rename_chat(chat_id, title):
    run("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
    return get_chat(chat_id)


def touch_chat(chat_id):
    # Moves the chat to the top of the sidebar
    run("UPDATE chats SET updated_at = ? WHERE id = ?", (now(), chat_id))


def delete_chat(chat_id):
    # Its messages are deleted automatically (ON DELETE CASCADE)
    run("DELETE FROM chats WHERE id = ?", (chat_id,))


def delete_all_chats():
    run("DELETE FROM chats")


# ---------------------------------------------------------------
# Messages
# role is "user" (a question) or "assistant" (Farmora's answer)
# stopped is 1 if the user pressed Stop, otherwise 0
# ---------------------------------------------------------------

def add_message(chat_id, role, content, stopped=0):
    return run(
        "INSERT INTO messages (chat_id, role, content, stopped, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (chat_id, role, content, stopped, now())
    )


def get_messages(chat_id):
    return fetch_all(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
        (chat_id,)
    )


def get_message(chat_id, message_id):
    return fetch_one(
        "SELECT * FROM messages WHERE chat_id = ? AND id = ?",
        (chat_id, message_id)
    )


def update_message(chat_id, message_id, content):
    run(
        "UPDATE messages SET content = ? WHERE chat_id = ? AND id = ?",
        (content, chat_id, message_id)
    )


def delete_messages_after(chat_id, message_id):
    # Deletes every message that came after the given message
    run(
        "DELETE FROM messages WHERE chat_id = ? AND id > ?",
        (chat_id, message_id)
    )


def get_last_question(chat_id):
    return fetch_one(
        "SELECT * FROM messages WHERE chat_id = ? AND role = 'user' "
        "ORDER BY id DESC LIMIT 1",
        (chat_id,)
    )


def get_history_before(chat_id, message_id, limit):
    # The last few messages before the given message, oldest first
    rows = fetch_all(
        "SELECT role, content FROM messages WHERE chat_id = ? AND id < ? "
        "ORDER BY id DESC LIMIT ?",
        (chat_id, message_id, limit)
    )
    rows.reverse()
    return rows
