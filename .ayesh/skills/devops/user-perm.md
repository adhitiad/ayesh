---
name: user-perm
description: "Manajemen user, group, & permission Linux. Trigger: /userperm"
---

# User & Permissions Management

## Users
```bash
id username
id -u username        # UID
id -g username        # GID
id -gn username       # group name
id -un username       # user name

useradd -m -s /bin/bash -G sudo username
useradd -m -d /home/user -s /bin/zsh username
useradd -r -s /bin/false systemuser

passwd username
passwd -l username    # lock
passwd -u username    # unlock
passwd -e username    # expire
chage -l username

usermod -aG sudo username
usermod -aG docker username
usermod -s /bin/zsh username
usermod -L username   # lock
usermod -U username   # unlock

userdel -r username
userdel username
```

## Groups
```bash
groupadd groupname
groupdel groupname
groupmod -n newname oldname

getent group groupname
cat /etc/group
cat /etc/passwd

# Primary vs Supplementary
usermod -g primary_group username
usermod -aG supplementary_group username
```

## File Permissions
```bash
chmod 755 file
chmod 644 file
chmod 600 file
chmod 700 dir
chmod u+x file
chmod g+w file
chmod o-r file
chmod a+r file
chmod -R 755 dir

chown user file
chown user:group file
chown -R user:group dir
chgrp group file
```

## Special Permissions
```bash
chmod u+s file        # SUID
chmod g+s dir         # SGID
chmod +t dir          # Sticky bit

chmod 4755 file       # SUID numeric
chmod 2755 dir        # SGID numeric
chmod 1755 dir        # Sticky numeric
```

## ACL
```bash
getfacl file
setfacl -m u:user:rw file
setfacl -m g:group:r file
setfacl -m d:u:user:rw dir
setfacl -x u:user file
setfacl -b file
```

## Sudo
```bash
visudo
cat /etc/sudoers
cat /etc/sudoers.d/

# /etc/sudoers syntax
username ALL=(ALL:ALL) ALL
%group ALL=(ALL:ALL) ALL
username ALL=(ALL) NOPASSWD: ALL
username ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
```

## Password Policy
```bash
# /etc/login.defs
PASS_MAX_DAYS   90
PASS_MIN_DAYS   7
PASS_WARN_AGE   14
PASS_MIN_LEN    8

# Per-user
chage -M 90 username
chage -m 7 username
chage -W 14 username
chage -l username
```

## Audit
```bash
last
lastb
lastlog
who
w
lastcomm
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Permission denied | `ls -la`, cek ownership |
| Cannot sudo | cek `/etc/sudoers` |
| Locked account | `passwd -u`, `chage -l` |
| Too many users | `last`, bersihkan tidak aktif |
| Wrong group | `id`, `usermod -aG` |
