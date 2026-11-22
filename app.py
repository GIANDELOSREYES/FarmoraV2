# app.py
# Farmora v2 web server.
#
# Run:   python app.py
# Open:  http://127.0.0.1:5050

import json

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import database as db
from retrieve import (
    SOURCES_MARKER,
    generate_response_stream,
    get_starter_questions,
    is_refusal,
    suggest_follow_ups
)

app = Flask(__name__)

HISTORY_LIMIT = 10   # how many earlier messages the model sees
TITLE_LENGTH = 40    # longest automatic chat title

ERROR_MESSAGE = "Sorry, something went wrong. Please try again."
OLLAMA_MESSAGE = (
    "Sorry, Farmora can't reach its language model right now. "
    "Please make sure Ollama is running, then try again."
)

db.init_db()


# ---------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------

def error(message, status):
    return jsonify({"error": message}), status


def get_text(field):
    # Reads one text field from the JSON the browser sent
    data = request.get_json(silent=True) or {}
    return str(data.get(field, "")).strip()


def make_title(question):
    # Uses the first question as the chat title, cut to TITLE_LENGTH
    title = " ".join(question.split())

    if len(title) > TITLE_LENGTH:
        title = title[:TITLE_LENGTH].strip() + "..."

    return title


def remove_empty_bullet(answer):
    # A stopped answer can end with an empty "-" or "2." line
    lines = answer.split("\n")
    last_line = lines[-1].strip()

    is_bullet = last_line in ["-", "*"]
    is_number = last_line.endswith(".") and last_line[:-1].isdigit()

    if len(lines) > 1 and (is_bullet or is_number):
        lines.pop()

    return "\n".join(lines).strip()


def error_text(problem):
    # A friendlier message when Ollama isn't running
    text = (type(problem).__name__ + " " + str(problem)).lower()

    if "connect" in text or "refused" in text or "ollama" in text:
        return OLLAMA_MESSAGE
    return ERROR_MESSAGE


