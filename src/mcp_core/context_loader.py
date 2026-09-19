from pathlib import Path

# Lazy-init globals
_embeddings = None
_vector_stores = {"rules": None, "skills": None}


def _get_embeddings():
    """Lazy init HuggingFace embeddings hanya saat dibutuhkan."""
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return _embeddings


def _build_vector_store(directory_path: str):
    """Membaca markdown, memecahnya menjadi chunks, dan menyimpannya di FAISS in-memory."""
    path = Path(directory_path)
    if not path.exists():
        return None

    all_text = ""
    for md_file in path.rglob("*.md"):
        with open(md_file, encoding="utf-8") as f:
            all_text += f"\n--- [FILE: {md_file.name}] ---\n{f.read()}\n"

    if not all_text.strip():
        return None

    from langchain_community.vectorstores import FAISS
    from langchain_text_splitters import CharacterTextSplitter

    text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = text_splitter.split_text(all_text)

    if not docs:
        return None

    return FAISS.from_texts(docs, _get_embeddings())
