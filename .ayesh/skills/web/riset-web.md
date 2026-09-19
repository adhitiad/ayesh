---
name: riset-web
description: dipakai saat butuh informasi terkini dari internet (harga, berita, regulasi, saham). trigger: /riset-web
---

# Skill: Riset Web

Jalankan setiap kali jawaban membutuhkan fakta terkini yang tidak ada di memori internal.

## Langkah
1. Rumuskan query spesifik via `cari_web` (maks 5 hasil per panggilan).
2. Jika hasil kurang, variasikan kata kunci sekali lagi — jangan loop lebih dari 2x.
3. Sajikan jawaban dengan sumber yang jelas. Jika pencarian gagal, katakan gagal + sarankan sumber resmi, jangan mengarang angka.

## Aturan
- JANGAN dipakai untuk pengetahuan umum yang stabil.
- Angka (harga, kurs, UMK) wajib dari hasil pencarian, bukan ingatan.
