---
name: rsync
description: "File synchronization & backup dengan rsync. Trigger: /rsync"
---

# rsync File Sync & Backup

## Basic Usage
```bash
rsync -av source/ dest/
rsync -avz source/ dest/                  # compressed
rsync -avzP source/ dest/                 # with progress + resume
rsync -avz --delete source/ dest/         # mirror
rsync -avz --exclude='*.log' source/ dest/
rsync -avz --exclude-from='exclude.txt' source/ dest/
rsync -avz --bwlimit=1000 source/ dest/  # limit KB/s

# Dry run
rsync -avzn --delete source/ dest/
```

## Remote Sync
```bash
# Push
rsync -avz source/ user@remote:/path/dest/

# Pull
rsync -avz user@remote:/path/source/ dest/

# SSH with port/key
rsync -avz -e 'ssh -p 2222' source/ user@host:/path/
rsync -avz -e 'ssh -i ~/.ssh/key' source/ user@host:/path/
```

## Important
```bash
# Source path trailing slash matters!
rsync -av source/ dest/   # sync source CONTENTS to dest
rsync -av source dest/    # sync source DIRECTORY to dest/source
```

## Incremental Backup
```bash
#!/bin/bash
set -euo pipefail

SOURCE="/data/"
DEST="/backup/"
DATE=$(date +%Y%m%d_%H%M%S)
LATEST="$DEST/latest"
BACKUP="$DEST/$DATE"

# Incremental backup using hardlinks
rsync -avz --delete --link-dest="$LATEST" "$SOURCE" "$BACKUP"

# Update latest link
ln -snf "$BACKUP" "$LATEST"

# Keep last 7 days
find "$DEST" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```

## Common Scenarios

### Website Sync
```bash
rsync -avz --delete \
  --exclude='cache/' \
  --exclude='*.log' \
  --exclude='uploads/tmp/' \
  /var/www/html/ backup@remote:/backup/www/
```

### DB Backup Sync
```bash
mysqldump -u root -p database > /backup/db.sql
rsync -avzP /backup/db.sql backup@remote:/backup/mysql/
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Permission error | `--chmod`, cek target permissions |
| Connection timeout | Cek network, SSH config |
| Disk full | Bersihkan target, `--max-size` |
| Slow sync | `-z` compressed, `--bwlimit` |
