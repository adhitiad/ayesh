---
name: pdf-merge-split
description: "Gabung atau split beberapa file PDF. Trigger: /pdf-gabung [operasi] [file1.pdf file2.pdf]"
---

# PDF Merge/Split

Gabungkan beberapa file PDF atau pisahkan berdasarkan halaman.

## Operasi

| Operasi | Command | Keterangan |
|---------|---------|------------|
| Gabung | `/pdf-gabung merge file1.pdf file2.pdf` | Gabung beberapa PDF |
| Split | `/pdf-gabung split file.pdf 1-5` | Ambil halaman 1-5 |
| Hapus | `/pdf-gabung remove file.pdf 3` | Hapus halaman 3 |

## Contoh Penggunaan

```
/pdf-gabung merge laporan1.pdf laporan2.pdf laporan3.pdf
/pdf-gabung split presentasi.pdf 1-10
/pdf-gabung remove dokumen.pdf 5-8
```

## Limitasi

- Ukuran output dibatasi oleh sumber daya sistem
- PDF terproteksi tidak dapat digabung tanpa password
