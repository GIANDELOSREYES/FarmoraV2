# retrieve.py
# Farmora's RAG engine: it finds the right sections of the farming
# documents and asks the farming-guide model to answer from them.
#
# Steps for every question:
#   1. Rewrite a follow-up question so it makes sense on its own.
#   2. Search the knowledge base and keep only relevant sections.
#   3. Ask the model to answer using only those sections.
#   4. Send the names of the documents used (shown as "Sources").

import json
import random
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from ingest import (
    PASSAGES_COLLECTION,
    SECTIONS_COLLECTION,
    load_embedding_model,
    open_collection
)


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

MODEL_NAME = "farming-guide"   # the model built from the Modelfile

# Retrieval. Scores go from 0 (unrelated) to 1 (same meaning).
# They were checked against the documents: questions the documents
# answer score about 0.50-0.85, unrelated questions below 0.47.
PASSAGES_TO_SEARCH = 24        # passages compared with each question
MIN_RELEVANCE = 0.48           # below this, the documents can't answer
SCORE_WINDOW = 0.12            # keep sections close to the best match
MAX_SECTIONS = 6               # most sections given to the model
MAX_CONTEXT_CHARACTERS = 12000 # about 3,000 tokens of document text

# How much of the conversation the model sees when answering
HISTORY_FOR_ANSWER = 4         # messages
HISTORY_ANSWER_LENGTH = 700    # characters kept from each earlier answer

# Model settings. Ollama's default context window (2,048 tokens) is too
# small: long prompts were cut silently, so the model lost its
# instructions or the document text. Llama 3 supports 8,192 tokens.
CONTEXT_WINDOW = 8192
MAX_ANSWER_TOKENS = 2048

# The one sentence Farmora uses when it can't answer. The system prompt
# below tells the model to use the same sentence.
NO_INFO_ANSWER = "I'm sorry, but I do not have sufficient information to answer your question."

# Profanity: Farmora stays calm instead of refusing or copying the words.
# Whole words only, so words like "shiitake" are not matched.
PROFANE_WORDS = [
    # English
    r"fuck\w*", r"motherfuck\w*", r"shit", r"shitty", r"bullshit", r"bitch\w*",
    r"bastards?", r"assholes?", r"dickhead", r"damn\w*", r"crap", r"crappy",
    r"wtf", r"stfu", r"pissed", r"screw you",
    # Filipino
    r"putang ?ina\w*", r"tang ?ina\w*", r"kingina", r"puta", r"gago", r"gaga",
    r"ulol", r"bobo", r"tanga", r"punyeta", r"pakshet", r"tarantado"
]
PROFANITY_PATTERN = re.compile(r"\b(" + "|".join(PROFANE_WORDS) + r")\b", re.IGNORECASE)

# Reply when the message is only frustration or insults
CALM_ANSWER = (
    "I can tell you're frustrated, and that's completely understandable. "
    "Farming problems can be stressful. Let's take it one step at a time.\n\n"
    "Tell me what's happening: the crop or animal, what you're seeing, "
    "and when it started. I'll look for what my farming documents say about it."
)

# Added before the answer when a farming question includes profanity
CALM_OPENING = "I understand this is frustrating. Let's work through it together.\n\n"

GREETING_ANSWER = (
    "Hello! I'm Farmora, your farming guide. Ask me about crops, soil, "
    "fertilizers, composting, pests, gardening or raising animals, and "
    "I'll answer from my farming documents."
)

THANKS_ANSWER = "You're welcome! Let me know if you have another farming question."

GREETING_PATTERN = re.compile(
    r"^(hi|hello|hey|good (morning|afternoon|evening|day)|kumusta|musta)\b[\s!.,?]*(farmora)?[\s!.]*$",
    re.IGNORECASE
)
THANKS_PATTERN = re.compile(
    r"^(thanks|thank you|thank you so much|salamat|ok|okay|great|nice)[\s!.,]*(farmora)?[\s!.]*$",
    re.IGNORECASE
)

# Sent to the browser after the answer, followed by the list of
# documents used (must match script.js)
SOURCES_MARKER = "[[FARMORA_SOURCES]]"

