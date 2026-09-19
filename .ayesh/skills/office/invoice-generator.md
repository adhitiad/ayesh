---
name: invoice-generator
description: dipakai saat user meminta pembuatan invoice, faktur, atau tagihan. trigger: /invoice
---

# Skill: Pembuatan Invoice

Jalankan setiap kali user meminta pembuatan invoice/faktur profesional.

## Langkah

1. **Kumpulkan informasi:**
   - Data bisnis user (nama, alamat, NPWP jika ada)
   - Data klien (nama, alamat, kontak)
   - Item/layanan (deskripsi, kuantitas, harga satuan)
   - Nomor invoice (atau usulkan format: INV-YYYY-XXXX)
   - Syarat pembayaran (jatuh tempo, metode bayar)
   - Mata uang (IDR, USD, EUR, dll)
   - Pajak (PPN, pajak daerah, dll)

2. **Hitung:**
   - Subtotal = total item
   - Pajak (PPN Indonesia: 11%)
   - Total = subtotal + pajak

3. **Generate invoice:**
   - Format markdown atau teks
   - Layout profesional dengan kolom yang jelas

## Komponen Wajib Invoice

| Elemen | Keterangan |
|--------|------------|
| Nomor Invoice | Unik, berurutan |
| Tanggal | Tanggal penerbitan |
| Jatuh Tempo | Batas waktu pembayaran |
| Dari | Data bisnis user |
| Kepada | Data klien |
| Item | Deskripsi, qty, harga, jumlah |
| Total | Total yang harus dibayar |
| Syarat Bayar | Net 15/30/60, dll |

## Pajak di Indonesia

| Jenis | Tarif | Keterangan |
|-------|-------|------------|
| PPN | 11% | Untuk bisnis terdaftar PKP |
| PPh 23 | 2% | Untuk jasa (dipotong klien) |
| PPh 4(2) | 0,5% | Untuk UMKM (pph final) |

## Format Nomor Invoice

| Format | Contoh | Cocok Untuk |
|--------|--------|-------------|
| Urut | 001, 002, 003 | Volume rendah |
| Tahun-Urut | 2026-001 | Mudah lacak per tahun |
| Klien-Urut | ACME-001 | Banyak klien |

## Aturan
- Jangan pernah nomor ulang invoice
- Sertakan deskripsi jelas (bukan "Konsultasi" tapi "Konsultasi strategi marketing - Rencana Q1")
- Selalu sertakan syarat pembayaran
- Untuk B2B, sertakan NPWP

## Limitasi
- Hanya generate teks, bukan PDF
- Perhitungan pajak adalah estimasi - verifikasi dengan akuntan
- Tidak bisa integrasi dengan software akuntansi
