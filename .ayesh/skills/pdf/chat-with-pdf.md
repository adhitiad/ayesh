---
name: chat-with-pdf
description: "Tanya jawab isi dokumen PDF. Trigger: /pdf-chat [pertanyaan] [path/file.pdf]"
---

# Chat with PDF

Tanya jawab interaktif dengan dokumen PDF.

## Langkah

1. **Baca PDF**: Gunakan tool `baca_file` atau `firecrawl_parse` untuk ekstrak konten
2. **Identifikasi**: Tentukan bagian yang relevan dengan pertanyaan
3. **Jawab**: Berikan jawaban dengan referensi halaman jika memungkinkan

## Fitur

- Ekstrak teks, tabel, dan metadata dari PDF
- Jawab pertanyaan spesifik dengan kutipan langsung
- Ringkas seluruh dokumen jika diminta

## Contoh Penggunaan

```
/pdf-chat Apa poin utama dari kontrak ini? /path/contract.pdf
/pdf-chat Ringkas dokumen ini dalam 5 poin
/pdf-chat Berapa total biaya yang disebutkan?
```

## Limitasi

- Hanya untuk PDF yang tidak terproteksi password
- Tabel kompleks mungkin perlu konfirmasi ulang
- Tidak dapat membaca gambar dalam PDF kecuali menggunakan OCR
