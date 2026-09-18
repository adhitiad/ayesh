"""Helper teks bersama: normalisasi konten LLM/MCP yang bentuknya tak konsisten.

LangChain/Gemini kadang mengembalikan str, kadang list of blocks
(dict {"type": "text", "text": ...}, str, atau objek dengan atribut .text).
Satu fungsi untuk semua situs (dulu 7 duplikasi inline).
"""


def extract_text(content, sep: str = "\n") -> str:
    """Ubah str | list blok | objek .text → str. Tak pernah raise."""
    try:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for x in content:
                if isinstance(x, dict):
                    if x.get("type") == "text":
                        parts.append(str(x.get("text", "")))
                    elif "text" in x:
                        parts.append(str(x["text"]))
                elif isinstance(x, str):
                    parts.append(x)
                elif hasattr(x, "text"):
                    parts.append(str(x.text))
                else:
                    parts.append(str(x))
            return sep.join(p for p in parts if p)
        if hasattr(content, "text"):
            return str(content.text)
        return str(content)
    except Exception:
        try:
            return str(content)
        except Exception:
            return ""
