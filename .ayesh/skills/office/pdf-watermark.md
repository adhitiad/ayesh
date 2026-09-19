---
name: pdf-watermark
description: "Tambah watermark, nomor halaman, header/footer ke PDF. Trigger: /pdf-watermark, /watermark-pdf, /stempel-pdf"
category: office
tags: [pdf, watermark, branding, security]
---

# PDF Watermark & Page Elements

Tambahkan watermark, nomor halaman, header, footer, dan elemen overlay ke dokumen PDF.

## Langkah

### Watermark Teks
```
"Tambah watermark 'CONFIDENTIAL' ke PDF ini"
```

### Menggunakan office_tool
```
office_tool("add_watermark", '{"input": "dokumen.pdf", "output": "dokumen_watermarked.pdf", "text": "RAHASIA", "fontsize": 72, "color": [1,0,0]}')
```

### Watermark Gambar
```
"Tambah logo perusahaan sebagai watermark di pojok kanan bawah"
```

### Nomor Halaman
```
"Tambah nomor halaman di footer tengah, format: Halaman X dari Y"
```

### Header/Footer
```
"Tambah header dengan judul dokumen dan footer dengan tanggal"
```

## Opsi Watermark

### Teks
```python
import fitz  # PyMuPDF

doc = fitz.open("input.pdf")
for page in doc:
    rect = page.rect
    text_point = fitz.Point(rect.width/3, rect.height/2)
    page.insert_text(
        text_point,
        "CONFIDENTIAL",
        fontsize=72,
        color=(1, 0, 0),  # merah
        rotate=45,  # diagonal
        overlay=True,
        fontname="helv"
    )
doc.save("output.pdf")
```

### Gambar
```python
page.insert_image(
    fitz.Rect(100, 100, 300, 200),
    filename="logo.png",
    overlay=True,
    maintain=True
)
```

### Preset Watermark

| Preset | Teks | Warna | Guna |
|--------|------|-------|------|
| Draft | DRAFT | Abu-abu, diagonal | Dokumen kerja |
| Confidential | CONFIDENTIAL | Merah, diagonal | Dokumen rahasia |
| Copy | COPY | Biru, horizontal | Salinan |
| Approved | APPROVED | Hijau, stamp | Sudah disetujui |
| Sample | SAMPLE | Abu-abu, tile | Contoh |

## Nomor Halaman

### Format

| Gaya | Contoh |
|------|--------|
| Sederhana | 1, 2, 3 |
| Page X | Halaman 1 |
| X of Y | 1 dari 25 |
| Romawi | i, ii, iii |

### Implementasi
```python
for i, page in enumerate(doc):
    text = f"Halaman {i+1} dari {len(doc)}"
    page.insert_text(
        fitz.Point(page.rect.width/2 - 50, page.rect.height - 30),
        text,
        fontsize=10,
        color=(0.3, 0.3, 0.3),
        fontname="helv"
    )
```

## Header/Footer

### Header
```python
# Kiri: logo, Tengah: judul, Kanan: tanggal
header_y = 25

# Logo
page.insert_image(fitz.Rect(30, 10, 130, 35), filename="logo.png")

# Judul
page.insert_text(fitz.Point(page.rect.width/2 - 50, header_y),
    "Laporan Keuangan", fontsize=12, fontname="helv")

# Tanggal
page.insert_text(fitz.Point(page.rect.width - 100, header_y),
    "2026-01-29", fontsize=10, color=(0.5,0.5,0.5), fontname="helv")
```

## Batch Processing

```python
from pathlib import Path

for pdf_file in Path("/input/").glob("*.pdf"):
    doc = fitz.open(str(pdf_file))
    for page in doc:
        page.insert_text(
            fitz.Point(page.rect.width/3, page.rect.height/2),
            "CONFIDENTIAL",
            fontsize=72,
            color=(1, 0, 0),
            rotate=45,
            overlay=True
        )
    doc.save(f"/output/{pdf_file.name}")
```

## Stamps & Label

| Stamp | Warna | Guna |
|-------|-------|------|
| APPROVED | Hijau | Disetujui |
| REJECTED | Merah | Ditolak |
| REVIEWED | Biru | Sudah direview |
| PENDING | Kuning | Menunggu |
| FINAL | Hitam | Dokumen final |

## Limitasi
- Watermark gambar harus resolusi cukup
- PDF terenkripsi tidak bisa dimodifikasi
- Font yang tersedia terbatas (helv, cour, times)
- Watermark mungkin tidak konsisten di ukuran halaman berbeda
