---
name: docx-editor
description: "Buat, edit, dan analisis dokumen Word (.docx). Trigger: /docx [operasi] [file.docx]"
---

# DOCX Editor

Buat, edit, dan analisis dokumen Word (.docx) dengan dukungan tracked changes, komentar, dan ekstraksi teks.

## Workflow Decision Tree

### Membaca/Menganalisis Konten
- Gunakan `baca_file` atau `firecrawl_parse` untuk ekstrak teks
- Gunakan `pandoc` untuk konversi ke markdown

### Membuat Dokumen Baru
- Buat file `.js` dengan struktur Document, Paragraph, TextRun
- Export via `Packer.toBuffer()`

### Mengedit Dokumen yang Ada
- **Dokumen sendiri + perubahan sederhana**: Edit langsung
- **Dokumen orang lain**: Gunakan redlining workflow (recommended)
- **Dokumen legal/bisnis/akademik**: Gunakan redlining workflow (required)

## Membaca & Menganalisis Konten

### Ekstraksi Teks dengan Pandoc
```bash
# Konversi ke markdown dengan tracked changes
pandoc --track-changes=all file.docx -o output.md
# Opsi: --track-changes=accept/reject/all
```

### Akses Raw XML
Untuk komentar, format kompleks, struktur dokumen, media embedded, dan metadata:

```bash
# Unpack dokumen
python ooxml/scripts/unpack.py

# Struktur file penting:
# word/document.xml   - Konten utama
# word/comments.xml   - Komentar
# word/media/         - Gambar dan media
# Tracked changes: <w:ins> (insertions) dan <w:del> (deletions)
```

## Membuat Dokumen Baru

Gunakan **docx-js** (JavaScript/TypeScript) untuk membuat dokumen dari awal.

### Langkah
1. Buat file `.js` dengan komponen Document, Paragraph, TextRun
2. Definisikan sections, headings, paragraphs
3. Export: `Packer.toBuffer()`

### Contoh Struktur
```javascript
const { Document, Paragraph, TextRun, Packer } = require('docx');
const fs = require('fs');

const doc = new Document({
  sections: [{
    children: [
      new Paragraph({
        children: [new TextRun({ text: "Judul Dokumen", bold: true, size: 28 })]
      }),
      new Paragraph({
        children: [new TextRun("Isi paragraf pertama.")]
      }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("output.docx", buffer);
});
```

## Mengedit Dokumen yang Ada

Gunakan **Document library** (Python) untuk manipulasi OOXML.

### Langkah
1. Unpack: `python ooxml/scripts/unpack.py`
2. Baca dan edit XML
3. Pack: `python ooxml/scripts/pack.py unpacked output.docx`

## Redlining Workflow (Tracked Changes)

Untuk review dokumen profesional dengan tracked changes.

### Prinsip: Minimal, Precise Edits
Hanya tandai teks yang benar-benar berubah. Jangan ulang teks yang tidak berubah.

```python
# BAD - Mengganti seluruh kalimat
'The term is 30 days.The term is 60 days.'

# GOOD - Hanya tandai yang berubah
'The term is <w:del>30</w:del><w:ins>60</w:ins> days.'
```

### Langkah Redlining
1. **Konversi ke markdown**: `pandoc --track-changes=all file.docx -o current.md`
2. **Identifikasi perubahan**: Kelompokkan perubahan ke batch 3-10 item
3. **Baca dokumentasi**: Baca `ooxml.md` untuk pola tracked changes
4. **Implementasi per batch**: Gunakan `get_node` untuk cari node, implementasi perubahan
5. **Pack dokumen**: `python ooxml/scripts/pack.py unpacked reviewed.docx`
6. **Verifikasi**: Konversi ulang dan periksa semua perubahan

### Strategi Batch
Kelompokkan perubahan terkait:
- Per section/heading
- Per tipe perubahan (tanggal, nama, istilah)
- Per kompleksitas (sederhana dulu, kompleks belakangan)

## Konversi Dokumen ke Gambar

```bash
# DOCX → PDF
soffice --headless --convert-to pdf document.docx

# PDF → JPEG
pdftoppm -jpeg -r 150 document.pdf page
# Output: page-1.jpg, page-2.jpg, dll.

# Opsi untuk range halaman:
pdftoppm -jpeg -r 150 -f 2 -l 5 document.pdf page
```

## Dependencies

- **pandoc**: Ekstraksi teks → `sudo apt-get install pandoc`
- **docx (npm)**: Buat dokumen baru → `npm install -g docx`
- **LibreOffice**: Konversi ke PDF → `sudo apt-get install libreoffice`
- **Poppler**: PDF ke gambar → `sudo apt-get install poppler-utils`
- **defusedxml**: Parsing XML aman → `pip install defusedxml`

## Limitasi

- Edit kompleks membutuhkan pemahaman OOXML
- Tracked changes memerlukan implementasi batch yang hati-hati
- Dokumen dengan macro VBA tidak didukung
- Format sangat kompleks mungkin tidak sempurna
