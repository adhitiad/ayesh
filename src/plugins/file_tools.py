"""Core file tools: tulis_kode, baca_file, info_sistem, set_target_dir."""

import os

from langchain_core.tools import tool

from src.plugins.file_safety import _safe_path
from src.plugins.tool_error import tool_error_from_exception


@tool
def tulis_kode(filepath: str, konten: str, overwrite: bool = False) -> str:
    """Menulis teks atau kode program ke dalam file lokal.

    Args:
        filepath: Path file tujuan.
        konten: Isi teks/kode yang ingin ditulis.
        overwrite: Jika True, timpa file yang sudah ada. Jika False (default), error jika file sudah ada.
    """
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "tulis_kode",
                {"filepath": filepath, "overwrite": overwrite},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return tool_error_from_exception(e)
        if os.path.exists(filepath) and not overwrite:
            return f"Error: File '{filepath}' sudah ada. Gunakan overwrite=True untuk menimpa."
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(konten)
        return f"File berhasil dibuat di {filepath}"
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def baca_file(filepath: str) -> str:
    """Membaca isi dari file lokal (project root/output/ atau direktori pilihan user)."""
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: File tidak ditemukan."
    except Exception as e:
        return f"Error saat membaca file: {e!s}"


@tool
def info_sistem() -> str:
    """Tampilkan spesifikasi mesin lokal: OS, CPU, RAM, partisi/drive, Python,
    GPU, Redis, PostgreSQL. Tanpa argumen. Tanpa akses jaringan/infra berat
    (probe lokal bertimeout singkat, hasil di-cache 5 menit)."""
    try:
        from src.core.system.sysinfo import get_sysinfo_block

        return get_sysinfo_block()
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def set_target_dir(path: str) -> str:
    """Catat direktori kerja pilihan user untuk session ini agar tulis_kode
    boleh menulis di luar project root.

    WAJIB dipanggil SETELAH user menyebut lokasi simpan (mis. "F:/bdk") dan
    SEBELUM tulis_kode ke lokasi tersebut. Tanpa ini, tulis ke luar root
    ditolak. File sensitif (.env, *.key/pem/dsb.) tetap selalu ditolak.

    Args:
        path: Path folder absolut pilihan user, mis. F:/bdk atau /home/user/proj.
    """
    try:
        from src.core.auth.approval import current_session
        from src.core.system.workspaces import note_target_dir

        try:
            session_id = current_session.get() or ""
        except Exception as _e:
            session_id = ""
            import logging as _log

            _log.getLogger(__name__).debug("current_session.get error: %s", _e)
        ok, result = note_target_dir(session_id, path)
        if not ok:
            return result
        return f"Direktori kerja session ini dicatat: {result}. tulis_kode kini boleh menulis di dalamnya."
    except Exception as e:
        return tool_error_from_exception(e)
