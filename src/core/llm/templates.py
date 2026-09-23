"""Library template prompt: simpan & reuse template siap pakai (peran/format).

Dua sumber template:
  1. Bawaan: ``_BUILTIN`` (snippet umum — ringkas, surat resmi, dll.).
  2. File: ``.ayesh/templates/*.md`` otomatis ter-registrasi saat import
     (nama file = nama template), best-effort — folder boleh tidak ada.

Template memakai placeholder ``{nama}``. ``render`` hanya mengisi placeholder
yang tersedia; placeholder tanpa nilai dibiarkan utuh (tidak melempar).
Tidak menyentuh penyusunan system prompt default — murni library utusan.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BUILTIN: dict[str, str] = {
    "ringkas": (
        "Ringkas teks berikut dalam maksimal {max_kata} kata, bahasa {bahasa}, tanpa komentar atau opini:\n\n{teks}"
    ),
    "surat_resmi": (
        "Tulis surat resmi berbahasa {bahasa} dengan struktur lengkap (kopi, "
        "tanggal, nomor, lampiran, perihal, pembuka, isi, penutup, tanda tangan), "
        "untuk keperluan: {keperluan}. Detail tambahan:\n\n{detail}"
    ),
    "intent": (
        "Tentukan intent dari pesan user di bawah. Balas hanya satu kata dari: {daftar_intent}. Pesan:\n{pesan}"
    ),
    "kode_review": (
        "Review kode berikut fokus pada {aspek}. Beri daftar temuan terurut "
        "berdasarkan dampak, masing-masing dengan baris yang relevan.\n\n{kode}"
    ),
    "terjemah": (
        "Terjemahkan teks berikut ke bahasa {bahasa}. Pertahankan nada dan "
        "istilah teknis yang sesuai konteks.\n\n{teks}"
    ),
}

_templates: dict[str, str] = dict(_BUILTIN)

_loaded = False


def _autoload_files() -> None:
    """Registrasi .ayesh/templates/*.md (nama file = nama template). Best-effort."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        base = Path(__file__).resolve().parents[3] / ".ayesh" / "templates"
        if not base.exists():
            return
        for md in sorted(base.glob("*.md")):
            _templates.setdefault(md.stem, md.read_text(encoding="utf-8").strip())
    except Exception as _e:
        logger.debug("autoload templates error: %s", _e)


def register_template(name: str, text: str) -> None:
    """Simpan/ubah template kustom (menimpa bila nama sama)."""
    name = (name or "").strip()
    if not name:
        raise ValueError("nama template tidak boleh kosong")
    _templates[name] = text


class _Fill(dict):
    """dict yang mengembalikan placeholder asli untuk kunci tanpa nilai."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render(name: str, **kwargs) -> str:
    """Render template dengan placeholder yang disediakan; sisanya dibiarkan."""
    template = get_template(name)
    if template is None:
        raise KeyError(f"template tidak dikenal: {name}")
    return template.format_map(_Fill(kwargs))


def get_template(name: str):
    """Ambil teks template (bawaan/file/kustom) atau None bila tak ada."""
    if not _loaded:
        _autoload_files()
    return _templates.get(name)


def list_templates() -> list[str]:
    """Nama semua template terurut abjad."""
    if not _loaded:
        _autoload_files()
    return sorted(_templates)


def delete_template(name: str) -> None:
    """Hapus template kustom. Tolak template bawaan dan nama kosong.

    Raises:
        ValueError: nama kosong atau mencoba menghapus template bawaan.
        KeyError: template tidak dikenal.
    """
    if not _loaded:
        _autoload_files()
    name = (name or "").strip()
    if not name:
        raise ValueError("nama template tidak boleh kosong")
    if name in _BUILTIN:
        raise ValueError(f"template bawaan tidak bisa dihapus: {name}")
    if name not in _templates:
        raise KeyError(f"template tidak dikenal: {name}")
    del _templates[name]
    logger.info("template dihapus: %s", name)


def reset_templates() -> None:
    """Kembalikan hanya template bawaan (untuk test isolasi)."""
    global _loaded
    _templates.clear()
    _templates.update(_BUILTIN)
    _loaded = True
