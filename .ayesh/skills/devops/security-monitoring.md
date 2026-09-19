---
name: security-monitoring
description: "Deteksi ancaman keamanan siber. Trigger: /security [tipe] [target]"
---

# Security Monitoring

Monitoring dan deteksi ancaman keamanan siber.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| Vulnerability Scan | `/security scan [target]` | Scan kerentanan |
| Log Analysis | `/security log [file]` | Analisis log keamanan |
| Config Audit | `/security audit [config]` | Audit konfigurasi |
| Incident Report | `/security incident [deskripsi]` | Buat laporan insiden |

## Checklist Keamanan

1. **Authentication**: Pastikan autentikasi kuat
2. **Authorization**: Periksa kontrol akses
3. **Encryption**: Validasi enkripsi data
4. **Logging**: Pastikan logging memadai
5. **Backup**: Verifikasi backup reguler

## Contoh Penggunaan

```
/web-config audit nginx.conf
/security log /var/log/auth.log
/security incident Brute force login attempt
```

## Limitasi

- Tidak menggantikan tools keamanan profesional
- Untuk audit mendalam, gunakan tools khusus (Nessus, Qualys)
