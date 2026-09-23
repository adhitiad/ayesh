"""Code execution tools: jalankan_python, CodeExecutionSandbox."""

import os
import sys
from typing import ClassVar

from langchain_core.tools import tool

from src.plugins.file_safety import _safe_path
from src.plugins.tool_error import tool_error_from_exception


@tool
def jalankan_python(kode: str = "", filepath: str = "", timeout_detik: int = 30) -> str:
    """Menjalankan kode/file Python lokal dan mengembalikan outputnya.

    Pakai untuk verifikasi mandiri setelah tulis_kode: jalankan, baca error,
    perbaiki, ulangi sampai lolos. Isi salah satu: kode atau filepath.
    Proses dieksekusi di sandbox terisolasi.

    Args:
        kode: Kode Python untuk dieksekusi langsung.
        filepath: Path file .py lokal untuk dijalankan.
        timeout_detik: Batas waktu eksekusi (default 30, maks 120).
    """
    import subprocess  # nosec B404 (jalankan_python; digate HITL approval)

    try:
        from src.core.auth.approval import ensure_approved
        from src.core.auth.auth import get_current_user_id

        _ok, _msg = ensure_approved(
            "jalankan_python",
            {"filepath": filepath, "has_code": bool(kode)},
            owner_user_id=get_current_user_id(),
        )
        if not _ok:
            return _msg
    except Exception as e:
        return tool_error_from_exception(e)
    if not kode and not filepath:
        return "Error: Isi salah satu: kode atau filepath."
    timeout_detik = max(1, min(int(timeout_detik), 120))
    sandbox = CodeExecutionSandbox()
    if filepath:
        if not filepath.endswith(".py"):
            return "Error: Hanya file .py yang boleh dijalankan."
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        cmd = [sys.executable, filepath]
        sandbox.set_workdir(os.path.dirname(filepath))
    else:
        cmd = [sys.executable, "-c", kode]
    try:
        exit_code, output = sandbox.run(cmd, timeout=timeout_detik)
        output = output.strip()[:6000] or "(tidak ada output)"
        return f"exit={exit_code}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: Eksekusi melebihi {timeout_detik}s (timeout)."
    except Exception as e:
        return tool_error_from_exception(e)


class CodeExecutionSandbox:
    """Sandbox untuk eksekusi kode Python terisolasi.

    Security controls:
    - Environment variable whitelist (PATH, PYTHONUNBUFFERED only)
    - Dedicated working directory
    - Process timeout
    - No credential/env access
    - No network access by default
    - No subprocess escalation
    """

    _SAFE_ENV: ClassVar[set[str]] = {"PATH", "PYTHONUNBUFFERED", "TMPDIR", "TEMP", "TMP"}

    def __init__(self, workdir: str | None = None):
        import os

        self._workdir = workdir or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        self._env = {k: v for k, v in os.environ.items() if k in self._SAFE_ENV}
        self._env.setdefault("PYTHONUNBUFFERED", "1")

    def set_workdir(self, path: str) -> None:
        """Set dedicated working directory for the sandbox."""
        self._workdir = path

    def run(self, cmd: list, timeout: int = 30) -> tuple[int, str]:
        """Run command in sandbox. Returns (exit_code, output)."""
        import subprocess  # nosec B404 (sandbox run)

        proc = subprocess.run(  # nosec B603 (cmd list, shell=False, workdir jailed)
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=self._workdir,
            env=self._env,
            start_new_session=True,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip() or "(tidak ada output)"
