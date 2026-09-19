---
name: pdf-ocr
description: "Ekstrak teks dari PDF scan/gambar. Trigger: /pdf-ocr [path/file.pdf]"
---

# PDF OCR

Ekstrak teks dari dokumen PDF yang berisi gambar atau scan.

## Langkah

1. **Identifikasi**: Pastikan PDF berisi gambar/scan
2. **OCR**: Gunakan tool yang mendukung OCR untuk ekstrak teks
3. **Validasi**: Periksa hasil ekstraksi untuk akurasi

## Contoh Penggunaan

```
/pdf-ocr dokumen-scan.pdf
/pdf-ocr kartu-identitas.pdf
```

## Limitasi

- Akurasi tergantung kualitas scan
- Font dekoratif mungkin tidak terbaca dengan benar
- Tidak mendukung bahasa tertentu tanpa model OCR khusus
