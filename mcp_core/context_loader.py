import json
from pathlib import Path
from typing import Dict, Any

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


def load_mcp_config(filepath="mcp_core/mcp.json") -> Dict[str, Any]:
    """Membaca konfigurasi server MCP remote dengan Fallback."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Gagal memuat {filepath} ({str(e)}). Menggunakan fallback konteks kosong.")
        return {}


def _build_vector_store(directory_path: str):
    """Membaca markdown, memecahnya menjadi chunks, dan menyimpannya di FAISS in-memory."""
    path = Path(directory_path)
    if not path.exists():
        return None

    all_text = ""
    for md_file in path.rglob("*.md"):
        with open(md_file, 'r', encoding='utf-8') as f:
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


def get_relevant_context(user_input: str, directory_type: str) -> str:
    """Menarik 3 chunk paling relevan berdasarkan user_input dari FAISS."""
    if _vector_stores[directory_type] is None:
        dir_path = "ayesh/rules" if directory_type == "rules" else "ayesh/skills"
        _vector_stores[directory_type] = _build_vector_store(dir_path)

    vs = _vector_stores[directory_type]
    if vs is None:
        return ""

    docs = vs.similarity_search(user_input, k=3)
    return "\n\n".join([doc.page_content for doc in docs])


def get_full_agent_context(user_input: str = "") -> Dict[str, Any]:
    """Menggabungkan MCP config, RAG rules, dan RAG skills menjadi satu konteks relevan."""
    mcp_servers = load_mcp_config()

    rules_text = get_relevant_context(user_input, "rules") if user_input else ""
    skills_text = get_relevant_context(user_input, "skills") if user_input else ""

    return {
        "mcp_config": mcp_servers,
        "rules_text": rules_text,
        "skills_text": skills_text,
    }
