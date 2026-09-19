---
name: backup-strategy
description: "Strategi backup 3-2-1, retention, & verifikasi. Trigger: /backup"
---

# Backup Strategy Design

## 3-2-1 Strategy
```
3 - Minimal 3 copy data
2 - 2 media berbeda
1 - Minimal 1 offsite

Extended 3-2-1-1-0:
3 copy
2 media
1 offsite
1 immutable/offline
0 errors (verified)
```

### Implementation
```bash
# Local backup (copy 1)
tar -czvf /backup/local/data_$(date +%Y%m%d).tar.gz /data

# NAS backup (copy 2, different media)
rsync -avz /backup/local/ nas:/backup/

# Cloud backup (copy 3, offsite)
aws s3 sync /backup/local/ s3://backup-bucket/
```

## Backup Types

### Full Backup
```bash
tar -czvf /backup/full_$(date +%Y%m%d).tar.gz /data
```

### Incremental
```bash
tar -czvf /backup/incr_$(date +%Y%m%d).tar.gz \
    --newer-mtime="1 day ago" /data

tar -czvf /backup/incr.tar.gz -g /backup/snapshot.snar /data
```

### Differential
```bash
tar -czvf /backup/diff_$(date +%Y%m%d).tar.gz \
    --newer-mtime="$(cat /backup/last_full_date)" /data
```

## Retention Strategies

### GFS (Grandfather-Father-Son)
```bash
#!/bin/bash
BACKUP_DIR="/backup"
DATE=$(date +%Y%m%d)
DOW=$(date +%u)
DOM=$(date +%d)

# Daily
tar -czvf ${BACKUP_DIR}/daily/backup_${DATE}.tar.gz /data

# Weekly (Sunday)
if [ "$DOW" -eq 7 ]; then
    cp ${BACKUP_DIR}/daily/backup_${DATE}.tar.gz ${BACKUP_DIR}/weekly/
fi

# Monthly (1st)
if [ "$DOM" -eq "01" ]; then
    cp ${BACKUP_DIR}/daily/backup_${DATE}.tar.gz ${BACKUP_DIR}/monthly/
fi

# Cleanup
find ${BACKUP_DIR}/daily -mtime +7 -delete
find ${BACKUP_DIR}/weekly -mtime +28 -delete
find ${BACKUP_DIR}/monthly -mtime +365 -delete
```

### Rolling Retention
```bash
KEEP=10
ls -1t ${BACKUP_DIR}/*.tar.gz | tail -n +$((KEEP+1)) | xargs -r rm
```

## Verification

### Integrity Check
```bash
md5sum backup.tar.gz > backup.md5
md5sum -c backup.md5
tar -tzvf backup.tar.gz > /dev/null
gzip -t backup.tar.gz
```

### Restore Test
```bash
#!/bin/bash
TEST_DIR="/tmp/restore_test"
mkdir -p $TEST_DIR

tar -xzvf /backup/latest.tar.gz -C $TEST_DIR

ORIG_COUNT=$(find /data -type f | wc -l)
REST_COUNT=$(find $TEST_DIR -type f | wc -l)

if [ "$ORIG_COUNT" -eq "$REST_COUNT" ]; then
    echo "PASS"
else
    echo "FAIL: file count mismatch"
fi

rm -rf $TEST_DIR
```

## Common Scenarios

### Enterprise Backup
```bash
#!/bin/bash
LOG="/var/log/backup.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> $LOG; }

log "Starting DB backup"
mysqldump --all-databases | gzip > /backup/db_$(date +%Y%m%d).sql.gz

log "Starting file backup"
tar -czvf /backup/files_$(date +%Y%m%d).tar.gz /data

log "Syncing to NAS"
rsync -avz /backup/ nas:/backup/

log "Uploading to cloud"
aws s3 sync /backup/ s3://backup-bucket/

log "Verifying"
gzip -t /backup/*.gz

log "Cleaning old backups"
find /backup -mtime +7 -delete

log "Backup complete"
```

### Backup Monitoring
```bash
#!/bin/bash
BACKUP_DIR="/backup"
MAX_AGE=86400  # 24 hours

LATEST=$(ls -1t ${BACKUP_DIR}/*.tar.gz 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "CRITICAL: No backup files"
    exit 2
fi

AGE=$(($(date +%s) - $(stat -c %Y "$LATEST")))

if [ $AGE -gt $MAX_AGE ]; then
    echo "WARNING: Backup older than 24 hours"
    exit 1
fi

echo "OK: Latest backup $(basename $LATEST)"
exit 0
```

## Strategy Comparison
| Strategy | Storage | Restore Speed | Complexity |
|----------|---------|---------------|------------|
| Full | High | Fast | Low |
| Incremental | Low | Slow | High |
| Differential | Medium | Medium | Medium |
| GFS | Medium | Medium | Medium |

## Best Practices
```
1. Automate backups
2. Verify restore regularly
3. Encrypt sensitive backups
4. Monitor backup status
5. Document recovery procedures
6. Test recovery drills
```
