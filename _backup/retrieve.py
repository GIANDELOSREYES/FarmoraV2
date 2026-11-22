"""
retrieve.py - Farmora's RAG engine

1. rewrite_question()          turns follow-up questions into standalone ones
2. retrieve_context()          finds the most relevant chunks in vector_db/
3. generate_response_stream()  streams the answer word by word
4. suggest_follow_ups()        suggests follow-up questions after an answer
"""

import random
import re

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama

# ---------------------------------------------------------------
# Settings
# ---------------------------------------------------------------

MODEL_NAME = "farming-guide"     # built from the Modelfile
NUMBER_OF_CHUNKS = 5             # chunks retrieved per question

# Phrases the bot should never say to the user
UNWANTED_PHRASES = [
    "the provided information does not contain",
    "the document does not mention",
    "the retrieved context",
    "the available information does not",
    "the database does not contain",
    "according to the provided document"
]

FALLBACK_ANSWER = (
    "I'm sorry, I don't have enough information "
    "to answer that question accurately."
)

# Special marker sent to the browser when a streamed answer
# must be replaced with the fallback answer (see script.js)
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
# Models and vector database
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
# Helpers
# ---------------------------------------------------------------

def get_starter_questions(count=4):
    return random.sample(STARTER_QUESTIONS, count)


def contains_unwanted_phrase(text):

    text_lower = text.lower()

    return any(phrase in text_lower for phrase in UNWANTED_PHRASES)


def format_history(conversation_history):
    """Turn [{'role': ..., 'content': ...}] into readable text."""

    if not conversation_history:
        return "(no previous messages)"

    lines = []

    for message in conversation_history:
        speaker = "User" if message["role"] == "user" else "Farmora"
        lines.append(f"{speaker}: {message['content']}")

    return "\n".join(lines)


def rewrite_question(question, conversation_history):
    """Rewrite a follow-up question into a standalone question."""

    # The first question in a chat has no context to add,
    # so skip the extra model call
    if not conversation_history:
        return question

    history = format_history(conversation_history)

    rewrite_prompt = f"""
    Given the conversation history and the latest user question,
    rewrite the latest question into a standalone question.

    If the question is already understandable without context,
    keep its original meaning.

    Do not answer the question.
    Only return the rewritten question.

    Conversation History:
    {history}

    Latest User Question:
    {question}

    Standalone Question:
    """

    response = llm.invoke(rewrite_prompt)

    return response.content.strip() or question


def retrieve_context(search_question):

    results = vector_store.similarity_search_with_relevance_scores(
        search_question,
        k=NUMBER_OF_CHUNKS
    )

    print("\n========== RETRIEVAL SCORES ==========")
    print("Search Question:", search_question)

    for index, (document, score) in enumerate(results, start=1):
        print(f"\n--- Document {index} ---")
        print(f"Relevance Score: {score:.4f}")
        print(document.page_content)

    print("======================================\n")

    return "\n\n".join(
        document.page_content for document, score in results
    )


