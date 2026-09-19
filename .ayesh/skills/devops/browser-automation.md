---
name: browser-automation
description: "Otomasi browser dengan Puppeteer/Playwright. Trigger: /browser-auto [tipe] [target]"
---

# Browser Automation

Otomasi interaksi browser untuk scraping, testing, atau automasi tugas.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| Scrape | `/browser-auto scrape [URL]` | Ekstrak konten |
| Screenshot | `/browser-auto ss [URL]` | Ambil screenshot |
| Form Fill | `/browser-auto fill [URL] [data]` | Isi form |
| Click | `/browser-auto click [URL] [selector]` | Klik elemen |
| Test | `/browser-auto test [URL] [skenario]` | Jalankan test |

## Contoh Penggunaan

```
/browser-auto scrape https://example.com/pricing
/browser-auto ss https://app.example.com/dashboard
/browser-auto test https://example.com/login "login dengan valid"
```

## Limitasi

- Tidak dapat bypass CAPTCHA
- Beberapa website memblokir automated access
- Gunakan dengan bertanggung jawab
