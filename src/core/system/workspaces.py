"""Direktori kerja output & lokasi simpan pilihan user (per session).

Kebijakan:
- File lepas tanpa proyek (laporan, csv, script sekali pakai, dsb.) selalu ke
  folder `output/` di project root (dibuat otomatis bila belum ada).
- Project/kode multi-file: agent WAJIB tanya dulu mau disimpan di mana, lalu
  catat jawaban user via `note_target_dir()` (dipanggil tool `set_target_dir`).
  `tulis_kode` hanya boleh menulis di luar root bila path-nya di dalam direktori
  yang sudah dicatat untuk session berjalan.

Penyimpanan approved-dirs in-memory per session (cukup untuk sesi berjalan;
pilihan user selalu eksplisit per percakapan, jadi tak perlu persisten).
"""

from __future__ import annotations

import os
import threading

OUTPUT_DIRNAME = "output"

_lock = threading.Lock()
_APPROVED: dict[str, set[str]] = {}  # session_id -> set direktori absolut


def project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def output_dir() -> str:
    """Path absolut folder output/ (di dalam project root)."""
    return os.path.join(project_root(), OUTPUT_DIRNAME)


def ensure_output_dir() -> str:
    """Buat folder output/ bila belum ada. Return path absolutnya."""
    path = output_dir()
    os.makedirs(path, exist_ok=True)
    return path


def current_session_id() -> str:
    """Session id berjalan via ContextVar approval (fallback '')."""
    try:
        from src.core.auth.approval import current_session

        return current_session.get() or ""
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("current_session_id error: %s", _e)
        return ""


def _normalize_dir(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def note_target_dir(session_id: str, path: str, create: bool = True) -> tuple:
    """Catat direktori pilihan user untuk session. Return (ok, abs/error).

    - path harus absolut (mis. `F:/bdk`, `F:\\bdk`, `/home/user/proj`).
    - Direktori dibuat bila belum ada (create=True).
    - File sensitif tetap diblokir saat penulisan oleh `_safe_path`.
    """
    p = (path or "").strip().strip('"').strip("'")
    if not p:
        return False, "Error: path kosong. Sebutkan folder tujuan, mis. F:/bdk."
    if not os.path.isabs(p):
        return False, (
            f"Error: '{p}' bukan path absolut. Sebutkan path lengkap, mis. "
            "F:/bdk (Windows) atau /home/user/proj (Linux)."
        )
    ap = os.path.abspath(os.path.normpath(p))
    if create:
        try:
            os.makedirs(ap, exist_ok=True)
        except Exception as e:
            return False, f"Error: folder '{ap}' tak bisa dibuat: {e}"
    elif not os.path.isdir(ap):
        return False, f"Error: folder '{ap}' tidak ada."
    sid = session_id or ""
    with _lock:
        _APPROVED.setdefault(sid, set()).add(_normalize_dir(ap))
    return True, ap


def target_dirs_for(session_id: str) -> set:
    """Set direktori absolut (normalize-case) yang disetujui session ini."""
    with _lock:
        return set(_APPROVED.get(session_id or "", set()))


def is_path_allowed(abs_path: str, session_id: str = "") -> bool:
    """True bila abs_path di dalam project root/output ATAU approved dir session."""
    try:
        ap = os.path.abspath(abs_path)
    except Exception:  # noqa: S110 — is_path_allowed must never raise
        pass
    root = os.path.abspath(project_root())
    if ap == root or ap.startswith(root + os.sep):
        return True
    sid = session_id or current_session_id()
    if not sid:
        return False
    norm = _normalize_dir(ap)
    return any(norm == d or norm.startswith(d + os.sep) for d in target_dirs_for(sid))


def clear_session_targets(session_id: str) -> None:
    """Hapus catatan direktori session (beberesih opsional)."""
    with _lock:
        _APPROVED.pop(session_id or "", None)
