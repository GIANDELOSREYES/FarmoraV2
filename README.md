# Farmora v3

Farmora is an agriculture and farming chatbot that answers from farming documents using RAG (retrieval-augmented generation), a local Llama 3 model in Ollama, and a Flask web app.

Version 3 makes answers more trustworthy: Farmora now refuses questions about crops and animals its documents don't cover, understands Filipino and Taglish questions, and points users to the topics it can help with.

## What's new in v3

| Feature | What it does |
|---|---|
| **Crop and animal check** | If a question names a crop or animal (for example mango or tilapia) that none of the found sections mention, Farmora refuses instead of giving advice meant for another crop. If a question names two crops and only one is covered, it answers that one and says it doesn't know the other. Edit `CROP_GROUPS` in `retrieve.py` to add crops. |
| **Word mapping** | Words people type are matched to the words the documents use, so "pigery", "piggery" and "baboy" find the hog-raising sections, and "kamatis" finds tomato. The mapping is also in `CROP_GROUPS`. |
| **Filipino and Taglish questions** | Search now uses a multilingual embedding model, so questions like "Paano magtanim ng kamatis?" find the right sections. |
| **Helpful refusals** | "I'm sorry, but I do not have sufficient information…" is followed by a short list of topics Farmora can help with (`TOPICS_HINT` in `retrieve.py`). |
| **Better profanity handling** | A real question that contains profanity gets a calm opening line and then a normal answer, or a refusal with the topic list. Only messages that are mostly frustration ("fuck you") get the calm, supportive reply. |
| **Honest greeting** | The greeting lists the topics Farmora actually covers instead of promising "raising animals" in general. |
| **Invented-number log** | Numbers in an answer that aren't in the retrieved sections are written to `unverified_numbers.log` as well as the terminal, so they can be reviewed after testing. |
| **Test script** | `python test_questions.py` checks which questions Farmora would answer or refuse, without calling the language model, so it runs in seconds. |

### Features from v2

| Feature | How to use it |
|---|---|
| **Chat history sidebar** | Every chat is saved in `farmora.db` and listed in the sidebar. Click a chat to open it. Chats stay after a refresh or a server restart. |
| **New chat** | Click **New chat**. The chat is saved when you send the first question and is named after that question. |
| **Rename chat** | Hover over a chat in the sidebar and click the pencil, then type the new name in the dialog. |
| **Delete a conversation** | Click the trash icon at the top right of the open chat, or next to any chat in the sidebar. A dialog asks you to confirm. The chat and all its messages are removed from `farmora.db`. |
| **Delete all chats** | Click **Delete all chats** at the bottom of the sidebar and confirm. |
| **Edit a question** | Hover over your question and click the pencil. The question becomes a text box: **Save** (or Enter) gets a new answer, **Cancel** (or Esc) keeps the old one. Answers and messages after the edited question are removed, because they replied to the old question. |
| **Natural answers** | Farmora talks like a person: it never mentions documents, excerpts or sources. The documents used are still saved with each answer; set `SHOW_SOURCES = true` in `static/js/script.js` to show them under answers. |
| **Stop** | While Farmora answers, the send button becomes a square Stop button. The partial answer is kept and marked "Answer stopped." |
| **Regenerate** | Click the circular arrow under the latest answer to answer the same question again. |
| **Copy** | Click the copy icon under any message. |
| **Starter questions** | The welcome screen shows 4 random farming questions. Click one to ask it. |
| **Follow-up suggestions** | After each answer, Farmora suggests up to 3 follow-up questions. |
| **Faster first question** | The first question in a chat skips the question-rewriting step, saving one model call. |

## What Farmora can answer

The knowledge base is 40 Department of Agriculture and Agricultural Training Institute (DA-ATI) leaflets covering:

- **Crops:** rice, corn, strawberry, coffee, potato, and vegetables such as tomato, ampalaya, okra, pechay, squash, pole sitaw, snap bean, cabbage and hot pepper
- **Gardening:** urban and home gardening (lowland and upland), container gardening, plant propagation
- **Soil and inputs:** composting, green manuring, fertilizers, fertigation, organic concoctions, mokusaku (wood vinegar)
- **Animals:** organic hog raising, African swine fever prevention, organic poultry, goats and sheep, forage crops
- **Farm systems and safety:** integrated farming systems, food safety hazards

