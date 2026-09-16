import json
import os
from pathlib import Path
from typing import Dict, Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import CharacterTextSplitter

# Inisialisasi embeddings sekali saja untuk efisiensi
_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Global cache untuk in-memory vector stores
_vector_stores = {
    "rules": None,
    "skills": None
}

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

    # Pecah teks menjadi paragraf/chunk
    text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = text_splitter.split_text(all_text)
    
    if not docs:
        return None

    return FAISS.from_texts(docs, _embeddings)

def get_relevant_context(user_input: str, directory_type: str) -> str:
    """Menarik 3 chunk paling relevan berdasarkan user_input dari FAISS."""
    global _vector_stores
    
    # Lazy loading vector store
    if _vector_stores[directory_type] is None:
        dir_path = "rules" if directory_type == "rules" else "skills"
        _vector_stores[directory_type] = _build_vector_store(dir_path)
    
    vs = _vector_stores[directory_type]
    if vs is None:
        return ""
    
    # Ambil 3 dokumen paling relevan
    docs = vs.similarity_search(user_input, k=3)
    return "\n\n".join([doc.page_content for doc in docs])

def get_full_agent_context(user_input: str = "") -> Dict[str, Any]:
    """Menggabungkan MCP config, RAG rules, dan RAG skills menjadi satu konteks relevan."""
    mcp_servers = load_mcp_config()
    
    # Jika user_input ada, gunakan RAG. Jika tidak, return string kosong/default.
    rules_text = get_relevant_context(user_input, "rules") if user_input else ""
    skills_text = get_relevant_context(user_input, "skills") if user_input else ""

    return {
        "mcp_config": mcp_servers,
        "rules_text": rules_text,
        "skills_text": skills_text
    }