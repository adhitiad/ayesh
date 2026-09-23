"""RAG retrieval dengan fallback vektor FAISS.

Primary: similarity search FAISS + HuggingFace embeddings atas data + .ayesh.
Fallback: TF-IDF token overlap sederhana bila vektor tidak tersedia.
"""

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

STOPWORDS = frozenset(
    [
        "yang",
        "dan",
        "di",
        "ke",
        "dari",
        "untuk",
        "dengan",
        "pada",
        "adalah",
        "ini",
        "itu",
        "sebagai",
        "dalam",
        "oleh",
        "karena",
        "atau",
        "juga",
        "tidak",
        "ada",
        "akan",
        "telah",
        "sudah",
        "bisa",
        "dapat",
        "harus",
        "agar",
        "supaya",
        "jika",
        "kalau",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "as",
        "by",
        "from",
        "at",
        "an",
        "a",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "yang",
        "saya",
        "kamu",
        "anda",
        "dia",
        "mereka",
        "kita",
        "kami",
        "nya",
        "lah",
        "kah",
        "pun",
        "tak",
        "jangan",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
CHUNK_SIZE = 600

_vector_store = None
_embeddings = None


def _tokens(text: str) -> set:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in STOPWORDS}


def _chunks(text: str, source: str, size: int = CHUNK_SIZE) -> list:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 > size and buf:
            out.append((source, buf))
            buf = ""
        buf = f"{buf}\n{p}".strip() if buf else p
    if buf:
        out.append((source, buf))
    return out


def load_corpus(root: Path | None = None) -> list:
    """Muat (source, chunk) dari data/*.txt + .ayesh/rules + .ayesh/skills."""
    root = root or _PROJECT_ROOT
    corpus = []
    for pattern in ("data/*.txt", ".ayesh/rules/*.md", ".ayesh/skills/*.md"):
        for f in sorted((root).glob(pattern)):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = str(f.relative_to(root))
            corpus.extend(_chunks(text, rel))
    return corpus


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return _embeddings


def _ensure_vector_store(root: Path | None = None):
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    try:
        from langchain.schema import Document
        from langchain_community.vectorstores import FAISS
        from langchain_text_splitters import CharacterTextSplitter

        corpus = load_corpus(root)
        if not corpus:
            return None

        docs = []
        for source, chunk in corpus:
            docs.append(Document(page_content=chunk, metadata={"source": source}))

        splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        split_docs = []
        for d in docs:
            parts = splitter.split_text(d.page_content)
            for p in parts:
                split_docs.append(Document(page_content=p, metadata=d.metadata))

        if not split_docs:
            return None

        _vector_store = FAISS.from_documents(split_docs, _get_embeddings())
        return _vector_store
    except Exception:
        _vector_store = None
        return None


def retrieve(query: str, top_k: int = 3, min_overlap: int = 2, root: Path | None = None) -> list:
    """Return [(source, chunk, skor)] terbaik. Kosong bila tidak relevan."""
    if not query.strip():
        return []

    store = _ensure_vector_store(root)
    if store is not None:
        try:
            results = store.similarity_search_with_score(query, k=top_k)
            out = []
            for doc, score in results:
                source = doc.metadata.get("source", "unknown")
                out.append((source, doc.page_content, float(score)))
            if out:
                return out
        except Exception:  # nosec B110
            pass  # intentionally silent: FAISS optional, fallback to TF-IDF

    qtokens = _tokens(query)
    if not qtokens:
        return []
    scored = []
    for source, chunk in load_corpus(root):
        score = len(qtokens & _tokens(chunk))
        stem = Path(source).stem.replace("-", " ").replace("_", " ")
        if stem and stem in query.lower():
            score += 2
        if score >= min_overlap:
            scored.append((source, chunk, score))
    scored.sort(key=lambda x: -x[2])
    return scored[:top_k]


def build_references(query: str, top_k: int = 3) -> str:
    """Blok '## Referensi' siap injeksi prompt. String kosong bila tak relevan."""
    hits = retrieve(query, top_k=top_k)
    if not hits:
        return ""
    lines = ["## Referensi (dokumen internal, prioritaskan bila relevan):"]
    for source, chunk, score in hits:
        snippet = chunk[:500]
        lines.append(f"\n### {source} (skor {score})\n{snippet}")
    return "\n".join(lines)
