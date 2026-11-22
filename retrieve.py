# retrieve.py
# Farmora's RAG engine: it finds the right parts of the farming PDF
# and asks the farming-guide model to answer from them.

import random

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama


# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

MODEL_NAME = "farming-guide"   # the model built from the Modelfile
NUMBER_OF_CHUNKS = 8           # how many PDF chunks to use per question

# If an answer contains one of these phrases, it is replaced
UNWANTED_PHRASES = [
    "the provided information does not contain",
    "the document does not mention",
    "the retrieved context",
    "the available information does not",
    "the database does not contain",
    "according to the provided document"
]

FALLBACK_ANSWER = "I'm sorry, I don't have enough information to answer that question accurately."

# Sent to the browser to say "replace the answer" (must match script.js)
REPLACE_MARKER = "[[FARMORA_REPLACE]]"

# Questions shown on the welcome screen (4 are picked at random)
STARTER_QUESTIONS = [
    "What are the benefits of cover cropping?",
    "How do I start an organic farm?",
    "What is crop rotation and why is it important?",
    "How can I improve my soil fertility naturally?",
    "How do I control pests without chemicals?",
    "What should I include in a farm plan?",
    "What is composting and how do I make compost?",
    "How does mulching help my crops?",
    "What are the principles of organic agriculture?",
    "How can I conserve water on my farm?"
]


# ---------------------------------------------------------------
# Load the embedding model, the vector database and the AI model
# ---------------------------------------------------------------

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vector_store = Chroma(
    persist_directory="vector_db",
    embedding_function=embedding_model
)

llm = ChatOllama(
    model=MODEL_NAME,
    temperature=0.3
)


# ---------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------

def get_starter_questions():
    return random.sample(STARTER_QUESTIONS, 4)


def has_unwanted_phrase(text):
    text = text.lower()

    for phrase in UNWANTED_PHRASES:
        if phrase in text:
            return True

    return False


def format_history(history):
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
            lines.append("Farmora: " + message["content"])

    return "\n".join(lines)


# ---------------------------------------------------------------
# Step 1: Rewrite follow-up questions
# ---------------------------------------------------------------

def rewrite_question(question, history):
    # The first question in a chat doesn't need rewriting
    if len(history) == 0:
        return question

    rewrite_prompt = f"""
    Given the conversation history and the latest user question,
    rewrite the latest question into a standalone question.

    If the question is already understandable without context,
    keep its original meaning.

    Do not answer the question.
    Only return the rewritten question.

    Conversation History:
    {format_history(history)}

    Latest User Question:
    {question}

    Standalone Question:
    """

    rewritten = llm.invoke(rewrite_prompt).content.strip()

    if rewritten == "":
        return question
    return rewritten


# ---------------------------------------------------------------
# Step 2: Find the most relevant chunks of the PDF
# ---------------------------------------------------------------

def find_context(search_question):
    results = vector_store.similarity_search_with_relevance_scores(
        search_question,
        k=NUMBER_OF_CHUNKS
    )

    print("\n========== RETRIEVAL SCORES ==========")
    print("Search Question:", search_question)

    chunks = []

    for document, score in results:
        print(f"\nRelevance Score: {score:.4f}")
        print(document.page_content)
        chunks.append(document.page_content)

    print("======================================\n")

    return "\n\n".join(chunks)


# ---------------------------------------------------------------
# Step 3: Build the prompt and stream the answer
# ---------------------------------------------------------------

def build_prompt(history, context, search_question):

    conversation_history = format_history(history)

    prompt = f"""
    You are Farmora, a friendly and knowledgeable farming assistant.
    You talk directly to farmers, students and anyone interested in agriculture.

    REFERENCE NOTES (private: the user cannot see these, never mention them):
    {context}

    CONVERSATION SO FAR (only use it to understand follow-up questions):
    {conversation_history}

    QUESTION:
    {search_question}

    HOW TO ANSWER:

    1. Facts
       - Use only facts found in the REFERENCE NOTES.
       - Never invent facts, numbers, fertilizer rates or pesticide doses.
       - Do not treat earlier Farmora answers in the conversation as facts.

    2. Voice
       - Answer the question right away, like a helpful expert talking to a friend.
       - Never introduce yourself. Never write "As Farmora".
       - Never say you are excited, happy or glad to help.
       - Never mention the REFERENCE NOTES, "the information", "the document",
         "the context", "the source" or "the database".
       - Never write phrases like "according to the information",
         "based on the provided", "the document says" or
         "these benefits are supported by".
       - Do not end with a note about where the answer came from.

    3. Format
       - Start with one short sentence that answers the question.
       - For benefits, causes, types or tips: use bullet points,
         each starting with a **bold label** followed by a short explanation.
       - For steps or procedures: use a numbered list, one step per line.
       - Keep sentences short and simple. Avoid long paragraphs.
       - For a simple question, a short answer is enough.

    4. When you can't answer
       - Questions about crops, soil, fertilizers, pests, irrigation, livestock,
         organic farming and farm planning are always farming questions.
       - If the question is not about farming or agriculture, reply exactly:
         I'm sorry, I can only help with farming and agriculture topics.
       - If the REFERENCE NOTES do not contain the answer, reply exactly:
         I'm sorry, I don't have enough information to answer that question accurately.
       - If the notes answer only part of the question, answer that part
         without guessing the rest.
       - These two exact replies are the only time you may use the word "information".

    EXAMPLE

    Question: What are the benefits of cover cropping?

    Bad answer:
    As Farmora, I'm happy to help! According to the provided information,
    cover cropping has several benefits... Please note that these benefits
    are supported by the provided agricultural information.

    Good answer:
    Cover cropping protects and improves your soil in several ways:

    - **Adds organic matter:** The crops break down and enrich the soil.
    - **Controls weeds:** A thick cover crowds out weeds.
    - **Prevents erosion:** Roots hold the soil in place between seasons.

    Now answer the QUESTION.
    """
    return prompt

def generate_response_stream(question, history):
    # This is a generator: "yield" sends each piece of the
    # answer to app.py as soon as the model writes it.

    search_question = rewrite_question(question, history)
    context = find_context(search_question)
    prompt = build_prompt(history, context, search_question)

    answer = ""

    for chunk in llm.stream(prompt):
        answer = answer + chunk.content

        # Stop and send the fallback answer if an unwanted phrase appears
        if has_unwanted_phrase(answer):
            print("\n[Farmora] Unwanted phrase found. Sending fallback answer.\n")
            yield REPLACE_MARKER + FALLBACK_ANSWER
            return

        yield chunk.content

    print("\n========== MODEL ANSWER ==========")
    print(answer.strip())
    print("==================================\n")


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


def suggest_follow_ups(question, answer):
    prompt = f"""
    A farmer asked an agriculture chatbot this question:
    {question}

    The chatbot answered:
    {answer}

    Write 3 short follow-up questions the farmer might ask next.
    Each question must be about farming or agriculture, be under
    12 words, and relate to the answer above.

    Return ONLY the questions, one per line, with no numbering,
    no bullet points, and no other text.
    """

    response = llm.invoke(prompt).content

    suggestions = []

    for line in response.split("\n"):
        line = clean_suggestion(line)

        # Keep only real questions
        if len(line) > 8 and line.endswith("?"):
            suggestions.append(line)

    return suggestions[:3]


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
            if chunk.startswith(REPLACE_MARKER):
                chunk = chunk.replace(REPLACE_MARKER, "")
                answer = ""
            answer = answer + chunk
            print(chunk, end="", flush=True)

        print()

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