It doesn't cover fruit trees such as mango or banana, fish, cattle or ducks.

## Project structure

```
farmora-v3/
├── documents/
│   └── combined_agriculture_documents.md   40 DA-ATI leaflets, already split into sections
├── static/
│   ├── fonts/poppins.regular.ttf
│   ├── images/               Favicon (favicon.ico, favicon.png, apple-touch-icon.png)
│   └── js/script.js          Chat interface: sidebar, streaming, stop, edit, suggestions
├── templates/
│   └── index.html            Page layout: sidebar, chat area, input
├── Modelfile                 Defines the farming-guide model
├── ingest.py                 Builds vector_db/ from the documents
├── retrieve.py               RAG engine: rewrite, retrieve, crop check, stream, follow-ups
├── database.py               SQLite storage for chats and messages
├── app.py                    Flask server and REST API
├── test_questions.py         Answer-or-refuse tests (new)
├── requirements.txt
└── .gitignore
```

Generated while running (not included): `.venv/`, `vector_db/`, `farmora.db`, `unverified_numbers.log`.

## Setup

1. **Install Ollama** from https://ollama.com/download, then build the model from the project folder:

   ```bash
   ollama pull llama3:8b
   ollama create farming-guide -f ./Modelfile
   ```

   **Run `ollama create` again if you built `farming-guide` with v1:** the Modelfile keeps the model to the documents and gives it a larger context window.

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

   The first run downloads the multilingual embedding model (about 470 MB).

   **Coming from v2?** Delete the old `vector_db/` folder first (`rmdir /s /q vector_db` on Windows). v3 uses a different embedding model, so the old knowledge base can't be reused.

4. **Check the answer-or-refuse tests:**

   ```bash
   python test_questions.py
   ```

5. **Start Farmora:**

   ```bash
   python app.py
   ```

   Open **http://127.0.0.1:5050**. Press Ctrl + C in the terminal to stop the server.

## How v3 works

### Answering from the documents (`ingest.py`, `retrieve.py`)

1. **Sections, not blind cuts.** The document is already divided into sections, each starting with a line like `[Topic: … | Subject: … | Document: … | Section: …]`. `ingest.py` keeps every section whole, and also cuts it into small overlapping passages (400 characters, 80 overlap). The embedding model, `paraphrase-multilingual-MiniLM-L12-v2`, reads only about the first 128 tokens of a text, so the search compares the question with these small passages, and the model is given the *whole* section they belong to.
2. **Word mapping.** Before searching, words from `CROP_GROUPS` that the documents don't use are mapped to ones they do: "what is pigery" is searched as "what is pigery hog".
3. **Relevance filtering.** Each section is scored by its best passage (cosine similarity, 0–1). If even the best score is below `MIN_RELEVANCE`, Farmora refuses without asking the model. Otherwise it keeps sections within `SCORE_WINDOW` (0.12) of the best one, up to 6 sections and 12,000 characters, and adds a section's "(continued)" neighbour.
4. **Crop and animal check.** If the question names crops or animals and none of them appear in the chosen sections, Farmora refuses. If only some are missing, the model is told it knows nothing about them and must say so in one sentence.
5. **Grounded prompt.** Each section is labelled with its crop or animal and topic. The model is told to use only these sections, not to apply advice for one crop to another, to answer only the parts it can support, and to refuse with the fixed sentence when they cover nothing. It is also asked for complete, well-organised answers: headings, every step in order, quantities, examples and precautions.
6. **Natural voice.** The model is given the sections as its own "farming knowledge", without numbered labels, and told never to mention where its knowledge comes from. As a safety net, `AnswerCleaner` in `retrieve.py` removes leftovers such as "According to [Excerpt 5]," or "The question asks ..." while the answer streams.
7. **Refusals.** Every refusal, whether from the code or from the model, is followed by `TOPICS_HINT`, the list of topics Farmora can help with.
8. **Checks.** Numbers in an answer that don't appear in the sections are printed in the terminal and written to `unverified_numbers.log`. Follow-up suggestions are only shown if the documents can answer them.

