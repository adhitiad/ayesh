---
name: gmail-workflows
description: "Otomasi email Gmail. Trigger: /gmail-auto [tipe] [target]"
---

# Gmail Workflows

Otomasi pengelolaan email di Gmail.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| Search | `/gmail-auto search [query]` | Cari email |
| Filter | `/gmail-auto filter [kriteria]` | Buat filter |
| Template | `/gmail-auto template [nama]` | Buat template |
| Schedule | `/gmail-auto schedule [email] [waktu]` | Jadwalkan kirim |
| Auto-Reply | `/gmail-auto auto-reply [kondisi]` | Balas otomatis |

## Contoh Penggunaan

```
/gmail-auto search "from:boss@company.com subject:urgent"
/gmail-auto filter "from:*@newsletter.com label:Newsletter"
/gmail-auto template "Follow-up setelah meeting"
/gmail-auto schedule client@email.com "besok jam 9"
```

## Limitasi

- Membutuhkan akses Gmail API
- Tidak dapat bypass security policy organisasi
