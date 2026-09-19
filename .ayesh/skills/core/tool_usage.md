# Panduan Penggunaan Tool

## tulis_kode
- **Fungsi:** Menulis kode atau teks ke file lokal.
- **Kapan digunakan:** Saat pengguna meminta pembuatan file, menulis kode, atau menyimpan hasil.
- **Parameter:**
  - `filepath`: Path file tujuan (bisa absolut atau relatif).
  - `konten`: Isi teks atau kode yang akan ditulis.
- **Contoh:** `tulis_kode(filepath="main.py", konten="print('Hello')")`

## baca_file
- **Fungsi:** Membaca isi dari file lokal.
- **Kapan digunakan:** Saat pengguna meminta analisis kode, membaca dokumen, atau melihat isi file.
- **Parameter:**
  - `filepath`: Path file yang ingin dibaca.
- **Contoh:** `baca_file(filepath="README.md")`

## cari_web
- **Fungsi:** Mencari informasi terkini di internet via DuckDuckGo.
- **Kapan digunakan:** Saat informasi yang dibutuhkan tidak ada di memori internal atau dokumen RAG.
- **Parameter:**
  - `query`: Kata kunci atau pertanyaan pencarian.
- **Contoh:** `cari_web(query="UMK Subang 2025")`

## Best Practices
- Pilih tool yang sesuai sebelum menjalankan. Jangan gunakan tool jika tidak diperlukan.
- Pastikan path file valid sebelum menulis atau membaca.
- Gunakan query spesifik untuk pencarian web agar hasil lebih relevan.
- Laporkan error tool ke pengguna dengan pesan yang jelas.
