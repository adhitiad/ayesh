---
name: brand-guidelines
description: "Buat panduan brand style guide. Trigger: /brand [nama_brand]"
---

# Brand Guidelines

Buat style guide lengkap untuk identitas brand.

## Komponen Style Guide

| Komponen | Command | Keterangan |
|----------|---------|------------|
| Logo Usage | `/brand logo [nama]` | Panduan penggunaan logo |
| Color Palette | `/brand warna [nama]` | Skema warna brand |
| Typography | `/brand font [nama]` | Pilihan font |
| Voice & Tone | `/brand voice [nama]` | Gaya komunikasi |
| Full Guide | `/brand guide [nama]` | Style guide lengkap |

## Output Format

```markdown
# Brand Style Guide: [Nama Brand]

## Logo
- Primary logo: [deskripsi]
- Variations: [list]
- Clear space: [aturan]

## Colors
- Primary: #XXXXXX
- Secondary: #XXXXXX
- Accent: #XXXXXX

## Typography
- Headings: [Font Name]
- Body: [Font Name]

## Voice
- Tone: [profesional/casual/friendly]
- Keywords: [kata kunci brand]
```

## Contoh Penggunaan

```
/brand guide Ayesh AI
/brand warna TechStartup XYZ
/brand voice Konsultan Digital
```

## Limitasi

- Hasil adalah panduan awal, perlu review desainer
- Tidak termasuk aset desain (logo, dll)
