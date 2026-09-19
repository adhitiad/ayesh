---
name: disaster-recovery
description: "Rencana & eksekusi disaster recovery. Trigger: /disaster"
---

# Disaster Recovery

## Core Concepts

### RTO & RPO
```
RPO (Recovery Point Objective)
- Jumlah data yang hilang
- Menentukan frekuensi backup

RTO (Recovery Time Objective)
- Waktu pemulihan yang diterima
- Menentukan strategi pemulihan

Contoh:
- RPO = 1 jam → backup per jam
- RTO = 4 jam → perlu hot standby
```

### Recovery Strategies
```
Cold Standby
- Biaya minimum
- RTO terlama
- Untuk sistem non-kritis

Warm Standby
- Biaya sedang
- RTO sedang
- Sync data periodik

Hot Standby
- Biaya tertinggi
- RTO tercepat
- Sync real-time
```

## Database Recovery

### PostgreSQL
```bash
# Restore dari backup
pg_restore -d database backup.dump

# PITR Recovery
restore_command = 'cp /archive/%f %p'
recovery_target_time = '2024-01-15 10:00:00'

# Promote standby
pg_ctl promote -D /var/lib/postgresql/data
```

### MySQL
```bash
# Restore dari backup
mysql -u root -p < full_backup.sql

# Apply binlog
mysqlbinlog mysql-bin.000001 | mysql -u root -p

# PITR
mysqlbinlog --stop-datetime="2024-01-15 10:00:00" mysql-bin.* | mysql -u root -p
```

### Redis
```bash
# Dari RDB
cp backup.rdb /var/lib/redis/dump.rdb
systemctl restart redis

# Dari AOF
cp backup.aof /var/lib/redis/appendonly.aof
redis-check-aof --fix appendonly.aof
systemctl restart redis
```

## System Recovery

### File System
```bash
tar -xzvf /backup/system.tar.gz -C /
rsync -avz /backup/system/ /
```

### Boot Repair
```bash
mount /dev/sda1 /mnt
mount --bind /dev /mnt/dev
mount --bind /proc /mnt/proc
mount --bind /sys /mnt/sys
chroot /mnt
grub-install /dev/sda
update-grub
```

## Failover

### Keepalived
```bash
vrrp_instance VI_1 {
    priority 50    # Lower to failover
}
systemctl reload keepalived
```

### DNS Failover
```bash
# Lower TTL, change A record
dig +short example.com
```

## Recovery Script
```bash
#!/bin/bash
echo "1. Assessing damage..."
echo "2. Notifying team..."
echo "3. Restoring network..."
echo "4. Restoring database..."
mysql -u root -p < /backup/latest.sql
echo "5. Starting application..."
systemctl start application
echo "6. Verifying..."
curl -s http://localhost/health
echo "7. Done!"
```

## DR Drill
```bash
#!/bin/bash
LOG="/var/log/dr-drill.log"
echo "$(date): Starting DR drill" >> $LOG
# 1. Switch to DR site
# 2. Verify services
# 3. Test data consistency
# 4. Record actual RTO
# 5. Switch back
```

## DR Checklist
| Item | Check |
|------|-------|
| Backup | Integritas, dapat restore |
| Dokumentasi | Langkah restore, kontak |
| Network | DNS, IP, firewall |
| Data | Konsistensi data |
| Aplikasi | Config, dependensi, cert |

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Backup corrupt | Verifikasi checksum |
| Restore gagal | Cek versi, permissions |
| Replikasi delay | `pg_stat_replication` |
| DNS propagate lambat | Turunkan TTL |
