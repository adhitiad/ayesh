---
name: network
description: "Monitoring & troubleshooting jaringan Linux (netstat, ss, curl). Trigger: /network"
---

# Network Tools

## Connection Analysis
```bash
ss -tulnp
ss -tunap | grep :80
ss -s
ss state established
ss state time-wait
ss -tnp | grep ESTABLISHED

netstat -tulnp
netstat -anp | grep :80
netstat -s | grep retransmit
```

## DNS
```bash
dig example.com
dig example.com +short
dig example.com A
dig example.com MX
dig example.com NS
dig +trace example.com

nslookup example.com
host example.com
```

## HTTP & Web
```bash
curl -I https://example.com
curl -v https://example.com
curl -s -o /dev/null -w "%{http_code}" https://example.com
curl -X POST -d "data" https://example.com/api
curl -H "Authorization: Bearer token" https://example.com
curl -o file.tar.gz https://example.com/file.tar.gz
curl --connect-timeout 5 https://example.com

wget https://example.com/file.tar.gz
wget -c https://example.com/file.tar.gz
```

## Tracing & Diagnostics
```bash
traceroute example.com
mtr example.com
ping -c 5 example.com
arp -a
ip neigh
```

## Network Configuration
```bash
ip addr
ip addr show eth0
ip route
ip route show
ip link show
ip link set eth0 up
ip route add default via 192.168.1.1
```

## Firewall
```bash
# iptables
iptables -L -n
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -j DROP

# firewalld
firewall-cmd --list-all
firewall-cmd --add-port=8080/tcp --permanent
firewall-cmd --reload

# ufw
ufw status
ufw allow 80/tcp
ufw enable
```

## Bandwidth Monitoring
```bash
iftop
nethogs
bmon
vnstat
vnstat -d
vnstat -h
```

## Remote Access
```bash
ssh user@host
ssh -p 2222 user@host
ssh -i ~/.ssh/key user@host

scp file user@host:/path/
scp -r dir user@host:/path/
rsync -avz dir user@host:/path/
```

## SSL/TLS
```bash
openssl s_client -connect host:443
openssl s_client -connect host:443 -servername example.com
openssl x509 -in cert.pem -text -noout
openssl x509 -in cert.pem -noout -dates
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Connection refused | `ss -tlnp`, cek service |
| DNS tidak resolve | `dig`, `/etc/resolv.conf` |
| Slow connection | `mtr`, `ping` |
| TLS error | `openssl s_client` |
| High retransmit | `netstat -s`, cek link |
