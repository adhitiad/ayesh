---
name: file-ops
description: "Operasi file & direktori Linux (find, chmod, rsync). Trigger: /file"
---

# File & Directory Operations

## File Search
```bash
find /path -name "*.log"
find /path -iname "*.LOG"           # case insensitive
find /path -type f                  # files only
find /path -type d                  # directories only
find /path -type l                  # symlinks
find /path -mtime -7                # modified within 7 days
find /path -mtime +30               # modified > 30 days ago
find /path -mmin -60                # modified within 60 min
find /path -size +100M              # > 100MB
find /path -name "*.log" -mtime +7 -size +10M

locate filename
updatedb
```

## File Operations
```bash
cp file1 file2
cp -r dir1 dir2
cp -p file1 file2

mv file1 file2
mv file1 /path/to/dest/

rm file
rm -rf dir
rm -i file

touch file
mkdir -p dir1/dir2/dir3
```

## Batch Operations
```bash
rename 's/old/new/' *.txt
for f in *.txt; do mv "$f" "${f%.txt}.md"; done

find /path -name "*.tmp" -delete
find /path -name "*.log" -mtime +30 -exec rm {} \;
find /src -name "*.conf" -exec cp {} /dest/ \;
```

## View Files
```bash
cat file
head -n 20 file
tail -n 20 file
tail -f file
less file

wc -l file
wc -w file
wc -c file
```

## File Comparison
```bash
diff file1 file2
diff -u file1 file2
diff -r dir1 dir2
sdiff file1 file2
vimdiff file1 file2
```

## Permissions
```bash
ls -la
stat file

chmod 755 file
chmod 644 file
chmod u+x file
chmod g-w file
chmod o=r file
chmod a+r file
chmod -R 755 dir

chown user file
chown user:group file
chown -R user:group dir
```

## Common Scenarios

### Clean Large Files
```bash
find / -type f -size +100M -exec ls -lh {} \; 2>/dev/null
du -ah /path | sort -rh | head -20
```

### Find Recent Files
```bash
find /path -type f -mtime -1
ls -lt /path | head -20
```

### Batch Replace Content
```bash
sed -i 's/old/new/g' file
find /path -name "*.conf" -exec sed -i 's/old/new/g' {} \;
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Permission denied | `sudo` atau cek permissions |
| Disk penuh | `df -h`, `du -sh *` |
| Special chars in filename | Quote: `rm "file name"` |
| Hapus banyak file lambat | `rsync --delete` atau `find -delete` |
