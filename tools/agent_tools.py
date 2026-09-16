"""Modul Tools (Tangan & Kaki AI) untuk eksekusi aksi nyata di sistem lokal."""

import os
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults

# Inisialisasi pencarian web
web_search_tool = DuckDuckGoSearchResults()

@tool
def tulis_kode(filepath: str, konten: str) -> str:
    """
    Menulis teks atau kode program ke dalam file lokal.
    Gunakan fungsi ini saat Anda perlu menyimpan hasil coding, membuat file konfigurasi, 
    atau menulis dokumen ke disk.
    
    Args:
        filepath: Path lengkap atau relatif ke file tujuan.
        konten: Isi teks/kode yang ingin ditulis.
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(konten)
        return f"File berhasil dibuat di {filepath}"
    except Exception as e:
        return f"Gagal menulis file: {str(e)}"

@tool
def baca_file(filepath: str) -> str:
    """
    Membaca isi dari file lokal.
    Gunakan fungsi ini untuk menganalisis kode yang sudah ada atau membaca dokumen referensi lokal.
    
    Args:
        filepath: Path ke file yang ingin dibaca.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "Error: File tidak ditemukan."
    except Exception as e:
        return f"Error saat membaca file: {str(e)}"

@tool
def cari_web(query: str) -> str:
    """
    Melakukan pencarian informasi terkini di internet menggunakan DuckDuckGo.
    Gunakan fungsi ini jika informasi yang dibutuhkan tidak ada dalam memori internal atau dokumen RAG.
    
    Args:
        query: Kata kunci pencarian.
    """
    return web_search_tool.run(query)
