---
name: pdf-compress
description: "Kompres ukuran file PDF. Trigger: /pdf-kompres [path/file.pdf]"
---

# PDF Compress

Kurangi ukuran file PDF tanpa mengorbankan kualitas secara signifikan.

## Langkah

1. **Analisis**: Periksa ukuran dan konten PDF
2. **Kompres**: Terapkan kompresi yang sesuai
3. **Validasi**: Pastikan kualitas masih dapat diterima

## Level Kompresi

| Level | Keterangan | Kualitas |
|-------|------------|----------|
| Rendah | Ukuran -30% | Tinggi |
| Sedang | Ukuran -50% | Sedang |
| Tinggi | Ukuran -70% | Rendah |

## Contoh Penggunaan

```
/pdf-kompres laporan-besar.pdf
/pdf-kompres presentasi.pdf --level tinggi
```

## Limitasi

- Tidak semua PDF dapat dikompres signifikan
- PDF dengan banyak gambar lebih sulit dikompres
