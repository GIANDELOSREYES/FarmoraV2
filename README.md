# Farmora v2

Farmora is an agriculture and farming chatbot that answers from farming documents using RAG (retrieval-augmented generation), a local Llama 3 model in Ollama, and a Flask web app.

Version 2 adds ChatGPT-style features on top of Farmora v1.

## What's new in v2

| Feature | How to use it |
|---|---|
| **Chat history sidebar** | Every chat is saved in `farmora.db` and listed in the sidebar. Click a chat to open it. Chats stay after a refresh or a server restart. |
| **New chat** | Click **New chat**. The chat is saved when you send the first question and is named after that question. |
| **Rename chat** | Hover over a chat in the sidebar and click the pencil, then type the new name in the dialog. |
| **Delete a conversation** | Click the trash icon at the top right of the open chat, or next to any chat in the sidebar. A dialog asks you to confirm. The chat and all its messages are removed from `farmora.db`. |
| **Delete all chats** | Click **Delete all chats** at the bottom of the sidebar and confirm. |
| **Edit a question** | Hover over your question and click the pencil. The question becomes a text box: **Save** (or Enter) gets a new answer, **Cancel** (or Esc) keeps the old one. Answers and messages after the edited question are removed, because they replied to the old question. |
| **Sources** | Each answer lists the documents it was based on. |
| **Calm replies to profanity** | Profanity is removed before searching. A farming question still gets its answer, with a calm opening line; a message with no farming question gets a calm, supportive reply. Edit `PROFANE_WORDS` in `retrieve.py` to change the list. |
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
│   └── combined_agriculture_documents.md   40 DA-ATI leaflets, already split into sections
├── static/
│   ├── fonts/poppins.regular.ttf
│   └── js/script.js          Chat interface: sidebar, streaming, stop, edit, suggestions
├── templates/
│   └── index.html            Page layout: sidebar, chat area, input
├── Modelfile                 Defines the farming-guide model
├── ingest.py                 Builds vector_db/ from the documents
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

   **Run `ollama create` again if you built `farming-guide` before:** the Modelfile now keeps the model to the documents and gives it a larger context window.

2. **Create a virtual environment and install the libraries:**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Build the knowledge base** (run it again whenever the documents change; it replaces the old data instead of adding duplicates):

   ```bash
   python ingest.py
   ```

   A `vector_db/` folder from v1 can't be reused: the knowledge base is now stored differently.

4. **Start Farmora:**

   ```bash
   python app.py
   ```

   Open **http://127.0.0.1:5050**. Press Ctrl + C in the terminal to stop the server.

## How v2 works

### Answering from the documents (`ingest.py`, `retrieve.py`)

1. **Sections, not blind cuts.** The document is already divided into sections, each starting with a line like `[Topic: … | Document: … | Section: …]`. `ingest.py` keeps every section whole, and also cuts it into small overlapping passages (600 characters, 120 overlap). The embedding model reads only the first 256 tokens of a text, so the search compares the question with these small passages, and the model is given the *whole* section they belong to.
2. **Relevance filtering.** Each section is scored by its best passage (cosine similarity, 0–1). If even the best score is below `MIN_RELEVANCE` (0.48), Farmora replies "I'm sorry, but I do not have sufficient information to answer your question." without asking the model. Otherwise it keeps sections within `SCORE_WINDOW` (0.12) of the best one, up to 6 sections and 12,000 characters, and adds a section's "(continued)" neighbour.
3. **Grounded prompt.** Each excerpt is labelled with its document, crop and section. The model is told to use only the excerpts, to answer only the parts the documents support, and to refuse with the same sentence when they cover nothing. It is also asked for complete, well-organised answers: headings, every step in order, quantities, examples and precautions.
4. **Checks.** Numbers in an answer that don't appear in the excerpts are printed in the terminal for review. Follow-up suggestions are only shown if the documents can answer them.

### Database (`database.py`)

SQLite comes with Python, so no extra package is needed. The database file `farmora.db` is created automatically on first run.

| Table | Columns |
|---|---|
| `chats` | `id`, `title`, `created_at`, `updated_at` |
| `messages` | `id`, `chat_id`, `role` (`user` / `assistant`), `content`, `stopped`, `sources` (JSON list), `created_at` |

Deleting a chat also deletes its messages (`ON DELETE CASCADE`). An older `farmora.db` gets the new `sources` column automatically. To start over with no history, stop the server and delete `farmora.db`.

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
| `MIN_RELEVANCE` | `retrieve.py` | `0.48`: below this the documents can't answer |
| `SCORE_WINDOW` / `MAX_SECTIONS` | `retrieve.py` | `0.12` / `6` sections per question |
| `MAX_CONTEXT_CHARACTERS` | `retrieve.py` | `12000` characters of document text |
| `CONTEXT_WINDOW` / `MAX_ANSWER_TOKENS` | `retrieve.py` | `8192` / `2048` tokens |
| `PASSAGE_SIZE` / `PASSAGE_OVERLAP` | `ingest.py` | `600` / `120` characters (run `ingest.py` after changing) |
| `STARTER_QUESTIONS` | `retrieve.py` | 10 farming questions |
| `HISTORY_LIMIT` | `app.py` | Last `10` messages sent as context |
| `port` | `app.py` (last line) | `5050` |
| `TITLE_LENGTH` | `app.py` | Chat titles cut at `40` characters |

## Notes

- **Follow-up suggestions** use one extra model call after each answer, so on slow computers they can take a few seconds to appear. They're skipped after refusals, errors and stopped answers.
- **All chats are shared** by everyone who opens the app on this server. It's designed for running locally on one computer.
- **Internet is needed** while using the page, because Tailwind CSS, marked and DOMPurify load from a CDN (marked and DOMPurify are pinned to tested versions).
- **Small model, strict rules.** Llama 3 8B follows the grounding rules well, but no prompt can fully stop a model from adding a detail. Check the terminal for the "numbers not in the excerpts" warning while testing.
- **Before deploying,** set `debug=False` in `app.run()`.