# Questions shown on the welcome screen (4 are picked at random).
# Every one of these is answered by the documents.
STARTER_QUESTIONS = [
    "How do I prepare the land for hybrid rice?",
    "What are the symptoms of nitrogen deficiency in rice?",
    "How do I make compost at home?",
    "What is green manuring and what are its benefits?",
    "How do I grow strawberry runners?",
    "What are the benefits of an integrated farming system?",
    "How do I grow tomatoes?",
    "What is mokusaku and how is it used?",
    "How do I raise organic chickens?",
    "How can I prevent African swine fever?"
]


# ---------------------------------------------------------------
# Load the embedding model, the vector database and the AI model
# ---------------------------------------------------------------

embedding_model = load_embedding_model()

passages = open_collection(PASSAGES_COLLECTION, embedding_model)
sections = open_collection(SECTIONS_COLLECTION, embedding_model)

# Writes the answers
answer_llm = ChatOllama(
    model=MODEL_NAME,
    temperature=0.2,
    num_ctx=CONTEXT_WINDOW,
    num_predict=MAX_ANSWER_TOKENS
)

# Small jobs: rewriting questions and suggesting follow-ups
helper_llm = ChatOllama(
    model=MODEL_NAME,
    temperature=0.1,
    num_ctx=4096,
    num_predict=200
)

if len(passages.get(limit=1)["ids"]) == 0:
    print("\n[Farmora] The knowledge base is empty. Run: python ingest.py\n")


# ---------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------

def get_starter_questions():
    return random.sample(STARTER_QUESTIONS, 4)


def is_refusal(answer):
    return answer.strip().startswith("I'm sorry")


def format_history(history, answer_length=None):
    # Turns the list of messages into text like:
    #   User: What is mulching?
    #   Farmora: Mulching is ...
    if len(history) == 0:
        return "(no previous messages)"

    lines = []

    for message in history:
        if message["role"] == "user":
            lines.append("User: " + message["content"])
        else:
            content = message["content"]
            if answer_length and len(content) > answer_length:
                content = content[:answer_length].rstrip() + " ..."
            lines.append("Farmora: " + content)

    return "\n".join(lines)


def remove_profanity(text):
    # Returns the text without profanity, and whether any was found
    cleaned, count = PROFANITY_PATTERN.subn(" ", text)
    cleaned = " ".join(cleaned.split())
    return cleaned, count > 0


def small_talk_answer(question):
    # Greetings and thanks don't need a document search
    text = question.strip()

    if GREETING_PATTERN.match(text):
        return GREETING_ANSWER
    if THANKS_PATTERN.match(text):
        return THANKS_ANSWER
    return None


# ---------------------------------------------------------------
# Step 1: Rewrite follow-up questions
# ---------------------------------------------------------------

def clean_rewrite(text, question):
    # Keep only the first line and remove labels the model may add
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if len(lines) == 0:
        return question

    rewritten = re.sub(r"^(standalone question|rewritten question|question)\s*:\s*",
                       "", lines[0], flags=re.IGNORECASE)
    rewritten = rewritten.strip().strip('"').strip()

    # A very long "rewrite" is probably an answer, not a question
    if rewritten == "" or len(rewritten) > max(300, len(question) * 4):
        return question
    return rewritten


def rewrite_question(question, history):
    # The first question in a chat doesn't need rewriting
    if len(history) == 0:
        return question

    messages = [
        SystemMessage(content=(
            "You rewrite follow-up questions so they can be understood "
            "without the conversation. You never answer questions."
        )),
        HumanMessage(content=f"""Conversation history:
{format_history(history[-6:], answer_length=400)}

Latest user question:
{question}

Rewrite the latest user question as one standalone question. Replace words
like "it", "that", "this crop" or "the second step" with what they refer to
in the conversation. If the question is already clear on its own, return it
unchanged. Return only the question on one line, nothing else.""")
    ]

    try:
        rewritten = clean_rewrite(helper_llm.invoke(messages).content, question)
    except Exception as problem:
        print("\n[Farmora] Could not rewrite the question:", problem, "\n")
        return question

    print("\n[Farmora] Standalone question:", rewritten)
    return rewritten


