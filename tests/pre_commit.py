#!/usr/bin/env python3
"""Pre-commit hook: jalankan test struktur prompt otomatis.

Cara pakai:
  1. Copy ke .git/hooks/pre-commit (atau symlink)
  2. chmod +x .git/hooks/pre-commit (Mac/Linux)
  3. Akan jalan otomatis tiap git commit

  Windows: JANGAN copy langsung (shebang `env python3` kena Microsoft Store
  stub "Python was not found"). Sebagai gantinya, isi .git/hooks/pre-commit
  dengan wrapper sh yang mencari venv dulu (lihat riwayat file ini di git).

Skrip ini hanya jalan jika ada perubahan pada file Python terkait prompt.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_FILES = {
    "config/rules.py",
    "mcp_core/registry.py",
    "mcp_core/skills.py",
    "mcp_core/context_loader.py",
    "plugins/core_tools.py",
    "main.py",
}


def get_staged_files() -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, cwd=ROOT
    )
    return {f.strip() for f in result.stdout.splitlines() if f.strip()}


def main() -> int:
    staged = get_staged_files()
    changed = staged & PROMPT_FILES

    if not changed:
        return 0

    print(f"[pre-commit] Prompt file berubah: {', '.join(changed)} — menjalankan structural tests...")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_prompt_structure", "-v"],
        cwd=ROOT
    )

    if result.returncode != 0:
        print("\n[pre-commit] GAGAL — commit dibatalkan. Perbaiki test dulu.")
        return 1

    print("[pre-commit] LOLOS — commit dilanjutkan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
