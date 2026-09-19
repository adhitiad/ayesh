---
name: lead-qualification
description: "Skor & kualifikasi leads. Trigger: /kualifikasi [leads] [kriteria]"
---

# Lead Qualification

Skor dan kualifikasi leads berdasarkan kriteria yang ditentukan.

## Framework Kualifikasi

### BANT (Budget, Authority, Need, Timeline)

| Kriteria | Pertanyaan | Skor |
|----------|------------|------|
| Budget | Apakah ada budget? | 1-10 |
| Authority | Apakah decision maker? | 1-10 |
| Need | Apakah ada kebutuhan? | 1-10 |
| Timeline | Kapan timeline? | 1-10 |

### MEDDIC (Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion)

| Kriteria | Keterangan |
|----------|------------|
| Metrics | Bagaimana mengukur sukses? |
| Economic Buyer | Siapa yang approve budget? |
| Decision Criteria | Apa faktor penentu? |
| Decision Process | Bagaimana proses keputusan? |
| Identify Pain | Apa pain point utama? |
| Champion | Siapa internal champion? |

## Output Format

```markdown
# Lead Qualification: [Nama Leads]

## Skor Kualifikasi
- BANT Score: XX/40
- Rating: Hot/Warm/Cold

## Rekomendasi
- [Action items]
- [Next steps]
```

## Contoh Penggunaan

```
/kualifikasi PT Maju Jaya --bant
/kualifikasi "John Doe, CTO StartupX" --meddic
```

## Limitasi

- Skor bersifat subjektif, perlu validasi manual
- Tidak menggantikan penilaian sales expert
