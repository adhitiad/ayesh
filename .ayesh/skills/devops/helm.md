---
name: helm
description: "Package manager Kubernetes (Helm). Trigger: /helm"
---

# Helm Package Manager

## Basic Commands
```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm repo list
helm search repo nginx
helm search hub nginx

helm install my-release bitnami/nginx
helm install my-release bitnami/nginx -f values.yaml
helm install my-release bitnami/nginx --set replicaCount=3
helm install my-release bitnami/nginx -n mynamespace

helm list
helm list -a
helm list -n mynamespace

helm status my-release
helm history my-release

helm upgrade my-release bitnami/nginx --set replicaCount=5
helm upgrade my-release bitnami/nginx -f values.yaml
helm upgrade --install my-release bitnami/nginx

helm rollback my-release 1
helm uninstall my-release
helm uninstall my-release -n mynamespace
```

## Chart Management
```bash
helm create mychart
helm package mychart
helm lint mychart
helm template mychart
helm template mychart -f values.yaml
helm install myrelease ./mychart
helm diff upgrade myrelease ./mychart

helm show chart bitnami/nginx
helm show values bitnami/nginx
helm show readme bitnami/nginx
helm show all bitnami/nginx
```

## Values
```yaml
replicaCount: 3
image:
  repository: nginx
  tag: "1.25"
  pullPolicy: IfNotPresent
service:
  type: ClusterIP
  port: 80
resources:
  limits:
    cpu: 500m
    memory: 128Mi
  requests:
    cpu: 250m
    memory: 64Mi
```

```bash
helm install myrelease ./mychart -f values.yaml
helm install myrelease ./mychart --set replicaCount=3
helm install myrelease ./mychart --set image.tag=1.25 --set service.type=LoadBalancer
```

## Chart Structure
```
mychart/
  Chart.yaml
  values.yaml
  charts/
  templates/
    deployment.yaml
    service.yaml
    ingress.yaml
    configmap.yaml
    secret.yaml
    hpa.yaml
    _helpers.tpl
  README.md
```

## Template Functions
```yaml
{{ .Values.replicaCount }}
{{ .Release.Name }}
{{ .Release.Namespace }}
{{ include "mychart.fullname" . }}
{{ required "Name is required" .Values.name }}
{{ toYaml .Values.resources | nindent 4 }}
{{ if .Values.ingress.enabled }}...{{ end }}
{{ range .Values.users }}...{{ end }}
{{ randAlphaNum 10 | b64enc }}
```

## Secrets Management
```bash
helm plugin install https://github.com/jkroepke/helm-secrets
helm secrets install myrelease -f secrets.yaml ./mychart
helm secrets upgrade myrelease -f secrets.yaml ./mychart
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Install gagal | `helm status`, `kubectl describe` |
| Template error | `helm template`, `helm lint` |
| Upgrade stuck | `helm history`, cek events |
| Rollback needed | `helm rollback` |
| Chart tidak ditemukan | `helm repo update`, `helm search` |
