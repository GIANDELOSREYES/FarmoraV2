# ingest.py
# Builds Farmora's knowledge base (the vector_db/ folder) from the
# farming documents.
#
# Run:   python ingest.py
#
# The document is already organised into sections. Each section starts
# with a context line such as:
#   [Topic: Rice Production | Subject: rice | Document: Planting Guide
#    for Hybrid Rice | Section: Irrigation | Chunk: planting-guide-...-002]
#
# Two ChromaDB collections are stored:
#   - SECTIONS: every section, whole. These are what the model reads.
#   - PASSAGES: each section cut into small overlapping passages.
#     These are what the search compares the question with.
#
# Why two? The embedding model only reads the first 256 tokens
# (about 1,000 characters) of a text and ignores the rest, but many
# sections are longer than that. Searching small passages means every
# part of a section can be found; giving the model the whole section
# means it gets the full steps and details, not a cut-off piece.

import re

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ---------------------------------------------------------------
# Settings (retrieve.py uses the same ones)
# ---------------------------------------------------------------

DOCUMENT_FILE = "documents/combined_agriculture_documents.md"
VECTOR_DB_DIR = "vector_db"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

PASSAGE_SIZE = 400      # this model reads about 128 tokens, so passages are shorter
PASSAGE_OVERLAP = 80

PASSAGES_COLLECTION = "farmora_passages"
SECTIONS_COLLECTION = "farmora_sections"

PASSAGE_SIZE = 600      # characters of section text per passage
PASSAGE_OVERLAP = 120   # characters shared by neighbouring passages

# Cosine distance gives relevance scores between 0 and 1
COLLECTION_SETTINGS = {"hnsw:space": "cosine"}

HEADER_PATTERN = re.compile(r"^\[(Topic:.*?)\]\s*$", re.MULTILINE)


def load_embedding_model():
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True}
    )


def open_collection(name, embedding_model):
    return Chroma(
        collection_name=name,
        persist_directory=VECTOR_DB_DIR,
        embedding_function=embedding_model,
        collection_metadata=COLLECTION_SETTINGS
    )


# ---------------------------------------------------------------
# Step 1: Read the document and split it into its sections
# ---------------------------------------------------------------

def parse_header(header):
    # "Topic: A | Subject: b | Document: C" -> {"topic": "A", ...}
    fields = {}

    for part in header.split("|"):
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key.strip().lower()] = value.strip()

    return fields


def read_sections(path):
    with open(path, encoding="utf-8") as file:
        text = file.read()

    # Every section starts with a "### " heading
    blocks = re.split(r"(?m)^(?=### )", text)

    sections = []
    position_in_document = {}

    for block in blocks:
        match = HEADER_PATTERN.search(block)
        if match is None:
            continue   # the catalogue and document introductions

        fields = parse_header(match.group(1))
        document = fields.get("document", "Unknown document")

        # Text after the context line, without "## DOCUMENT" blocks that
        # may follow the last section of a document
        body = block[match.end():]
        body = re.split(r"(?m)^#{1,2} ", body)[0].strip()

        if body == "":
            continue

        position = position_in_document.get(document, 0)
        position_in_document[document] = position + 1

        sections.append({
            "id": fields.get("chunk", f"{document}-{position}"),
            "header": "[" + match.group(1) + "]",
            "body": body,
            "topic": fields.get("topic", ""),
            "subject": fields.get("subject", ""),
            "document": document,
            "section": fields.get("section", ""),
            "position": position
        })

    return sections


# ---------------------------------------------------------------
# Step 2: Cut each section into small passages for searching
# ---------------------------------------------------------------

def make_documents(sections):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=PASSAGE_SIZE,
        chunk_overlap=PASSAGE_OVERLAP
    )

    section_documents = []
    passage_documents = []

    for section in sections:
        metadata = {
            "section_id": section["id"],
            "topic": section["topic"],
            "subject": section["subject"],
            "document": section["document"],
            "section": section["section"],
            "position": section["position"]
        }

        section_documents.append(Document(
            page_content=section["body"],
            metadata=metadata
        ))

        # Each passage starts with the context line, so a passage about
        # "Land Preparation" still says it is about hybrid rice
        for piece in splitter.split_text(section["body"]):
            passage_documents.append(Document(
                page_content=section["header"] + "\n" + piece,
                metadata=metadata
            ))

    return section_documents, passage_documents


# ---------------------------------------------------------------
# Step 3: Store everything in ChromaDB
# ---------------------------------------------------------------

def rebuild_collection(name, documents, embedding_model, ids=None):
    # Start from an empty collection. (Before, running ingest.py twice
    # stored every chunk twice, so searches returned duplicates.)
    old = open_collection(name, embedding_model)
    old.delete_collection()

    store = open_collection(name, embedding_model)

    batch_size = 500
    for start in range(0, len(documents), batch_size):
        batch_ids = None
        if ids is not None:
            batch_ids = ids[start:start + batch_size]
        store.add_documents(documents[start:start + batch_size], ids=batch_ids)

    return store


def remove_old_collection(embedding_model):
    # Farmora v1 stored its chunks in the default "langchain" collection
    try:
        Chroma(
            persist_directory=VECTOR_DB_DIR,
            embedding_function=embedding_model
        ).delete_collection()
    except Exception:
        pass


def main():
    sections = read_sections(DOCUMENT_FILE)
    section_documents, passage_documents = make_documents(sections)

    documents_found = sorted({section["document"] for section in sections})
    lengths = sorted(len(section["body"]) for section in sections)

    print("\nDocuments:", len(documents_found))
    print("Sections: ", len(sections),
          f"(shortest {lengths[0]}, longest {lengths[-1]} characters)")
    print("Passages: ", len(passage_documents))

    print("\nExample passage:\n")
    print(passage_documents[0].page_content)

    embedding_model = load_embedding_model()

    remove_old_collection(embedding_model)

    section_ids = [section["id"] for section in sections]
    rebuild_collection(SECTIONS_COLLECTION, section_documents, embedding_model, section_ids)
    rebuild_collection(PASSAGES_COLLECTION, passage_documents, embedding_model)

    print("\nSuccessfully stored the knowledge base in ChromaDB!")


if __name__ == "__main__":
    main()