### Profanity

Profanity is removed before searching, using the English and Filipino list in `PROFANE_WORDS` (`retrieve.py`).

| Message | Reply |
|---|---|
| Profanity with a farming question the documents cover | Calm opening line, then the answer |
| Profanity with a question the documents don't cover | Calm opening line, then the refusal and topic list |
| Only profanity, or fewer than 3 other words | Calm, supportive reply asking what's happening on the farm |

### Testing (`test_questions.py`)

The script runs each question through the same search and crop check the app uses, but doesn't call the language model, and prints PASS or FAIL with the best relevance score:

```
PASS  score 0.71  expected answer  got answer  How do I prepare the land for hybrid rice?
PASS  score 0.52  expected refuse  got refuse  what is the best weather to plant mango
```

- **Add a test for every bad answer** you find in the app, as a new line in `TESTS`.
- **Run the tests after any change** to `MIN_RELEVANCE`, `CROP_GROUPS`, the embedding model or the documents.
- **To tune `MIN_RELEVANCE`,** set it roughly halfway between the lowest score of an "answer" test and the highest score of a "refuse" test.

### Database (`database.py`)

SQLite comes with Python, so no extra package is needed. The database file `farmora.db` is created automatically on first run.

| Table | Columns |
|---|---|
| `chats` | `id`, `title`, `created_at`, `updated_at` |
| `messages` | `id`, `chat_id`, `role` (`user` / `assistant`), `content`, `stopped`, `sources` (JSON list), `created_at` |

Deleting a chat also deletes its messages (`ON DELETE CASCADE`). An older `farmora.db` gets the `sources` column automatically. To start over with no history, stop the server and delete `farmora.db`.

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
| `MIN_RELEVANCE` | `retrieve.py` | Below this the documents can't answer. Tune it with `test_questions.py` after changing the embedding model or documents |
| `SCORE_WINDOW` / `MAX_SECTIONS` | `retrieve.py` | `0.12` / `6` sections per question |
| `MAX_CONTEXT_CHARACTERS` | `retrieve.py` | `12000` characters of document text |
| `CONTEXT_WINDOW` / `MAX_ANSWER_TOKENS` | `retrieve.py` | `8192` / `2048` tokens |
| `CROP_GROUPS` | `retrieve.py` | Crops and animals for the crop check and word mapping |
| `TOPICS_HINT` | `retrieve.py` | Topic list shown after refusals |
| `PROFANE_WORDS` | `retrieve.py` | English and Filipino profanity list |
| `STARTER_QUESTIONS` | `retrieve.py` | 10 farming questions |
| `EMBEDDING_MODEL` | `ingest.py` | `paraphrase-multilingual-MiniLM-L12-v2` (run `ingest.py` after changing) |
| `PASSAGE_SIZE` / `PASSAGE_OVERLAP` | `ingest.py` | `400` / `80` characters (run `ingest.py` after changing) |
| `HISTORY_LIMIT` | `app.py` | Last `10` messages sent as context |
| `port` | `app.py` (last line) | `5050` |
| `TITLE_LENGTH` | `app.py` | Chat titles cut at `40` characters |

## Notes

- **The crop check only knows listed crops.** A crop or animal missing from `CROP_GROUPS` falls back to the relevance check alone. Add a row when you find one.
- **Passing mentions can slip through.** A crop mentioned only once, for example mango as an ingredient in a fruit juice recipe, passes the check if that exact section is found.
- **Follow-up suggestions** use one extra model call after each answer, so on slow computers they can take a few seconds to appear. They're skipped after refusals, errors and stopped answers.
- **All chats are shared** by everyone who opens the app on this server. It's designed for running locally on one computer.
- **Internet is needed** while using the page, because Tailwind CSS, marked and DOMPurify load from a CDN (marked and DOMPurify are pinned to tested versions).
- **Small model, strict rules.** Llama 3 8B follows the grounding rules well, but no prompt can fully stop a model from adding a detail. Review `unverified_numbers.log` after testing.
- **Before deploying,** set `debug=False` in `app.run()`.