"""Plugin Tools (Tangan & Kaki AI) untuk eksekusi aksi nyata di sistem lokal."""

import os
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults

web_search_tool = DuckDuckGoSearchResults()

@tool
def tulis_kode(filepath: str, konten: str) -> str:
    """Menulis teks atau kode program ke dalam file lokal."""
    try:
        # Proteksi Overwrite: Jika file ada, tambahkan suffix _v2, _v3, dst.
        original_path = filepath
        counter = 2
        while os.path.exists(filepath):
            path_parts = os.path.splitext(original_path)
            filepath = f"{path_parts[0]}_v{counter}{path_parts[1]}"
            counter += 1
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(konten)
        
        if filepath != original_path:
            return f"File sudah ada. Disimpan sebagai versi baru di {filepath}"
        return f"File berhasil dibuat di {filepath}"
    except Exception as e:
        return f"Gagal menulis file: {str(e)}"

@tool
def baca_file(filepath: str) -> str:
    """Membaca isi dari file lokal."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Error: File tidak ditemukan."
    except Exception as e:
        return f"Error saat membaca file: {str(e)}"

@tool
def cari_web(query: str) -> str:
    """Melakukan pencarian informasi terkini di internet menggunakan DuckDuckGo."""
    return web_search_tool.run(query)

AVAILABLE_PLUGINS = {
    "tulis_kode": tulis_kode,
    "baca_file": baca_file,
    "cari_web": cari_web,
}