# ---------------------------------------------------------------
# Step 2: Find the relevant sections of the documents
# ---------------------------------------------------------------

def base_section_name(name):
    return re.sub(r"\s*\(continued\)\s*$", "", name, flags=re.IGNORECASE).strip().lower()


def search_sections(search_question):
    # Searches the small passages, then scores each section by its
    # best passage. Returns [(score, metadata)], best first.
    results = passages.similarity_search_with_relevance_scores(
        search_question,
        k=PASSAGES_TO_SEARCH
    )

    best = {}

    for document, score in results:
        section_id = document.metadata["section_id"]

        if section_id not in best or score > best[section_id][0]:
            best[section_id] = (score, document.metadata)

    return sorted(best.values(), key=lambda item: item[0], reverse=True)


def find_neighbours(metadata):
    # The PDFs were converted to text, so one topic sometimes continues
    # into the next section with the same name, e.g. "Land Preparation"
    # followed by "Land Preparation (continued)".
    found = sections.get(
        where={"$and": [
            {"document": metadata["document"]},
            {"position": {"$in": [metadata["position"] - 1, metadata["position"] + 1]}}
        ]}
    )

    neighbours = []
    for neighbour in found["metadatas"]:
        if base_section_name(neighbour["section"]) == base_section_name(metadata["section"]):
            neighbours.append(neighbour)
    return neighbours


def find_context(search_question):
    # Returns the sections the model should read, as a list of
    # {"document", "section", "subject", "text", "score"}.
    # An empty list means the documents can't answer the question.
    ranked = search_sections(search_question)

    print("\n========== RETRIEVAL ==========")
    print("Search question:", search_question)

    for score, metadata in ranked[:10]:
        print(f"  {score:.3f}  {metadata['document']} / {metadata['section']}")

    if len(ranked) == 0 or ranked[0][0] < MIN_RELEVANCE:
        print("No section is relevant enough.")
        print("===============================\n")
        return []

    # Keep sections that are almost as relevant as the best one
    cutoff = max(MIN_RELEVANCE - 0.03, ranked[0][0] - SCORE_WINDOW)
    chosen = [(score, metadata) for score, metadata in ranked if score >= cutoff]
    chosen = chosen[:MAX_SECTIONS]

    # Add continued sections next to the two best matches
    chosen_ids = {metadata["section_id"] for _, metadata in chosen}
    for score, metadata in list(chosen[:2]):
        for neighbour in find_neighbours(metadata):
            if neighbour["section_id"] not in chosen_ids:
                chosen.append((score - 0.01, neighbour))
                chosen_ids.add(neighbour["section_id"])

    # Read the full sections
    texts = sections.get(ids=list(chosen_ids))
    text_by_id = dict(zip(texts["ids"], texts["documents"]))

    # Fill the space with the most relevant sections first
    context = []
    used = 0

    for score, metadata in chosen:
        text = text_by_id.get(metadata["section_id"], "")
        room = MAX_CONTEXT_CHARACTERS - used

        if text == "" or room < 300:
            continue
        if len(text) > room:
            text = text[:room].rsplit("\n", 1)[0] + "\n[...]"

        used = used + len(text)
        context.append({
            "document": metadata["document"],
            "section": metadata["section"],
            "subject": metadata["subject"],
            "position": metadata["position"],
            "score": score,
            "text": text
        })

    # Show sections from the same document together and in their
    # original order, so steps that run across sections stay in order
    document_rank = {}
    for item in context:
        document_rank.setdefault(item["document"], len(document_rank))
    context.sort(key=lambda item: (document_rank[item["document"]], item["position"]))

    print(f"\nUsing {len(context)} sections ({used} characters):")
    for item in context:
        print(f"  {item['score']:.3f}  {item['document']} / {item['section']}")
    print("===============================\n")

    return context


def format_context(context):
    blocks = []

    for number, item in enumerate(context, start=1):
        blocks.append(
            f"[Excerpt {number}] Document: {item['document']} | "
            f"Subject: {item['subject']} | Section: {item['section']}\n"
            f"{item['text']}"
        )

    return "\n\n".join(blocks)


