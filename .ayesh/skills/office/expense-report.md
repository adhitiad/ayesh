---
name: expense-report
description: dipakai saat user meminta pembuatan laporan pengeluaran, expense report, atau rekapan biaya. trigger: /expense
---

# Skill: Laporan Pengeluaran

Jalankan setiap kali user meminta pembuatan atau pengolahan laporan pengeluaran.

## Langkah

1. **Kumpulkan data:**
   - Daftar pengeluaran (tanggal, deskripsi, jumlah, kategori)
   - Bukti/kwitansi (jika ada)
   - Periode laporan
   - Mata uang

2. **Kategorikan:**
   - Transportasi (tiket, BBM, parkir, taksi)
   - Akomodasi (hotel, penginapan)
   - Makan (meeting, lembur)
   - Komunikasi (pulsa, internet)
   - ATK (perlengkapan kantor)
   - Lainnya

3. **Hitung total:**
   - Total per kategori
   - Total keseluruhan
   - Pajak (PPN, PPh 23, dll)

4. **Buat laporan:**
   - Format tabel yang rapi
   - Ringkasan per kategori
   - Rekomendasi kebijakan

## Template Laporan

```
# Laporan Pengeluaran

**Nama:** [Nama Karyawan]
**Divisi:** [Divisi]
**Periode:** [Tanggal Awal] - [Tanggal Akhir]
**Diajukan pada:** [Tanggal Pengajuan]

## Ringkasan

| Kategori | Jumlah | % dari Total |
|----------|--------|--------------|
| Transportasi | Rp X | X% |
| Akomodasi | Rp X | X% |
| Makan | Rp X | X% |
| Komunikasi | Rp X | X% |
| Lainnya | Rp X | X% |
| **Total** | **Rp X** | **100%** |

## Detail Pengeluaran

| No | Tanggal | Deskripsi | Kategori | Jumlah | Bukti |
|----|---------|-----------|----------|--------|-------|
| 1 | [Tanggal] | [Deskripsi] | [Kategori] | Rp X | [Ada/Tidak] |
| 2 | [Tanggal] | [Deskripsi] | [Kategori] | Rp X | [Ada/Tidak] |

## Rekomendasi

### Temuan:
- Total pengeluaran: Rp X (X% dari budget)
- Kategori terbesar: [Kategori] (Rp X)
- Pengeluaran di atas rata-rata: [Item]

### Saran Efisiensi:
1. [Saran 1]
2. [Saran 2]
3. [Saran 3]
```

## Kategori Umum Pengeluaran

| Kategori | Contoh Item |
|----------|-------------|
| Transportasi | Tiket pesawat, kereta, BBM, parkir, taksi/ride-hailing |
| Akomodasi | Hotel, penginapan |
| Makan | Makan meeting, makan lembur, jamuan klien |
| Komunikasi | Pulsa, paket data, telepon |
| ATK | Tulis, cetak, perlengkapan kantor |
| Entertainment | Jamuan klien, hadiah, acara |
| Pelatihan | Kursus, seminar, workshop, sertifikasi |

## Aturan
- Pastikan semua pengeluaran memiliki bukti/kwitansi
- Kategorikan secara konsisten
- Sertakan mata uang jika multi-currency
- Rekomendasikan kebijakan jika ada pola yang perlu diperhatikan

## Limitasi
- Hanya memproses data yang diberikan
- Tidak bisa memverifikasi keaslian bukti
- Rekomendasi kebijakan harus disesuaikan dengan peraturan perusahaan
