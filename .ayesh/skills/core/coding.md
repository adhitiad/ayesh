---
name: koding
description: dipakai saat user meminta kode, file, script, atau program. trigger: /koding
---

# Skill: Koding

Jalankan setiap kali user meminta pembuatan, perbaikan, atau penjelasan kode.

## Langkah
1. Orientasi dulu (bukan substantive work): jika perlu konteks repo, baca file yang relevan via `baca_file` sebelum menulis.
2. Minta review bila ragu: panggil `minta_review` SEBELUM menulis file penting atau menyatakan selesai, dan saat stuck.
3. Tulis via `tulis_kode`. Jangan timpa file yang sudah ada tanpa `overwrite=True` yang disadari — baca dulu targetnya.
4. Verifikasi: nyatakan selesai hanya jika hasil terverifikasi (baca balik file, cek error tool).

## Aturan
- Contoh kode pendek untuk chat ditulis langsung di jawaban, TANPA tool.
- `tulis_kode` hanya untuk file yang benar-benar harus tersimpan.
- Ikuti gaya kode sekitar (nama, komentar, idiom).
- Rujuk kode sebagai file_path:line_number.
