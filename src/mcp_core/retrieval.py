"""RAG ringan tanpa dependensi: retrieval TF-IDF-sederhana atas data + .ayesh.

Skor = jumlah token query berbeda yang muncul di chunk (stopword dibuang).
Hanya chunk dengan skor >= ambang yang dikembalikan, jadi sapaan/obrolan
biasa tidak menambah token sama sekali.
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
            except OSError, UnicodeDecodeError:
                continue
            rel = str(f.relative_to(root))
            corpus.extend(_chunks(text, rel))
    return corpus


def retrieve(query: str, top_k: int = 3, min_overlap: int = 2, root: Path | None = None) -> list:
    """Return [(source, chunk, skor)] terbaik. Kosong bila tidak relevan."""
    qtokens = _tokens(query)
    if not qtokens:
        return []
    scored = []
    for source, chunk in load_corpus(root):
        score = len(qtokens & _tokens(chunk))
        # Bonus bila nama file/skill disebut di query
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
