from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document



loader = TextLoader(
    "documents/combined_agriculture_documents.md",
    encoding="utf-8"
)

documents = loader.load()


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

# Combine all PDF pages into one document
combined_text = "\n\n".join(
    document.page_content
    for document in documents
)

combined_document = Document(
    page_content=combined_text,
    metadata={"source": "Farm Planning and Organic Agriculture"}
)

# Split the combined document into chunks
chunks = text_splitter.split_documents([combined_document])

print("\nTotal Chunks:", len(chunks))

for i, chunk in enumerate(chunks[:5]):
    print(f"\n========== CHUNK {i + 1} ==========")
    print("Page:", chunk.metadata.get("page"))
    print(chunk.page_content)

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vector_store = Chroma.from_documents(
    documents=chunks,
    embedding=embedding_model,
    persist_directory="vector_db"
)

print("\nSuccessfully stored document embeddings in ChromaDB!")