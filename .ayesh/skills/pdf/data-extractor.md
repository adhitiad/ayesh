---
name: data-extractor
description: "Ekstrak data terstruktur dari dokumen. Trigger: /ekstrak-data [tipe] [path/file]"
---

# Data Extractor

Ekstrak data terstruktur dari berbagai jenis dokumen.

## Tipe Ekstraksi

| Tipe | Command | Output |
|------|---------|--------|
| Tabel | `/ekstrak-data tabel dokumen.pdf` | CSV/JSON |
| Kontak | `/ekstrak-data kontak dokumen.pdf` | Daftar kontak |
| Tanggal | `/ekstrak-data tanggal dokumen.pdf` | Daftar tanggal |
| Angka | `/ekstrak-data angka dokumen.pdf` | Daftar numerik |

## Contoh Penggunaan

```
/ekstrak-data tabel laporan-keuangan.pdf
/ekstrak-data kontak daftar-klien.xlsx
/ekstrak-data tanggal jadwal-proyek.docx
```

## Limitasi

- Data harus dalam format yang dapat dikenali
- Dokumen dengan struktur kompleks mungkin perlu bantuan manual
