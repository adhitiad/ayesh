---
name: monitoring
description: "Monitoring & observability sistem (Prometheus, Grafana, logs). Trigger: /monitor"
---

# Monitoring & Observability

## Prometheus
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'app'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['app:3000']
```

### Common Queries
```promql
# CPU usage
100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk usage
(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100

# HTTP requests rate
rate(http_requests_total[5m])

# HTTP error rate
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Top 5 pods by CPU
topk(5, sum(rate(container_cpu_usage_seconds_total[5m])) by (pod))
```

## Alert Rules
```yaml
groups:
  - name: host
    rules:
      - alert: HighCPU
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU on {{ $labels.instance }}"

      - alert: HighMemory
        expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85
        for: 5m
        labels:
          severity: warning

      - alert: DiskSpaceLow
        expr: (1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100 > 90
        for: 5m
        labels:
          severity: critical
```

## Grafana
```bash
# API
curl -X POST http://admin:admin@localhost:3000/api/datasources -H "Content-Type: application/json" -d '
{
  "name": "Prometheus",
  "type": "prometheus",
  "url": "http://prometheus:9090",
  "access": "proxy"
}'

# Import dashboard
curl -X POST http://admin:admin@localhost:3000/api/dashboards/import -H "Content-Type: application/json" -d @dashboard.json
```

## Log Management

### Loki
```yaml
# loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 168h
```

```promql
# LogQL
{job="nginx"} |= "error"
{job="nginx"} !~ "health"
{job="nginx"} | logfmt | status >= 400
```

### ELK Stack
```json
// Elasticsearch query
{
  "query": {
    "bool": {
      "must": [
        { "match": { "level": "ERROR" } },
        { "range": { "@timestamp": { "gte": "now-1h" } } }
      ]
    }
  }
}
```

## Alertmanager
```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'slack'
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h

receivers:
  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/xxx'
        channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
```

## Uptime Monitoring
```bash
# Simple health check
curl -sf http://localhost:8080/health || exit 1

# Timeout
curl -sf --max-time 5 http://localhost:8080/health || exit 1
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Metrics missing | Cek scrape config, targets |
| Alert tidak fire | Cek rules, For duration |
| Grafana no data | Cek datasource, time range |
| Log tidak muncul | Cek Loki/ES connection |
| High latency | Cek Prometheus query performance |
