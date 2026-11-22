# Farmora v2

Farmora is an agriculture and farming chatbot that answers from farming documents using RAG (retrieval-augmented generation), a local Llama 3 model in Ollama, and a Flask web app.

Version 2 adds ChatGPT-style features on top of Farmora v1.

## What's new in v2

| Feature | How to use it |
|---|---|
| **Chat history sidebar** | Every chat is saved in `farmora.db` and listed in the sidebar. Click a chat to open it. Chats stay after a refresh or a server restart. |
| **New chat** | Click **New chat**. The chat is saved when you send the first question and is named after that question. |
| **Rename chat** | Hover over a chat in the sidebar and click the pencil. Press Enter to save or Esc to cancel. |
| **Delete chat / Delete all chats** | Click the trash icon next to a chat, or **Delete all chats** at the bottom of the sidebar. |
| **Edit a question** | Hover over your question and click the pencil. **Save & submit** replaces the question and gets a new answer. |
| **Stop** | While Farmora answers, the send button becomes a square Stop button. The partial answer is kept and marked "Answer stopped." |
| **Regenerate** | Click the circular arrow under the latest answer to answer the same question again. |
| **Copy** | Click the copy icon under any message. |
| **Starter questions** | The welcome screen shows 4 random farming questions. Click one to ask it. |
| **Follow-up suggestions** | After each answer, Farmora suggests up to 3 follow-up questions. |
| **Faster first question** | The first question in a chat skips the question-rewriting step, saving one model call. |

## Project structure

```
farmora-v2/
├── documents/
│   └── Farm-Planning-and-Organic-Agriculture-Management-Pactices.pdf
├── static/
│   ├── fonts/poppins.regular.ttf
│   └── js/script.js          Chat interface: sidebar, streaming, stop, edit, suggestions
├── templates/
│   └── index.html            Page layout: sidebar, chat area, input
├── Modelfile                 Defines the farming-guide model
├── ingest.py                 Builds vector_db/ from the PDF (same as v1)
├── retrieve.py               RAG engine: rewrite, retrieve, stream, follow-ups
├── database.py               SQLite storage for chats and messages (new)
├── app.py                    Flask server and REST API
├── requirements.txt
└── .gitignore
```

Generated while running (not included): `.venv/`, `vector_db/`, `farmora.db`.

## Setup

1. **Install Ollama** from https://ollama.com/download, then build the model from the project folder:

   ```bash
   ollama pull llama3:8b
   ollama create farming-guide -f ./Modelfile
   ```

   If you already built `farming-guide` for v1, skip this step.

2. **Create a virtual environment and install the libraries:**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Build the knowledge base.** Either copy the `vector_db/` folder from your v1 project into this folder (it uses the same embeddings), or build it:

   ```bash
   python ingest.py
   ```

4. **Start Farmora:**

   ```bash
   python app.py
   ```

   Open **http://127.0.0.1:5000**. Press Ctrl + C in the terminal to stop the server.

## How v2 works

### Database (`database.py`)

SQLite comes with Python, so no extra package is needed. The database file `farmora.db` is created automatically on first run.

| Table | Columns |
|---|---|
| `chats` | `id`, `title`, `created_at`, `updated_at` |
| `messages` | `id`, `chat_id`, `role` (`user` / `assistant`), `content`, `stopped`, `created_at` |

Deleting a chat also deletes its messages (`ON DELETE CASCADE`). To start over with no history, stop the server and delete `farmora.db`.

### REST API (`app.py`)

| Method | Route | Action |
|---|---|---|
| `GET` | `/api/chats` | List all chats (Read) |
| `POST` | `/api/chats` | Create a chat (Create) |
| `GET` | `/api/chats/<id>` | Get a chat with its messages (Read) |
| `PATCH` | `/api/chats/<id>` | Rename a chat (Update) |
| `DELETE` | `/api/chats/<id>` | Delete a chat (Delete) |
| `DELETE` | `/api/chats` | Delete all chats |
| `POST` | `/api/chats/<id>/messages` | Send a question; streams the answer as text |
| `POST` | `/api/chats/<id>/regenerate` | Answer the last question again; streams the answer |
| `PATCH` | `/api/chats/<id>/messages/<message_id>` | Edit a question and remove everything after it (Update) |
| `GET` | `/api/suggestions` | Get 4 starter questions |
| `POST` | `/api/chats/<id>/follow-ups` | Get follow-up questions for the last answer |

### Stop button

The browser cancels the request with an `AbortController`. Flask notices the closed connection and stops the answer generator, which also stops the model. The partial answer is saved with `stopped = 1`.

### Settings you can change

| Setting | File | Default |
|---|---|---|
| `MODEL_NAME` | `retrieve.py` | `"farming-guide"` |
| `NUMBER_OF_CHUNKS` | `retrieve.py` | `5` chunks per question |
| `STARTER_QUESTIONS` | `retrieve.py` | 10 farming questions |
| `HISTORY_LIMIT` | `app.py` | Last `10` messages sent as context |
| `TITLE_LENGTH` | `app.py` | Chat titles cut at `40` characters |

## Notes

- **Follow-up suggestions** use one extra model call after each answer, so on slow computers they can take a few seconds to appear. They're skipped after refusals, errors and stopped answers.
- **All chats are shared** by everyone who opens the app on this server. It's designed for running locally on one computer.
- **Internet is needed** while using the page, because Tailwind CSS, marked and DOMPurify load from a CDN.
- **Before deploying,** set `debug=False` in `app.run()`.
