import concurrent.futures
from main import route_request
from core.logger import setup_logger

logger = setup_logger("test_concurrent")


def run_session(session_id, prompt):
    logger.info(f"🟢 [{session_id}] Mulai memproses...")
    response = route_request(prompt, session_id)
    logger.info(f"✅ [{session_id}] Selesai!\nBalasan:\n{response}\n{'-'*30}")
    return response


if __name__ == "__main__":
    logger.info("🚀 Memulai Uji Coba Multi-Sesi Ekstrem...\n")
    queries = [
        ("session_1_coder", "Tolong buatkan file python bernama halo.py isinya print('Halo dari Sesi 1'). Gunakan tool tulis_kode."),
        ("session_3_admin", "Buatkan draf paragraf pendek tentang penyesuaian gaji berdasarkan UMK Subang dan UMP Jabar 2,3 Juta."),
        ("session_2_chat", "Halo! Aku cuma mau nyapa nih, ini sesi obrolan biasa.")
    ]


    # Eksekusi 3 sesi di detik yang sama menggunakan ThreadPool
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_session, sid, q) for sid, q in queries]
        concurrent.futures.wait(futures)


    logger.info("🏁 Semua proses selesai. Silakan cek file halo.py dan pastikan jawaban tidak tercampur!")
