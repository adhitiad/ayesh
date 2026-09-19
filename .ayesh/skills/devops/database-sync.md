---
name: database-sync
description: "Sinkronisasi data antar database. Trigger: /db-sync [sumber] [target]"
---

# Database Sync

Sinkronisasi data antar database atau environment.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| Schema Sync | `/db-sync schema [sumber] [target]` | Sinkron struktur |
| Data Sync | `/db-sync data [tabel]` | Sinkron data |
| Migration | `/db-sync migrate [versi]` | Jalankan migrasi |
| Backup | `/db-sync backup [db]` | Backup database |
| Compare | `/db-sync compare [db1] [db2]` | Bandingkan database |

## Database yang Didukung

- PostgreSQL
- MySQL/MariaDB
- SQLite
- MongoDB (schema only)

## Contoh Penggunaan

```
/db-sync schema dev_db prod_db
/db-sync data users_table
/db-sync backup production_db
```

## Limitasi

- Perlu akses database source dan target
- Data sensitif harus di-handle dengan hati-hati
- Sync besar mungkin membutuhkan downtime
