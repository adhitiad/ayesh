"""Load test Ayesh API via Locust (k6 alternative — lihat roadmap: Load test).

Jalankan (server API harus hidup dulu di :8080):
  locust -f tests/load/locustfile.py --host http://localhost:8080
  # lalu buka http://localhost:8089 atau headless:
  locust -f tests/load/locustfile.py --host http://localhost:8080 \
      -u 10 -r 2 -t 60s --headless --csv=load_results

Catatan:
- Mode default HANYA endpoint infra (health/metrics) — TANPA panggil LLM.
- Set LOADTEST_CHAT=1 (env) untuk menambah user POST /chat (butuh LLM key;
  pakai RATE_LIMIT_* tinggi / restart server dengan limit longgar karena
  rate limit per-IP aktif → 429 dianalisis terpisah, bukan error).
- 429 dihitung sebagai 'rate_limited' (bukan failure) agar laporan bersih.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, constant_pacing, task

CHAT_ENABLED = os.getenv("LOADTEST_CHAT", "0").strip().lower() in {"1", "true", "yes"}


def _check(res, name: str):
    """Tag response: 429 = rate_limited (bukan error), selain itu ikut status."""
    if res is None:
        res.failure(f"{name}: no response")
        return
    if res.status_code == 429:
        res.success()
        res.request.meta["description"] = f"{name} [rate_limited]"
        return
    if res.status_code >= 500:
        res.failure(f"{name}: {res.status_code}")
        return
    res.success()


class InfraUser(HttpUser):
    """Endpoint ringan tanpa LLM: health + metrics (Prometheus scrape path)."""

    wait_time = constant_pacing(0.2)

    @task(5)
    def health(self):
        with self.client.get("/health", name="/health", catch_response=True) as res:
            _check(res, "health")

    @task(2)
    def metrics_json(self):
        with self.client.get("/metrics", name="/metrics", catch_response=True) as res:
            _check(res, "metrics")

    @task(3)
    def metrics_prometheus(self):
        with self.client.get("/metrics/prometheus", name="/metrics/prometheus", catch_response=True) as res:
            _check(res, "metrics_prometheus")


class ChatUser(HttpUser):
    """POST /chat — aktif hanya bila LOADTEST_CHAT=1 (kenakan biaya LLM)."""

    wait_time = between(1, 3)
    weight = 1 if CHAT_ENABLED else 0

    @task
    def chat(self):
        payload = {
            "message": "halo, singkat saja jawabannya",
            "session_id": f"loadtest_{self.environment.process_id}",
        }
        with self.client.post("/chat", json=payload, name="/chat", catch_response=True) as res:
            _check(res, "chat")