def stream_answer(chat_id, question, history):
    # Sends the answer to the browser piece by piece, then saves it.
    # The last piece is SOURCES_MARKER + the documents used; the
    # browser shows those under the answer.

    def generate():
        answer = ""
        sources = []
        finished = False

        try:
            for chunk in generate_response_stream(question, history):

                if chunk.startswith(SOURCES_MARKER):
                    sources = json.loads(chunk[len(SOURCES_MARKER):])
                else:
                    answer = answer + chunk

                yield chunk

            finished = True

        except Exception as problem:
            print("\n[Farmora] Error while answering:", repr(problem), "\n")
            message = error_text(problem)

            if answer.strip() != "":
                message = "\n\n" + message

            answer = answer + message
            sources = []
            finished = True
            yield message

        finally:
            # This part always runs: when the answer finishes,
            # when there is an error, and when the user presses Stop.
            if finished:
                stopped = 0
                answer = answer.strip()
            else:
                stopped = 1
                answer = remove_empty_bullet(answer.strip())
                print("\n[Farmora] Answer stopped by the user.\n")

            if answer != "":
                db.add_message(chat_id, "assistant", answer, stopped, sources)

            db.touch_chat(chat_id)

    return Response(
        stream_with_context(generate()),
        content_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ---------------------------------------------------------------
# The chat page
# ---------------------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------------------------------------------------------
# Chats: Create, Read, Update, Delete
# ---------------------------------------------------------------

@app.route("/api/chats", methods=["GET"])
def list_chats():
    return jsonify(db.list_chats())


@app.route("/api/chats", methods=["POST"])
def create_chat():
    chat = db.create_chat()
    return jsonify(chat), 201


@app.route("/api/chats/<int:chat_id>", methods=["GET"])
def read_chat(chat_id):
    chat = db.get_chat(chat_id)

    if chat is None:
        return error("Chat not found.", 404)

    chat["messages"] = db.get_messages(chat_id)
    return jsonify(chat)


@app.route("/api/chats/<int:chat_id>", methods=["PATCH"])
def rename_chat(chat_id):
    if db.get_chat(chat_id) is None:
        return error("Chat not found.", 404)

    title = get_text("title")

    if title == "":
        return error("Title is required.", 400)

    chat = db.rename_chat(chat_id, title[:100])
    return jsonify(chat)


@app.route("/api/chats/<int:chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    if db.get_chat(chat_id) is None:
        return error("Chat not found.", 404)

    db.delete_chat(chat_id)
    return jsonify({"deleted": chat_id})


@app.route("/api/chats", methods=["DELETE"])
def delete_all_chats():
    db.delete_all_chats()
    return jsonify({"deleted": "all"})


# ---------------------------------------------------------------
# Messages: send, regenerate, edit
# ---------------------------------------------------------------

@app.route("/api/chats/<int:chat_id>/messages", methods=["POST"])
def send_message(chat_id):
    chat = db.get_chat(chat_id)

    if chat is None:
        return error("Chat not found.", 404)

    question = get_text("message")

    if question == "":
        return error("Message is required.", 400)

    # A new chat is named after its first question
    if chat["title"] == db.DEFAULT_TITLE and len(db.get_messages(chat_id)) == 0:
        db.rename_chat(chat_id, make_title(question))

    message_id = db.add_message(chat_id, "user", question)
    history = db.get_history_before(chat_id, message_id, HISTORY_LIMIT)

    print("\n[Farmora] New question in chat", chat_id, ":", question, "\n")

    return stream_answer(chat_id, question, history)


@app.route("/api/chats/<int:chat_id>/regenerate", methods=["POST"])
def regenerate(chat_id):
    if db.get_chat(chat_id) is None:
        return error("Chat not found.", 404)

    last_question = db.get_last_question(chat_id)

    if last_question is None:
        return error("There is no question to answer again.", 400)

    # Delete the old answer, then answer the same question again
    db.delete_messages_after(chat_id, last_question["id"])
    history = db.get_history_before(chat_id, last_question["id"], HISTORY_LIMIT)

    return stream_answer(chat_id, last_question["content"], history)


@app.route("/api/chats/<int:chat_id>/messages/<int:message_id>", methods=["PATCH"])
def edit_message(chat_id, message_id):
    message = db.get_message(chat_id, message_id)

    if message is None:
        return error("Message not found.", 404)

    if message["role"] != "user":
        return error("Only your own questions can be edited.", 400)

    new_text = get_text("content")

    if new_text == "":
        return error("Content is required.", 400)

    # Save the new question and delete everything after it: the old
    # answers replied to the old question, so they are no longer valid.
    # The browser then calls /regenerate to get a new answer.
    db.update_message(chat_id, message_id, new_text)
    db.delete_messages_after(chat_id, message_id)

    # If the first question was edited, update the automatic title too
    chat = db.get_chat(chat_id)
    first_message = db.get_messages(chat_id)[0]

    if first_message["id"] == message_id and chat["title"] == make_title(message["content"]):
        db.rename_chat(chat_id, make_title(new_text))

    return jsonify(db.get_message(chat_id, message_id))


# ---------------------------------------------------------------
# Suggested questions
# ---------------------------------------------------------------

@app.route("/api/suggestions", methods=["GET"])
def starter_suggestions():
    return jsonify({"suggestions": get_starter_questions()})


@app.route("/api/chats/<int:chat_id>/follow-ups", methods=["POST"])
def follow_up_suggestions(chat_id):
    messages = db.get_messages(chat_id)

    # We need a question followed by an answer
    if len(messages) < 2 or messages[-1]["role"] != "assistant":
        return jsonify({"suggestions": []})

    question = messages[-2]["content"]
    answer = messages[-1]["content"]

    # No suggestions after a stopped answer, a refusal, an error or
    # small talk (answers without sources)
    if messages[-1]["stopped"] == 1 or is_refusal(answer):
        return jsonify({"suggestions": []})
    if answer.endswith(ERROR_MESSAGE) or answer.endswith(OLLAMA_MESSAGE):
        return jsonify({"suggestions": []})
    if len(messages[-1]["sources"]) == 0:
        return jsonify({"suggestions": []})

    try:
        suggestions = suggest_follow_ups(question, answer, messages[-1]["sources"])
    except Exception as problem:
        print("\n[Farmora] Could not create follow-ups:", problem, "\n")
        suggestions = []

    return jsonify({"suggestions": suggestions})


# ---------------------------------------------------------------
# Start the server
# ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, threaded=True, port=5050)
