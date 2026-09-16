"""Orchestrator awal sistem Multi-Agent (Fase 1)."""

from core.logger import setup_logger

logger = setup_logger("core.main")


def main() -> None:
    logger.info("=== Multi-Agent System | Fase 1: Persiapan Lingkungan Dasar ===")
    logger.info("Workspace siap. Jalankan 'python -m core.memory' untuk tes koneksi Redis.")


if __name__ == "__main__":
    main()