def list_sources(context):
    sources = []
    for item in context:
        if item["document"] not in sources:
            sources.append(item["document"])
    return sources


# ---------------------------------------------------------------
# Step 3: Build the prompt and stream the answer
# ---------------------------------------------------------------

SYSTEM_PROMPT = """You are Farmora, an agricultural information assistant for farmers, students and gardeners.

You answer ONLY from the DOCUMENT EXCERPTS given with each question. They come from Department of Agriculture and Agricultural Training Institute extension materials.

GROUNDING RULES (most important)
1. Every fact, number, rate, dose, timing, measurement, name and step in your answer must come from the excerpts. Copy quantities and units exactly as written.
2. Do not use your own knowledge, assumptions or general farming advice to add details, even if you think they are true. If the excerpts don't say it, don't write it.
3. Pay attention to which document and crop each excerpt is about. If the user asks about one crop and an excerpt is about a different crop, do not present it as advice for the user's crop. You may mention it only if you clearly say which crop it is for.
4. Earlier Farmora answers in the conversation are not a source of facts. Use the conversation only to understand what the user is asking.
5. Never invent statistics, recommendations, procedures, chemical names, fertilizer rates or pesticide doses.

WHEN THE EXCERPTS ARE NOT ENOUGH
- If the excerpts fully answer the question, give a complete answer.
- If they answer only part of it, answer that part fully. Do not guess those parts. Do not add a separate section explaining what the documents do not cover.
IMPORTANT:
- If the excerpts do not answer the question at all, or the question is not about agriculture, reply with exactly this sentence and nothing else:
I'm sorry, but I do not have sufficient information to answer your question.

HOW TO WRITE THE ANSWER
- Be thorough. Include every relevant detail the excerpts give: explanations, reasons, quantities, timings, examples, varieties, materials, precautions and warnings. Do not shorten the answer or leave out useful information that is in the excerpts.
- Explain concepts: say what something is, why it matters and how it works, as far as the excerpts explain it. Don't stop at a one-line definition.
- Answer every part of the question.
- Start with a short overview (1-3 sentences) that directly answers the question. When you cannot answer the question, explicitly state that you do not have enough information for it.
 Do not say that the answer is not provided in the excerpts.
- Then organise the answer with Markdown headings (###) for each main part.
- Use numbered lists for steps and procedures. Give all the steps in the right order, with their quantities and timings.
- Use bullet points for benefits, types, materials, symptoms or tips. Start each bullet with a **bold label** followed by an explanation.
- Put warnings and precautions in their own "### Precautions" section when the excerpts give any.
- You may name a source document when it helps, e.g. "The *Tomato Production Guide* recommends...". Do not mention excerpt numbers.
- Write clearly and simply. Don't introduce yourself or say you are happy to help.
- The excerpts were copied from PDF leaflets, so some text may be jumbled. Use only what is clear; don't guess what jumbled text means."""


def build_messages(question, search_question, history, context):
    standalone = ""
    if search_question.strip().lower() != question.strip().lower():
        standalone = f"\n(Meaning of the question in this conversation: {search_question})"

    recent_history = history[-HISTORY_FOR_ANSWER:]

    user_message = f"""DOCUMENT EXCERPTS:

{format_context(context)}

CONVERSATION SO FAR (only to understand the question, not a source of facts):
{format_history(recent_history, answer_length=HISTORY_ANSWER_LENGTH)}

QUESTION:
{question}{standalone}

Write a complete, well-organised answer using only the DOCUMENT EXCERPTS above."""

    return [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_message)]


def numbers_not_in_context(answer, context):
    # A quick check for invented numbers, printed in the terminal so
    # they can be reviewed. (It can't catch every invented detail.)
    context_text = " ".join(item["text"] for item in context)
    context_numbers = set(re.findall(r"\d+(?:\.\d+)?", context_text))
    answer_numbers = re.findall(r"\d+(?:\.\d+)?", answer)

    missing = []
    for number in answer_numbers:
        if number not in context_numbers and number not in missing:
            missing.append(number)
    return missing


