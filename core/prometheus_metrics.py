from prometheus_client import Counter, Histogram, Gauge, generate_latest
import time

# Metrics
REQUEST_COUNT = Counter('agent_requests_total', 'Total agent requests', ['agent_type', 'status'])
REQUEST_LATENCY = Histogram('agent_request_latency_seconds', 'Request latency', ['agent_type'])
ACTIVE_SESSIONS = Gauge('agent_active_sessions', 'Active sessions')

def record_request(agent_type: str, status: str, duration: float):
    REQUEST_COUNT.labels(agent_type=agent_type, status=status).inc()
    REQUEST_LATENCY.labels(agent_type=agent_type).observe(duration)

def get_metrics_data():
    return generate_latest()
