---
name: system-admin
description: "Administrasi sistem Linux (disk, memory, config). Trigger: /sysadmin"
---

# System Administration

## System Info
```bash
uname -a
cat /etc/os-release
hostnamectl
uptime
date
timedatectl
```

## Disk Management
```bash
df -h
df -h / /home
du -sh /path/*
du -sh /var/log/*
lsblk

fdisk -l
parted /dev/sdb

# LVM
lvdisplay
lvcreate -L 10G -n lv_data vg0
lvextend -L +5G /dev/vg0/lv_data
resize2fs /dev/vg0/lv_data
```

## Memory
```bash
free -h
cat /proc/meminfo
vmstat 1 5
slabtop
```

## Users
```bash
id username
useradd -m -s /bin/bash username
passwd username
usermod -aG group username
userdel -r username

groupadd groupname
usermod -aG groupname username

last
lastb
lastlog
```

## Systemd
```bash
systemctl list-units
systemctl status service
systemctl start/stop/restart service
systemctl enable/disable service
systemctl cat service
systemctl edit service
systemctl daemon-reload
```

## Logs
```bash
journalctl -f
journalctl -u service --since "1 hour ago"
journalctl -p err
journalctl --disk-usage

cat /var/log/syslog
cat /var/log/messages
cat /var/log/secure
cat /var/log/auth.log
```

## Package Management
```bash
# Debian/Ubuntu
apt update
apt install package
apt remove package
apt upgrade
dpkg -l | grep package

# RHEL/CentOS
yum install package
dnf install package
rpm -qa | grep package
```

## Scheduled Tasks
```bash
crontab -e
crontab -l
at now + 5 minutes
batch
```

## Boot
```bash
systemctl get-default
systemctl set-default multi-user.target
systemctl set-default graphical.target
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Disk penuh | `df -h`, `du -sh *` |
| Memory tidak cukup | `free -h`, cek proses |
| Service tidak mulai | `journalctl -u service` |
| Login gagal | `lastb`, `/var/log/auth.log` |
| System lambat | `top`, `vmstat`, cek I/O |