def generate_response_stream(question, history):
    # This is a generator: "yield" sends each piece of the answer to
    # app.py as soon as the model writes it. The last piece is
    # SOURCES_MARKER followed by the list of documents used.

    # Profanity is removed before searching, so it doesn't spoil the search
    question, has_profanity = remove_profanity(question)

    if has_profanity:
        print("\n[Farmora] Profanity found. Responding calmly.")

    canned = small_talk_answer(question)
    if canned is not None:
        yield canned
        yield SOURCES_MARKER + "[]"
        return

    # Only profanity, with no question left
    if not re.search(r"[A-Za-z]{2}", question):
        yield CALM_ANSWER if has_profanity else NO_INFO_ANSWER
        yield SOURCES_MARKER + "[]"
        return

    search_question = rewrite_question(question, history)
    context = find_context(search_question)

    # Nothing relevant was found: don't let the model guess.
    # An upset user without a farming question gets a calm reply.
    if len(context) == 0:
        yield CALM_ANSWER if has_profanity else NO_INFO_ANSWER
        yield SOURCES_MARKER + "[]"
        return

    if has_profanity:
        yield CALM_OPENING

    messages = build_messages(question, search_question, history, context)

    answer = ""

    for chunk in answer_llm.stream(messages):
        if chunk.content:
            answer = answer + chunk.content
            yield chunk.content

    sources = [] if is_refusal(answer) else list_sources(context)

    print("\n========== MODEL ANSWER ==========")
    print(answer.strip())
    print("==================================")

    missing = numbers_not_in_context(answer, context)
    if missing and not is_refusal(answer):
        print("[Farmora] Check these numbers, they are not in the excerpts:", ", ".join(missing))
    print()

    yield SOURCES_MARKER + json.dumps(sources)


# ---------------------------------------------------------------
# Step 4: Suggest follow-up questions
# ---------------------------------------------------------------

def clean_suggestion(line):
    # Removes numbers, bullets and quotes the model may add,
    # for example "1. What is compost?" becomes "What is compost?"
    line = line.strip()
    line = line.lstrip("0123456789")
    line = line.lstrip(".)-*• ")
    line = line.strip('"')
    return line.strip()


def is_answerable(question):
    # Only suggest questions the documents can answer
    ranked = search_sections(question)
    return len(ranked) > 0 and ranked[0][0] >= MIN_RELEVANCE


def suggest_follow_ups(question, answer, sources=None):
    topics = ""
    if sources:
        topics = "\nThe answer came from these documents: " + "; ".join(sources)

    prompt = f"""A farmer asked an agriculture chatbot this question:
{question}

The chatbot answered:
{answer[:2000]}
{topics}

Write 5 short follow-up questions the farmer might ask next.
Each question must be about farming or agriculture, be under
12 words, relate to the answer above, and be about a topic the
same documents are likely to cover.

Return ONLY the questions, one per line, with no numbering,
no bullet points, and no other text."""

    response = helper_llm.invoke(prompt).content

    suggestions = []

    for line in response.split("\n"):
        line = clean_suggestion(line)

        # Keep only real questions that the documents can answer
        if len(line) > 8 and line.endswith("?") and line not in suggestions:
            if is_answerable(line):
                suggestions.append(line)

        if len(suggestions) == 3:
            break

    return suggestions


# ---------------------------------------------------------------
# Terminal mode: run "python retrieve.py" to chat without the website
# ---------------------------------------------------------------

if __name__ == "__main__":

    history = []

    while True:
        question = input("\nAsk your farming question: ")

        if question.lower() in ["exit", "quit", "bye"]:
            break

        print("\nFarmora: ", end="")
        answer = ""

        for chunk in generate_response_stream(question, history):
            if chunk.startswith(SOURCES_MARKER):
                sources = json.loads(chunk[len(SOURCES_MARKER):])
                if sources:
                    print("\n\nSources:", "; ".join(sources))
                continue
            answer = answer + chunk
            print(chunk, end="", flush=True)

        print()

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
