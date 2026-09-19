---
name: doc-parser
description: "Parse dokumen kompleks (Word, Excel, PPT). Trigger: /parse-doc [path/file.docx]"
---

# Document Parser

Ekstrak dan解析 isi dari dokumen Office (Word, Excel, PowerPoint).

## Format yang Didukung

| Ekstensi | Tool | Output |
|----------|------|--------|
| .docx | `firecrawl_parse` | Markdown/teks |
| .xlsx | `firecrawl_parse` | Tabel/CSV |
| .pptx | `firecrawl_parse` | Poin-poin |
| .odt | `firecrawl_parse` | Markdown |

## Contoh Penggunaan

```
/parse-doc laporan.docx
/parse-doc data-penjualan.xlsx
/parse-doc presentasi.pptx
```

## Limitasi

- Format kompleks (macro, VBA) tidak didukung
- Tabel dengan merge cell mungkin perlu penyesuaian
