"""Environment eksekusi / simulasi RL untuk agen.

Menyediakan antarmuka ala environment RL (reset/step) yang akan dipakai
untuk mengeksekusi aksi agen dan mengembalikan observasi serta reward.
"""

from __future__ import annotations


class AgentEnv:
    """Kerangka environment eksekusi (placeholder Fase 1)."""

    def reset(self) -> dict:
        """Reset environment ke state awal."""
        return {}

    def step(self, action: str) -> tuple[dict, float, bool]:
        """Eksekusi satu aksi.

        Returns:
            tuple berisi (observasi, reward, selesai).
        """
        raise NotImplementedError(
            "Environment akan diimplementasikan pada fase berikutnya."
        )
