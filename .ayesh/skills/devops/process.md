---
name: process
description: "Monitoring & manajemen proses Linux (ps, top, kill). Trigger: /process"
---

# Process Management

## View Processes
```bash
ps aux
ps aux | grep nginx
ps -ef | head -20
ps -eo pid,user,%cpu,%mem,command --sort=-%cpu | head -20
ps -eo pid,user,%cpu,%mem,command --sort=-%mem | head -20
pstree
```

## System Monitoring
```bash
top
htop
glances
nload
iostat
vmstat 1 5
dstat
```

## Resource Usage
```bash
free -h
cat /proc/meminfo
cat /proc/cpuinfo
nproc
lscpu
lscpu | grep "Model name"
```

## Top Processes by Resource
```bash
# CPU
ps aux --sort=-%cpu | head -10

# Memory
ps aux --sort=-%mem | head -10

# Disk
iotop
iotop -oP
```

## Process Control
```bash
kill PID
kill -9 PID
kill -15 PID
killall process_name
pkill -f pattern

# Background
command &
nohup command &
disown %1

# Foreground
jobs
fg %1
bg %1

# Signals
kill -l          # list signals
kill -HUP PID    # reload config
kill -USR1 PID   # custom signal
```

## Systemd Services
```bash
systemctl status service
systemctl start service
systemctl stop service
systemctl restart service
systemctl reload service
systemctl enable service
systemctl disable service

systemctl list-units --type=service
systemctl list-unit-files --type=service
journalctl -u service -f
journalctl -u service --since "1 hour ago"
```

## Crontab
```bash
crontab -l
crontab -e

# Format: minute hour day month weekday command
0 2 * * * /path/script.sh
*/5 * * * * /path/script.sh
0 0 * * 0 /path/weekly.sh
```

## Log Management
```bash
dmesg
dmesg | tail -50
journalctl -p err
journalctl -u service --since "2024-01-15"
journalctl --disk-usage
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| High CPU | `top`, `ps aux --sort=-%cpu` |
| High Memory | `free -h`, `ps aux --sort=-%mem` |
| Zombie processes | `ps aux | grep Z`, kill parent |
| Too many processes | `ps -eLf | wc -l` |
| Runaway process | `kill -9` |
