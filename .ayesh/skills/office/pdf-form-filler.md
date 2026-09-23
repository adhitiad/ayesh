---
name: pdf-form-filler
description: "Isi form PDF otomatis dan ekstrak data form. Trigger: /pdf-form-filler, /isi-form-pdf, /form-pdf, /isi-formulir"
category: office
tags: [pdf, form, fill, data-entry]
---

# PDF Form Filler

Isi form PDF secara otomatis dan ekstrak data dari form yang sudah diisi.

## Langkah

### Isi Form Tunggal
```
"Isi form PDF ini dengan data berikut:
- Nama: Budi Santoso
- Tanggal: 2026-01-29
- Jumlah: Rp 1.500.000"
```

### Ekstrak Data Form
```
"Ekstrak semua nilai field dari form PDF ini"
```

### Batch Fill
```
"Isi 50 salinan form ini menggunakan data dari spreadsheet"
```

### Menggunakan office_tool
```
office_tool("fill_pdf_form", '{"input": "form.pdf", "output": "filled.pdf", "data": {"name": "Budi", "date": "2026-01-29"}}')
```

### Generate Kode Python
1. Baca file PDF menggunakan `tulis_kode` atau `baca_file`
2. Identifikasi field yang tersedia (text, checkbox, radio, dropdown, date)
3. Generate kode Python menggunakan library `PyMuPDF` (`fitz`) — library yang sama dengan `office_tool`, atau `pdfrw` untuk kasus lanjutan:
```python
from pdfrw import PdfReader, PdfWriter, PageMerge
from pdfrw.annotate import PdfDict

reader = PdfReader('form.pdf')
writer = PdfWriter('output.pdf')

for page in reader.pages:
    annotations = page.get('/Annots', [])
    for annot in annotations:
        field_name = annot['/T']
        if field_name in data_dict:
            annot.update(PdfDict(V=data_dict[field_name]))
    writer.addpage(page)

writer.write()
```
4. Jalankan kode via `jalankan_python`

## Jenis Field yang Didukung

| Field Type | Metode Isi |
|------------|------------|
| Text Field | Input langsung |
| Checkbox | Check/uncheck |
| Radio Button | Pilih salah satu |
| Dropdown | Pilih dari opsi |
| Date Field | Input tanggal (MM/DD/YYYY) |
| Combo Box | Pilih atau ketik |

## Validasi Data

| Field | Aturan | Pesan Error |
|-------|--------|-------------|
| email | Format email valid | "Email tidak valid" |
| phone | 10-13 digit | "Nomor telepon harus 10-13 digit" |
| date | MM/DD/YYYY | "Format tanggal: MM/DD/YYYY" |
| zip | 5-6 digit | "Kode pos tidak valid" |
| amount | Angka > 0 | "Masukkan angka positif" |

## Output

### Laporan Hasil
```markdown
## Hasil Isi Form

| Status | Nilai |
|--------|-------|
| **Form** | application.pdf |
| **Field Terisi** | 23/25 |
| **Error** | 2 |
| **Output** | filled_application.pdf |
```

## Library yang Digunakan
- `pdfrw` — baca/tulis PDF
- `PyMuPDF (fitz)` — manipulasi PDF (pengganti PyPDF2 yang sudah usang)
- `reportlab` — generate PDF baru

## Limitasi
- Tidak bisa isi form yang di-encrypt/password protected
- Signature digital memerlukan sertifikat khusus
- Beberapa form complex dengan auto-calc mungkin tidak work
- Field name harus match persis
