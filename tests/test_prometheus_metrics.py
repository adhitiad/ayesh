import unittest

from fastapi.testclient import TestClient

from src.core.observability.prometheus_metrics import (
    DURATION_BUCKETS,
    iter_metric_names,
    record_request,
    render,
    reset_for_tests,
    snapshot_counts,
)


class TestPrometheusRender(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_counter_format(self):
        record_request("/chat", "POST", 200, 0.05)
        record_request("/chat", "POST", 200, 0.05)
        record_request("/chat", "POST", 500, 0.2)
        text = render()
        self.assertIn('ayesh_http_requests_total{route="/chat",method="POST",status="200"} 2', text)
        self.assertIn('ayesh_http_requests_total{route="/chat",method="POST",status="500"} 1', text)
        self.assertIn("# TYPE ayesh_http_requests_total counter", text)

    def test_histogram_format(self):
        record_request("/health", "GET", 200, 0.004)
        record_request("/health", "GET", 200, 0.2)
        text = render()
        self.assertIn("# TYPE ayesh_http_request_duration_seconds histogram", text)
        self.assertIn('ayesh_http_request_duration_seconds_bucket{route="/health",le="0.005"} 1', text)
        self.assertIn('ayesh_http_request_duration_seconds_bucket{route="/health",le="0.25"} 2', text)
        self.assertIn('ayesh_http_request_duration_seconds_bucket{route="/health",le="+Inf"} 2', text)
        self.assertIn('ayesh_http_request_duration_seconds_count{route="/health"} 2', text)
        self.assertIn("ayesh_http_request_duration_seconds_sum", text)
        self.assertEqual(DURATION_BUCKETS[0], 0.005)

    def test_label_escaping(self):
        record_request('/we"ird\\path', "GET", 200, 0.01)
        text = render()
        self.assertIn('route="/we\\"ird\\\\path"', text)

    def test_health_gauges_present(self):
        text = render()
        self.assertIn("ayesh_postgres_up ", text)
        self.assertIn("ayesh_redis_up ", text)
        self.assertIn("ayesh_last_query_ms ", text)
        self.assertIn("# TYPE ayesh_postgres_up gauge", text)

    def test_metric_names_set(self):
        record_request("/chat", "POST", 200, 0.01)
        names = iter_metric_names(render().splitlines())
        self.assertIn("ayesh_http_requests_total", names)
        self.assertIn("ayesh_http_request_duration_seconds_bucket", names)
        self.assertIn("ayesh_postgres_up", names)

    def test_reset_and_snapshot(self):
        record_request("/a", "GET", 200, 0.01)
        self.assertEqual(snapshot_counts().get(("/a", "GET", "200")), 1)
        reset_for_tests()
        self.assertEqual(snapshot_counts(), {})


class TestMetricsEndpoint(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_prometheus_endpoint_content_type(self):
        from api_server import app
        from src.core.auth.auth import create_user
        owner = create_user("prom_owner", "owner")
        from fastapi.testclient import TestClient as TC2
        with TC2(app, raise_server_exceptions=False) as client:
            resp = client.get("/metrics/prometheus", headers={"X-API-Key": owner["api_key"]})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/plain"))
        self.assertIn("version=0.0.4", resp.headers["content-type"])
        self.assertIn("ayesh_http_requests_total", resp.text)
        self.assertIn("ayesh_postgres_up", resp.text)

    def test_json_metrics_backward_compat(self):
        from api_server import app
        from src.core.auth.auth import create_user
        owner = create_user("prom_owner2", "owner")
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/metrics", headers={"X-API-Key": owner["api_key"]})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("postgres_healthy", body)
        self.assertIn("request_id", body)

    def test_requests_recorded_with_route_label(self):
        from api_server import app

        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/health")
        counts = snapshot_counts()
        # Label memakai pola route FastAPI, bukan path mentah yang bisa meledak.
        matched = [k for k in counts if k[0] == "/health" and k[2] == "200"]
        self.assertTrue(matched, f"route label /health tidak ditemukan: {counts}")


if __name__ == "__main__":
    unittest.main()
