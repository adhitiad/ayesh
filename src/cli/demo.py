"""CLI demo — standalone entry point for testing route_request interactively."""

import json

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.cli")


def run_demo():
    """Run interactive demo scenarios."""
    from src.core.routing.router import route_request_inner

    logger.info("=== Multi-Agent System | Fase 10: Smart Routing & Shortcut ===")
    logger.info("")

    logger.info("--- Tantangan 1: Coder Agent (dengan tool) ---")
    result1 = route_request_inner(
        session_id="session_1_coder",
        user_input="Tolong buatkan sebuah file Python bernama kalkulator.py di root direktori yang berisi fungsi pertambahan sederhana. Kamu WAJIB menggunakan tool tulis_kode untuk menyimpan file tersebut secara nyata ke komputerku.",
    )
    logger.info("Result: %s", json.dumps(result1, indent=2, ensure_ascii=False))
    logger.info("")

    logger.info("--- Tantangan 2: Admin Agent ---")
    result2 = route_request_inner(
        session_id="session_2_admin",
        user_input="Buatkan draf surat resmi kepada karyawan tentang penyesuaian gaji UMK Subang tahun 2025. Gunakan bahasa birokrasi yang formal.",
    )
    logger.info("Result: %s", json.dumps(result2, indent=2, ensure_ascii=False))
    logger.info("")

    logger.info("--- Tantangan 3: Casual Agent (shortcut) ---")
    result3 = route_request_inner(
        session_id="session_3_chat",
        user_input="Halo, ada yang bisa bantu? Apa kabar hari ini?",
    )
    logger.info("Result: %s", json.dumps(result3, indent=2, ensure_ascii=False))
    logger.info("")

    logger.info("--- Tantangan 4: Random Test ---")
    result4 = route_request_inner(
        session_id="session_4_random",
        user_input="Siapa presiden Indonesia sekarang?",
    )
    logger.info("Result: %s", json.dumps(result4, indent=2, ensure_ascii=False))
    logger.info("")

    logger.info("=== Selesai ===")


if __name__ == "__main__":
    run_demo()
