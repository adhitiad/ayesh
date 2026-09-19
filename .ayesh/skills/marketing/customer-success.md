---
name: customer-success
description: "Onboarding & retensi pelanggan. Trigger: /cs [tipe] [pelanggan]"
---

# Customer Success

Manajemen onboarding, retensi, dan kepuasan pelanggan.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| Onboarding Plan | `/cs onboarding [pelanggan]` | Rencana onboarding |
| Health Score | `/cs health [pelanggan]` | Skor kesehatan |
| Churn Risk | `/cs churn [pelanggan]` | Deteksi risiko churn |
| QBR Report | `/cs qbr [pelanggan]` | Quarterly Business Review |
| Upsell | `/cs upsell [pelanggan]` | Peluang upsell |

## Customer Health Score

| Komponen | Bobot | Indikator |
|----------|-------|-----------|
| Product Usage | 30% | Login frequency, feature adoption |
| Support Tickets | 20% | Jumlah & severity ticket |
| NPS/CSAT | 25% | Survey feedback |
| Payment History | 15% | Kelancaran pembayaran |
| Engagement | 10% | Respon terhadap komunikasi |

## Retention Strategy

1. **Proactive Support**: Hubungi sebelum ada masalah
2. **Value Realization**: Pastikan pelanggan mendapat value
3. **Relationship Building**: Bangun hubungan jangka panjang
4. **Success Planning**: Buat rencana sukses bersama

## Contoh Penggunaan

```
/cs onboarding PT ABC Corp
/cs health "John Doe - Enterprise"
/cs churn "Startup XYZ - 3 bulan tidak login"
/cs qbr PT Maju Jaya Q4 2024
```

## Limitasi

- Membutuhkan data CRM yang lengkap
- Health score perlu kalibrasi dengan data historis