def build_prompt(conversation_history, context, search_question):

    conversation_history = format_history(conversation_history)

    prompt = f"""
    You are Farmora, an Agriculture and Farming Guide chatbot.

    Your purpose is to help users understand agricultural topics
    using information from the provided agricultural documents.

    STRICT DOCUMENT-ONLY RULES:

    1. Use ONLY information explicitly supported by the
       AGRICULTURAL INFORMATION provided below.

    2. Do not use your general knowledge, training data, assumptions,
       or outside information to answer agricultural questions.

    3. Do not invent or add:
       - Agricultural facts
       - Benefits or disadvantages
       - Farming practices
       - Procedures or recommendations
       - Fertilizer rates or pesticide dosages
       - Statistics or measurements
       - Explanations not supported by the provided information

    4. You may summarize, simplify, reorganize, and combine information
       from different passages, provided every factual claim remains
       supported by the provided information.

    5. Do not interpret an incomplete statement as though it contains
       information that is not actually provided.

    6. Previous chatbot responses are NOT reliable sources of facts.
       Use conversation history only to understand follow-up questions.

    QUESTION HANDLING:

    1. The following subjects are ALWAYS considered related
       to agriculture and farming:
    
       - Crop production
       - Planting and harvesting
       - Fruit trees and fruit production
       - Soil preparation and soil management
       - Fertilizers and fertilizer application
       - Organic farming
       - Cover cropping and mulching
       - Pest and disease management
       - Irrigation and water management
       - Livestock production
       - Farm planning and management
       - Sustainable agriculture
    
    2. Do not classify a question as unrelated to agriculture
       simply because the provided documents lack information
       about the specific crop, technique, or subject.
    
    3. If the question concerns any agricultural subject,
       treat it as an agriculture-related question.
    
    4. If the question is unrelated to agriculture or farming,
       respond EXACTLY:
    
       I'm sorry, I can only help with farming and agriculture topics.
    
    5. If the question is agriculture-related, examine the
       AGRICULTURAL INFORMATION carefully.
    
    6. If relevant information exists, answer using only
       the supported information.
    
    7. If the information only partially answers the question,
       provide the supported information without inventing
       missing details.
    
    8. If no relevant information exists, respond EXACTLY:
    
       I'm sorry, I don't have enough information to answer that question accurately.
    
    9. Never use general knowledge, assumptions, or outside
       information to fill missing details.

    CONVERSATION HISTORY:
    {conversation_history}

    IMPORTANT:
    The conversation history is provided ONLY to understand
    the context of follow-up questions.

    Do not use previous assistant responses as factual information.

    AGRICULTURAL INFORMATION:
    {context}

    USER QUESTION:
    {search_question}

    ANSWER:
    """
    return prompt


# ---------------------------------------------------------------
# Main functions used by app.py
# ---------------------------------------------------------------

def generate_response_stream(question, conversation_history):
    """Yield the answer piece by piece as the model writes it."""

    search_question = rewrite_question(question, conversation_history)

    context = retrieve_context(search_question)

    prompt = build_prompt(conversation_history, context, search_question)

    response = ""

    for chunk in llm.stream(prompt):

        text = chunk.content

        if not text:
            continue

        response += text

        # If the model starts using an unwanted phrase, stop and
        # tell the browser to replace the answer with the fallback
        if contains_unwanted_phrase(response):

            print("\n========== RAW MODEL RESPONSE (STOPPED) ==========")
            print(response)
            print("==================================================\n")

            yield REPLACE_MARKER + FALLBACK_ANSWER
            return

        yield text

    print("\n========== RAW MODEL RESPONSE ==========")
    print(response.strip())
    print("========================================\n")


def suggest_follow_ups(question, answer, count=3):
    """Ask the model for short follow-up questions the user might ask next."""

    prompt = f"""
    A farmer asked an agriculture chatbot this question:
    {question}

    The chatbot answered:
    {answer}

    Write {count} short follow-up questions the farmer might ask next.
    Each question must be about farming or agriculture, be under
    12 words, and relate to the answer above.

    Return ONLY the questions, one per line, with no numbering,
    no bullet points, and no other text.
    """

    response = llm.invoke(prompt).content

    suggestions = []

    for line in response.splitlines():

        # Remove numbering, bullets and quotes the model may add
        line = re.sub(r'^\s*(\d+[.)]|[-*•])\s*', "", line)
        line = line.strip().strip('"').strip()

        if len(line) > 8 and line.endswith("?"):
            suggestions.append(line)

    return suggestions[:count]


# ---------------------------------------------------------------
# Terminal mode: python retrieve.py
# ---------------------------------------------------------------

if __name__ == "__main__":

    conversation_history = []

    while True:

        question = input("\nAsk your farming question: ")

        if question.lower() in ["exit", "quit", "bye"]:
            break

        if not question.strip():
            continue

        print("\nFarmora: ", end="", flush=True)

        answer = ""

        for chunk in generate_response_stream(question, conversation_history):

            if chunk.startswith(REPLACE_MARKER):
                chunk = chunk[len(REPLACE_MARKER):]
                answer = ""
                print("\n" + chunk, end="", flush=True)
            else:
                print(chunk, end="", flush=True)

            answer += chunk

        print()

        conversation_history.append({"role": "user", "content": question})
        conversation_history.append({"role": "assistant", "content": answer})
