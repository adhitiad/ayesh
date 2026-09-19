---
name: kontrak-review
description: dipakai saat user meminta analisis, review, atau tinjauan kontrak/Perjanjian. trigger: /kontrak-review
---

# Skill: Review Kontrak

Jalankan setiap kali user meminta review atau analisis kontrak.

## Langkah

1. **Kumpulkan informasi awal:**
   - Jenis kontrak (kerja, NDA, jual beli, sewa, jasa, dll)
   - Posisi user (karyawan, kontraktor, pembeli, penjual, dll)
   - Yurisdiksi/negara (Indonesia, US, EU, dll)
   - Area kekhawatiran spesifik (jika ada)

2. **Analisis risiko:**
   - **Risiko Tinggi (Merah):** Tanggung jawab tanpa batas, IP assignment terlalu luas, pemutusan sepihak, ganti rugi sepihak, pelepasan hak terlalu luas, perlindungan data tidak ada
   - **Risiko Sedang (Kuning):** Auto-renewal, denda berlebihan, non-compete luas, kerahasiaan tanpa batas waktu, yurisdiksi tidak menguntungkan, syarat pembayaran buruk
   - **Risiko Rendang (Hijau):** Hak audit tidak ada, klausul force majeure tidak ada

3. **Cek kelengkapan:**
   - [ ] Para pihak (nama lengkap, alamat)
   - [ ] Tanggal berlaku
   - [ ] Jangka waktu/durasi
   - [ ] Ruang lingkup pekerjaan
   - [ ] Kompensasi/pembayaran
   - [ ] Syarat pemutusan
   - [ ] Kerahasiaan
   - [ ] Kepemilikan IP
   - [ ] Batasan tanggung jawab
   - [ ] Ganti rugi
   - [ ] Hukum yang berlaku
   - [ ] Penyelesaian sengketa
   - [ ] Blok tanda tangan

4. **Buat laporan:**
   - Ringkasan risiko (Tinggi/Sedang/Rendah)
   - Temuan detail per klausul
   - Rekomendasi spesifik perubahan
   - Prioritas negosiasi

## Pola Risiko Penting

### Merah (Harus Diubah)
- **Tanggung jawab tanpa batas:** Minta cap tanggung jawab
- **IP assignment luas:** Kecualikan IP yang dibuat sebelum kontrak
- **Pemutusan sepihak:** Minta hak pemutusan timbal balik
- **Ganti rugi sepihak:** Negosiasi ganti rugi timbal balik

### Kuning (Perlu Diperhatikan)
- **Auto-renewal:** Minta opt-out 30 hari sebelumnya
- **Non-compete luas:** Batasi 1-2 tahun, wilayah spesifik
- **Kerahasiaan tanpa batas:** Minta batas waktu 3-5 tahun

## Contoh Output

```
## Laporan Analisis Kontrak

**Dokumen:** [Nama Kontrak]
**Jenis:** [Kerja/NDA/Jual Beli/etc]
**Yurisdiksi:** [Negara]
**Posisi Anda:** [Peran]

### Ringkasan Risiko
| Tingkat | Jumlah | Masalah Utama |
|---------|--------|---------------|
| Merah | X | [Daftar singkat] |
| Kuning | X | [Daftar singkat] |
| Hijau | X | [Daftar singkat] |

**Penilaian Keseluruhan:** [AMAN / PERLU REVIEW / RISIKO TINGGI]

### Temuan Detail
[Analisis per klausul dengan kutipan langsung]

### Rekomendasi
1. **Harus Diubah:** [Masalah kritis]
2. **Sebaiknya Diubah:** [Penting tapi negosiable]
3. **Nice to Have]: [Prioritas rendah]
```

## Aturan
- Selalu sertakan disclaimer: "Analisis ini untuk tujuan informasi saja dan bukan pengacara"
- Jika stakes tinggi (M&A, transaksi besar), sarankan konsultasi pengacara
- Jangan memberikan nasihat hukum yang spesifik
- Fokus pada pola umum yang bisa dideteksi dari teks kontrak

## Limitasi
- Tidak bisa memverifikasi apakah pihak lain akan mengikuti kontrak
- Pengetahuan mungkin tidak mencerminkan perubahan hukum terbaru
- Beberapa risiko spesifik industri mungkin perlu ahli
- Tidak menggantikan review hukum profesional untuk kontrak berisiko tinggi
