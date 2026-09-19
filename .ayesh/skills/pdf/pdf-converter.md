---
name: pdf-converter
description: "Konversi PDF ke format lain (Markdown, HTML, teks). Trigger: /pdf-konversi [format] [path/file.pdf]"
---

# PDF Converter

Konversi dokumen PDF ke berbagai format.

## Langkah

1. **Baca PDF**: Gunakan `firecrawl_parse` untuk ekstrak konten
2. **Konversi**: Ubah ke format yang diminta (Markdown, HTML, plain text)
3. **Simpan**: Output hasil konversi

## Format yang Didukung

| Format | Command | Kegunaan |
|--------|---------|----------|
| Markdown | `/pdf-konversi md file.pdf` | Untuk编辑/review |
| HTML | `/pdf-konversi html file.pdf` | Untuk web |
| Teks | `/pdf-konversi txt file.pdf` | Untuk analisis |

## Contoh Penggunaan

```
/pdf-konversi md laporan.pdf
/pdf-konversi html presentasi.pdf
```

## Limitasi

- Format kompleks (multi-column) mungkin tidak sempurna
- Gambar tidak diekstrak secara otomatis
