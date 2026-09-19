---
name: devops-automation
description: "Otomasi CI/CD dan infrastruktur. Trigger: /devops [tipe] [target]"
---

# DevOps Automation

Otomasi pipeline CI/CD dan manajemen infrastruktur.

## Fitur

| Fitur | Command | Keterangan |
|-------|---------|------------|
| CI/CD Pipeline | `/devops cicd [repo]` | Buat pipeline |
| Docker | `/devops docker [app]` | Buat Dockerfile |
| Kubernetes | `/devops k8s [app]` | Deploy k8s manifest |
| Terraform | `/devops terraform [infra]` | Buat infra as code |
| Monitoring | `/devops monitor [app]` | Setup monitoring |

## Contoh Penggunaan

```
/devops cicd api-server-python
/devops docker web-app-react
/devops k8s backend-service
/devops terraform aws-vpc
```

## Limitasi

- Hanya generate konfigurasi, tidak langsung deploy
- Perlu akses ke platform terkait untuk eksekusi
