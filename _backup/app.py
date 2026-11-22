"""
app.py - Farmora v2 web server

Run:   python app.py
Open:  http://127.0.0.1:5050

"""

import re

from flask import (
    Flask, Response, abort, jsonify, render_template,
    request, stream_with_context
)

import database as db
from retrieve import (
    FALLBACK_ANSWER, REPLACE_MARKER,
    generate_response_stream, get_starter_questions, suggest_follow_ups
)

app = Flask(__name__)

# How many earlier messages are sent to the model as context
HISTORY_LIMIT = 10

# Longest chat title created automatically from the first question
TITLE_LENGTH = 40

db.init_db()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def find_chat(chat_id):

    chat = db.get_chat(chat_id)

    if chat is None:
        abort(404, description="Chat not found.")

    return chat


def read_text(field):
    """Read a required, non-empty text field from the JSON body."""

    data = request.get_json(silent=True) or {}
    value = str(data.get(field, "")).strip()

    if not value:
        abort(400, description=f"'{field}' is required.")

    return value


def make_title(question):

    title = " ".join(question.split())

    if len(title) > TITLE_LENGTH:
        title = title[:TITLE_LENGTH].rsplit(" ", 1)[0] + "..."

    return title


def stream_answer(chat_id, question, history):
    """
    Stream the answer to the browser and save it when finished.

    If the user presses Stop, the browser closes the connection,
    Flask stops this generator, and the partial answer is saved
    with stopped=True.
    """

    def generate():

        answer = ""
        stopped = True

        try:
            for chunk in generate_response_stream(question, history):

                if chunk.startswith(REPLACE_MARKER):
                    answer = chunk[len(REPLACE_MARKER):]
                else:
                    answer += chunk

                yield chunk

            stopped = False

        except GeneratorExit:
            # The user pressed Stop or closed the page
            print("\n[Farmora] Answer stopped by the user.\n")
            raise

        except Exception as error:
            print("\n[Farmora] Error while answering:", error, "\n")
            message = "\n\nSorry, something went wrong. Please try again."
            answer += message
            stopped = False
            yield message

        finally:
            answer = answer.strip()

            # A stopped answer can end with an empty bullet ("-" or "2.")
            if stopped:
                answer = re.sub(r"\n\s*([-*]|\d+\.)\s*$", "", answer).strip()

            if answer:
                db.add_message(chat_id, "assistant", answer, stopped)
            db.touch_chat(chat_id)

    return Response(
        stream_with_context(generate()),
        content_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


# ---------------------------------------------------------------
# Pages
# ---------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------------------------------------------------------
# Chats (CRUD)
# ---------------------------------------------------------------

@app.get("/api/chats")
def list_chats():
    return jsonify(db.list_chats())


@app.post("/api/chats")
def create_chat():

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip() or db.DEFAULT_TITLE

    return jsonify(db.create_chat(make_title(title))), 201


@app.get("/api/chats/<int:chat_id>")
def read_chat(chat_id):

    chat = find_chat(chat_id)
    chat["messages"] = db.get_messages(chat_id)

    return jsonify(chat)


@app.patch("/api/chats/<int:chat_id>")
def rename_chat(chat_id):

    find_chat(chat_id)
    title = read_text("title")[:100]

    return jsonify(db.rename_chat(chat_id, title))


@app.delete("/api/chats/<int:chat_id>")
def delete_chat(chat_id):

    find_chat(chat_id)
    db.delete_chat(chat_id)

    return jsonify({"deleted": chat_id})


@app.delete("/api/chats")
def delete_all_chats():

    db.delete_all_chats()

    return jsonify({"deleted": "all"})


# ---------------------------------------------------------------
# Messages
# ---------------------------------------------------------------

@app.post("/api/chats/<int:chat_id>/messages")
def send_message(chat_id):

    chat = find_chat(chat_id)
    question = read_text("message")

    # Name a new chat after its first question
    if chat["title"] == db.DEFAULT_TITLE and not db.get_messages(chat_id):
        db.rename_chat(chat_id, make_title(question))

    message_id = db.add_message(chat_id, "user", question)
    history = db.get_history_before(chat_id, message_id, HISTORY_LIMIT)

    print("\n========== NEW QUESTION ==========")
    print("Chat:", chat_id, "| Question:", question)
    print("==================================\n")

    return stream_answer(chat_id, question, history)


@app.post("/api/chats/<int:chat_id>/regenerate")
def regenerate(chat_id):

    find_chat(chat_id)
    last_question = db.get_last_user_message(chat_id)

    if last_question is None:
        abort(400, description="There is no question to answer again.")

    # Remove the old answer, then answer the same question again
    db.delete_messages_after(chat_id, last_question["id"])
    history = db.get_history_before(
        chat_id, last_question["id"], HISTORY_LIMIT
    )

    return stream_answer(chat_id, last_question["content"], history)


@app.patch("/api/chats/<int:chat_id>/messages/<int:message_id>")
def edit_message(chat_id, message_id):

    find_chat(chat_id)
    message = db.get_message(chat_id, message_id)

    if message is None:
        abort(404, description="Message not found.")

    if message["role"] != "user":
        abort(400, description="Only your own questions can be edited.")

    content = read_text("content")

    # Save the edited question and remove everything after it.
    # The browser then calls /regenerate to get a new answer.
    db.update_message(chat_id, message_id, content)
    db.delete_messages_after(chat_id, message_id)

    return jsonify(db.get_message(chat_id, message_id))


# ---------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------

@app.get("/api/suggestions")
def starter_suggestions():
    return jsonify({"suggestions": get_starter_questions()})


@app.post("/api/chats/<int:chat_id>/follow-ups")
def follow_up_suggestions(chat_id):

    find_chat(chat_id)
    messages = db.get_messages(chat_id)

    if len(messages) < 2 or messages[-1]["role"] != "assistant":
        return jsonify({"suggestions": []})

    question = messages[-2]["content"]
    answer = messages[-1]["content"]

    # No suggestions after a refusal, an error or a stopped answer
    if (
        messages[-1]["stopped"]
        or answer.startswith("I'm sorry")
        or answer == FALLBACK_ANSWER
        or "something went wrong" in answer
    ):
        return jsonify({"suggestions": []})

    try:
        suggestions = suggest_follow_ups(question, answer)
    except Exception as error:
        print("\n[Farmora] Could not create follow-ups:", error, "\n")
        suggestions = []

    return jsonify({"suggestions": suggestions})


# ---------------------------------------------------------------
# Errors: return JSON for API requests
# ---------------------------------------------------------------

@app.errorhandler(400)
@app.errorhandler(404)
def handle_error(error):

    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code

    return error


if __name__ == "__main__":
    app.run(debug=True, threaded=True, port=5050)
