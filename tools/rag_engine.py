"""RAG Engine: Ingestion dokumen & retrieval menggunakan FAISS + HuggingFace Embeddings."""

import os
from pathlib import Path
import dotenv

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.logger import setup_logger

logger = setup_logger("rag_engine")
dotenv.load_dotenv()


DATA_DIR = Path(__file__).parent.parent / "data"
FAISS_INDEX_DIR = Path(__file__).parent.parent / "faiss_index"

_embeddings = None
_vectorstore = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )
    return _embeddings


def ingest_documents() -> None:
    """Baca semua .txt di data/, split, embed, simpan ke FAISS."""
    logger.info(f"Memuat dokumen dari {DATA_DIR}...")
    documents = []
    for txt_file in DATA_DIR.glob("*.txt"):
        loader = TextLoader(str(txt_file), encoding="utf-8")
        documents.extend(loader.load())
    logger.info(f"{len(documents)} dokumen dimuat.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    logger.info(f"Terpecah menjadi {len(chunks)} chunks.")

    embeddings = _get_embeddings()
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(str(FAISS_INDEX_DIR))
    logger.info(f"Index FAISS disimpan ke {FAISS_INDEX_DIR}")


def _get_vectorstore() -> FAISS:
    global _vectorstore
    if _vectorstore is None:
        if not FAISS_INDEX_DIR.exists():
            raise RuntimeError(
                "FAISS index belum ada. Jalankan ingest_documents() dulu."
            )
        embeddings = _get_embeddings()
        _vectorstore = FAISS.load_local(
            str(FAISS_INDEX_DIR),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    return _vectorstore


def get_relevant_context(query: str, k: int = 2) -> str:
    """Cari konteks relevan dari FAISS berdasarkan query."""
    vectorstore = _get_vectorstore()
    docs = vectorstore.similarity_search(query, k=k)
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)
