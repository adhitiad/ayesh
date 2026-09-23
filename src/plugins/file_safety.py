"""File safety utilities: path validation, sensitive file detection."""

import os
from pathlib import Path

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

_SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".env.staging"}
_SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".asc", ".gpg")
_SENSITIVE_PATTERNS = (
    "credentials",
    "secret",
    "service-account",
    ".git",
)


def _under(path: str, bases: list) -> bool:
    """True bila path (abspath+normcase) berada di salah satu base."""
    np_ = os.path.normcase(os.path.abspath(path))
    return any(np_ == b or np_.startswith(b + os.sep) for b in bases)


def _check_component_symlinks(original_abs: str, root: str) -> tuple:
    """Component-wise symlink audit: tiap symlink harus resolve ke base yang diizinkan.

    Menutup rantai multi-hop (symlink ke luar lalu balik ke dalam) yang lolos
    cek final-path saja. Basis: project root + direktori approved session.
    Fail-closed: kegagalan pemeriksaan → tolak.
    """
    try:
        bases = [os.path.normcase(os.path.abspath(root))]
        from src.core.system.workspaces import current_session_id, target_dirs_for

        bases.extend(os.path.normcase(d) for d in target_dirs_for(current_session_id()))
        cur = ""
        parts = Path(original_abs).parts
        for i, part in enumerate(parts):
            cur = part if i == 0 else os.path.join(cur, part)
            if os.path.islink(cur):
                real = os.path.realpath(cur)
                if not _under(real, bases):
                    return (
                        False,
                        (
                            f"Error: symlink escape terdeteksi. Komponen '{cur}' resolve ke "
                            f"'{real}' di luar area yang diizinkan."
                        ),
                    )
        return True, ""
    except Exception as e:
        return False, f"Error: pemeriksaan symlink komponen gagal ({e}); akses ditolak."


def _safe_path(path: str) -> tuple:
    """Validasi path TULIS: canonical path, anti-symlink escape, anti-sensitive files.

    P2.2 — Uses Path.resolve() for canonical paths. Rejects:
    - Symlink escape (resolved outside allowed dirs)
    - .. traversal
    - Absolute paths outside project root / approved dirs
    - .git, .env, .env.*, credentials*, secret*, *.pem, *.key, *.p12, *.pfx
    - service-account*.json

    Returns (ok, abs/error)."""
    p = (path or "").strip()
    if not p:
        return False, "Error: path kosong."

    # Resolve to canonical path (follows symlinks, normalizes ..)
    try:
        resolved = Path(p).resolve()
    except Exception:
        return False, f"Error: path '{p}' tidak valid."

    ap = str(resolved)

    # Check if resolved path is inside allowed directories
    root = os.path.abspath(_PROJECT_ROOT)
    root_slash = root.rstrip(os.sep) + os.sep
    in_root = ap == root or ap.startswith(root_slash)

    allowed = False
    if not in_root:
        try:
            from src.core.system.workspaces import is_path_allowed

            allowed = bool(is_path_allowed(ap))
        except Exception as _e:
            allowed = False
            import logging as _log

            _log.getLogger(__name__).debug("_safe_path workspaces error: %s", _e)
        if not allowed:
            return (
                False,
                (
                    f"Error: path di luar project root ({_PROJECT_ROOT}) dan bukan direktori "
                    "pilihan user. Tanya dulu mau disimpan di mana, lalu catat via tool "
                    "set_target_dir sebelum menulis."
                ),
            )

    # Check for symlink escape: if original path != resolved path and resolved is outside
    original_abs = os.path.abspath(p)
    if original_abs != ap and not (ap == root or ap.startswith(root_slash)):
        # Symlink resolved to outside allowed area
        return (
            False,
            f"Error: symlink escape terdeteksi. Path '{p}' resolve ke '{ap}' di luar area yang diizinkan.",
        )

    ok_link, msg_link = _check_component_symlinks(original_abs, root)
    if not ok_link:
        return False, msg_link

    # P2.2 — Sensitive file checks (canonical name matching)
    base = resolved.name.lower()
    parent_names = [part.lower() for part in resolved.parts]

    # Exact name match
    if base in _SENSITIVE_NAMES:
        return False, f"Error: file '{base}' sensitif, akses ditolak."

    # Suffix match
    if base.endswith(_SENSITIVE_SUFFIXES):
        return False, f"Error: file '{base}' sensitif (*.key/*.pem/etc), akses ditolak."

    # Pattern match in filename or path components
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in base:
            return (
                False,
                f"Error: file '{base}' mengandung pola sensitif '{pattern}', akses ditolak.",
            )
        for part in parent_names:
            if pattern in part:
                return False, f"Error: direktori '{part}' sensitif, akses ditolak."

    # Block .git directory
    if ".git" in parent_names:
        return False, "Error: akses ke direktori .git ditolak."

    return True, ap
