# database.py
# Saves Farmora's chats and messages in a file called farmora.db
# so the chat history is kept after a refresh or restart.
#
# It uses SQLite, which comes with Python (nothing to install).

import json
import sqlite3
from contextlib import closing
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


# "with closing(...)" closes the connection even if the SQL fails,
# and "with connection" commits, or rolls back after an error.

def run(sql, values=()):
    """Run an INSERT, UPDATE or DELETE. Returns the new row's id."""
    with closing(get_connection()) as connection:
        with connection:
            cursor = connection.execute(sql, values)
        return cursor.lastrowid


def fetch_one(sql, values=()):
    """Run a SELECT and return one row as a dictionary (or None)."""
    with closing(get_connection()) as connection:
        row = connection.execute(sql, values).fetchone()

    if row is None:
        return None
    return dict(row)


def fetch_all(sql, values=()):
    """Run a SELECT and return all rows as a list of dictionaries."""
    with closing(get_connection()) as connection:
        rows = connection.execute(sql, values).fetchall()

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
            sources     TEXT NOT NULL DEFAULT '[]',
            created_at  TEXT NOT NULL
        )
    """)

    # Databases made by an older Farmora have no "sources" column yet
    columns = [column["name"] for column in fetch_all("PRAGMA table_info(messages)")]
    if "sources" not in columns:
        run("ALTER TABLE messages ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'")


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
# sources is the list of documents an answer came from
# ---------------------------------------------------------------

def read_sources(message):
    # The sources are saved as JSON text, e.g. '["Tomato Production Guide"]'
    if message is not None:
        try:
            message["sources"] = json.loads(message.get("sources") or "[]")
        except ValueError:
            message["sources"] = []
    return message


def add_message(chat_id, role, content, stopped=0, sources=None):
    return run(
        "INSERT INTO messages (chat_id, role, content, stopped, sources, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, role, content, stopped, json.dumps(sources or []), now())
    )


def get_messages(chat_id):
    messages = fetch_all(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY id",
        (chat_id,)
    )
    return [read_sources(message) for message in messages]


def get_message(chat_id, message_id):
    return read_sources(fetch_one(
        "SELECT * FROM messages WHERE chat_id = ? AND id = ?",
        (chat_id, message_id)
    ))


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
    # The last few question-and-answer pairs before the given message,
    # oldest first. A question with no answer (for example, stopped
    # before any text appeared) is left out, so the model doesn't
    # mistake it for part of the current question.
    rows = fetch_all(
        "SELECT role, content FROM messages WHERE chat_id = ? AND id < ? "
        "ORDER BY id",
        (chat_id, message_id)
    )

    history = []
    for index, row in enumerate(rows):
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        answered = next_row is not None and next_row["role"] == "assistant"

        if row["role"] == "assistant" or answered:
            history.append(row)

    history = history[-limit:]

    # Start with a question, not with half of a pair
    if len(history) > 0 and history[0]["role"] == "assistant":
        history.pop(0)
    return history
