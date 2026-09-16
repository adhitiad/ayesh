"""Logika agen utama.

Modul ini berisi definisi agen (peran, instruksi, dan loop reasoning).
Implementasi penuh akan ditambahkan pada fase berikutnya.
"""

from __future__ import annotations


class Agent:
    """Kerangka dasar agen (placeholder Fase 1)."""

    def __init__(self, name: str, role: str = "generalist") -> None:
        self.name = name
        self.role = role

    def run(self, task: str) -> str:
        """Jalankan sebuah tugas oleh agen."""
        raise NotImplementedError(
            "Logika agen akan diimplementasikan pada fase berikutnya."
        )
