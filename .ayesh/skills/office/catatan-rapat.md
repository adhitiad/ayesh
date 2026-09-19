---
name: catatan-rapat
description: dipakai saat user meminta ringkasan rapat, notulensi, atau catatan pertemuan. trigger: /rapat
---

# Skill: Catatan Rapat

Jalankan setiap kali user meminta pembuatan atau pengolahan catatan rapat.

## Langkah

1. **Kumpulkan input:**
   - Teks mentah / transkrip rapat
   - Daftar hadir
   - Agenda rapat (jika ada)
   - Dokumen pendukung (jika ada)

2. **Struktur catatan:**
   - Identitas rapat (judul, tanggal, peserta)
   - Poin-poin pembahasan
   - Keputusan yang diambil
   - Action items dengan penanggung jawab
   - Tindak lanjut

3. **Format output:**
   - Ringkas dan terstruktur
   - Gunakan bullet point
   - Sertakan timestamp jika ada

## Template Catatan Rapat

```
# Catatan Rapat: [Judul]

**Tanggal:** [Tanggal]
**Waktu:** [Jam Mulai] - [Jam Selesai]
**Tempat:** [Lokasi/Platform]
**Peserta:** [Daftar nama]
**Catatan oleh:** [Nama pencatat]

## Agenda
1. [Agenda 1]
2. [Agenda 2]
3. [Agenda 3]

## Pembahasan

### 1. [Topik 1]
- [Poin diskusi]
- [Pendapat dari: Nama]

### 2. [Topik 2]
- [Poin diskusi]
- [Keputusan]

## Keputusan
1. [Keputusan 1]
2. [Keputusan 2]

## Action Items

| No | Tugas | Penanggung | Deadline | Status |
|----|-------|------------|----------|--------|
| 1 | [Tugas] | [Nama] | [Tanggal] | - |
| 2 | [Tugas] | [Nama] | [Tanggal] | - |

## Tindak Lanjut
- [Rapat berikutnya: tanggal/waktu]
- [Dokumen yang perlu disiapkan]
- [Yang perlu dipantau]
```

## Aturan
- Fokus pada keputusan dan action items, bukan percakapan
- Gunakan nama orang untuk action items (bukan "tim" atau "pihak terkait")
- Jika ada ketidaksepakatan, catat secara netral
- Sertakan deadline yang realistis
- Minta konfirmasi peserta sebelum final

## Limitasi
- Hanya memproses teks yang diberikan
- Tidak bisa mengenali siapa yang berbicara dari teks mentah
- Mungkin melewatkan konteks non-verbal (nada, ekspresi)
