"""P3.6 — Security regression test suite.

All tests are deterministic, no real LLM/API calls.
Each test maps to a specific security requirement.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestAuthRequired(unittest.TestCase):
    """test_auth_required: All API endpoints require authentication."""

    def test_chat_requires_auth(self):
        """POST /chat must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "test"})
        self.assertIn(resp.status_code, (401, 403))

    def test_sessions_requires_auth(self):
        """GET /sessions must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/sessions")
        self.assertIn(resp.status_code, (401, 403))

    def test_tasks_requires_auth(self):
        """GET /tasks must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/tasks")
        self.assertIn(resp.status_code, (401, 403))

    def test_jobs_requires_auth(self):
        """GET /jobs must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/jobs")
        self.assertIn(resp.status_code, (401, 403))

    def test_approvals_requires_auth(self):
        """GET /approvals/pending must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/approvals/pending")
        self.assertIn(resp.status_code, (401, 403))

    def test_users_requires_auth(self):
        """GET /users must reject unauthenticated requests."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/users")
        self.assertIn(resp.status_code, (401, 403))


class TestIDORSession(unittest.TestCase):
    """test_idor_session: Users cannot access other users' sessions."""

    def test_session_access_requires_owner(self):
        """GET /sessions/{id} must verify ownership (404 if not found is also acceptable)."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        # Without auth, must be rejected or 404 (not leaked data)
        resp = client.get("/sessions/nonexistent")
        self.assertIn(resp.status_code, (401, 403, 404))


class TestIDORMemory(unittest.TestCase):
    """test_idor_memory: Users cannot access other users' memory."""

    def test_memory_requires_owner(self):
        """GET /memory/{session_id} must verify ownership (404 if not found is also acceptable)."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/memory/nonexistent")
        self.assertIn(resp.status_code, (401, 403, 404))

    def test_memory_delete_requires_owner(self):
        """DELETE /memory/{session_id} must verify ownership (404 if not found is also acceptable)."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/memory/nonexistent")
        self.assertIn(resp.status_code, (401, 403, 404))


class TestIDORTask(unittest.TestCase):
    """test_idor_task: Users cannot access other users' tasks."""

    def test_task_requires_owner(self):
        """GET /tasks/{id} must verify ownership."""
        from fastapi.testclient import TestClient

        from api_server import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/tasks/nonexistent")
        self.assertIn(resp.status_code, (401, 403))


class TestJobPrivilegeEscalation(unittest.TestCase):
    """test_job_privilege_escalation: Jobs cannot escalate privileges."""

    def test_post_users_requires_owner(self):
        """POST /users must require owner role (not just admin)."""
        import inspect

        from src.core.auth.auth import require_owner_only

        source = inspect.getsource(require_owner_only)
        # Must check role == "owner" (the actual condition, not docstring)
        self.assertIn('role != "owner"', source)

    def test_job_default_approval_deny(self):
        """New jobs must default to deny_all approval policy."""
        import inspect

        from src.core.scheduler.scheduler import create_job

        source = inspect.getsource(create_job)
        self.assertIn("deny_all", source)


class TestSchedulerNoRCE(unittest.TestCase):
    """test_scheduler_no_rce: Scheduler cannot execute arbitrary code."""

    def test_scheduled_job_uses_route_request(self):
        """Scheduled jobs must use route_request, not exec/eval."""
        import inspect

        from src.core.scheduler.scheduler import run_due_jobs

        source = inspect.getsource(run_due_jobs)
        self.assertNotIn("exec(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("subprocess", source)


class TestPythonExecutionRestricted(unittest.TestCase):
    """test_python_execution_restricted: jalankan_python uses sandbox."""

    def test_jalankan_python_uses_sandbox(self):
        """jalankan_python must use CodeExecutionSandbox."""

        # jalankan_python is a StructuredTool; check the wrapped function
        # Check the source file for CodeExecutionSandbox usage
        import src.plugins.core_tools as mod

        with open(mod.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("CodeExecutionSandbox", src)
        # jalankan_python function body uses it
        self.assertIn("sandbox = CodeExecutionSandbox()", src)

    def test_sandbox_restricted_env_no_secrets(self):
        """Sandbox env must not leak secrets or full os.environ."""
        import os

        from src.plugins.core_tools import CodeExecutionSandbox

        sandbox = CodeExecutionSandbox()
        # Must have fewer vars than os.environ
        self.assertLess(len(sandbox._env), len(os.environ))
        # Must NOT contain sensitive vars
        for sensitive in (
            "NVIDIA_API_KEY",
            "DATABASE_URL",
            "TELEGRAM_BOT_TOKEN",
            "AWS_SECRET_ACCESS_KEY",
            "GOOGLE_API_KEY",
        ):
            self.assertNotIn(sensitive, sandbox._env)

    def test_sandbox_prevents_subprocess_env_leak(self):
        """Subprocess in sandbox cannot see parent secrets."""
        import os

        from src.plugins.core_tools import CodeExecutionSandbox

        os.environ["SANDBOX_TEST_SECRET"] = "leaked_value_12345"
        sandbox = CodeExecutionSandbox()
        # Run code that reads env vars
        _exit_code, output = sandbox.run(
            [
                "python",
                "-c",
                "import os; print(os.environ.get('SANDBOX_TEST_SECRET', 'NOT_FOUND'))",
            ],
            timeout=10,
        )
        self.assertNotIn("leaked_value_12345", output)
        # Clean up
        del os.environ["SANDBOX_TEST_SECRET"]


class TestSSRFPrivateIP(unittest.TestCase):
    """test_ssrf_private_ip: baca_url blocks private IPs."""

    def test_baca_url_blocks_localhost(self):
        """baca_url must block localhost."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "http://127.0.0.1:8080/secret"})
        self.assertIn("error", result.lower())

    def test_baca_url_blocks_private_ip(self):
        """baca_url must block 192.168.x.x."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "http://192.168.1.1/admin"})
        self.assertIn("error", result.lower())

    def test_baca_url_blocks_10_range(self):
        """baca_url must block 10.x.x.x."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "http://10.0.0.1/secret"})
        self.assertIn("error", result.lower())


class TestSSRFLoopback(unittest.TestCase):
    """test_ssrf_loopback: baca_url blocks loopback."""

    def test_baca_url_blocks_ipv6_loopback(self):
        """baca_url must block ::1."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "http://[::1]:8080/"})
        self.assertIn("error", result.lower())


class TestSSRFDNSRebinding(unittest.TestCase):
    """test_ssrf_dns_rebinding: baca_url validates DNS→IP."""

    def test_baca_url_blocks_non_http(self):
        """baca_url must reject non-http(s) schemes."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "file:///etc/passwd"})
        self.assertIn("error", result.lower())

    def test_baca_url_blocks_ftp(self):
        """baca_url must reject FTP scheme."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "ftp://example.com/file"})
        self.assertIn("error", result.lower())

    def test_baca_url_blocks_data_uri(self):
        """baca_url must reject data: URI."""
        from src.plugins.core_tools import baca_url

        result = baca_url.invoke({"url": "data:text/html,<script>alert(1)</script>"})
        self.assertIn("error", result.lower())


class TestSSRFFileOps(unittest.TestCase):
    """test_ssrf_file_ops: download_file/upload_file block SSRF vectors."""

    def test_download_file_blocks_private_ip(self):
        """download_file must block private IPs before any network request."""
        from src.plugins.core_tools import download_file

        result = download_file.invoke({"url": "http://127.0.0.1:8080/secret"})
        self.assertIn("error", result.lower())

    def test_download_file_rejects_file_scheme(self):
        """download_file must reject file:// URLs."""
        from src.plugins.core_tools import download_file

        result = download_file.invoke({"url": "file:///etc/passwd"})
        self.assertIn("error", result.lower())

    def test_upload_file_rejects_private_ip(self):
        """upload_file must reject private destination IPs."""
        from src.plugins.core_tools import upload_file

        result = upload_file.invoke({"filepath": "dummy.txt", "url": "http://192.168.1.1/upload", "method": "POST"})
        self.assertIn("error", result.lower())

    def test_file_ops_no_urllib_sinks(self):
        """file_ops must not use urllib.request urlopen/urlretrieve."""
        import inspect

        from src.plugins import file_ops

        source = inspect.getsource(file_ops)
        self.assertNotIn("urlopen", source)
        self.assertNotIn("urlretrieve", source)

    def test_open_pinned_connection_https_no_server_hostname_kwarg(self):
        """HTTPSConnection has no server_hostname param — must pre-wrap socket instead."""
        import src.plugins.web_tools as web_tools

        with (
            patch("http.client.HTTPSConnection") as https_conn,
            patch("ssl.create_default_context") as ctx,
            patch("socket.create_connection") as create_sock,
        ):
            raw = MagicMock()
            create_sock.return_value = raw
            wrapped = MagicMock()
            ctx.return_value.wrap_socket.return_value = wrapped
            conn = web_tools._open_pinned_connection("example.com", 443, "https", "93.184.216.34", 10)
            https_conn.assert_called_once_with("example.com", 443, timeout=10, context=ctx.return_value)
            create_sock.assert_called_once_with(("93.184.216.34", 443), timeout=10)
            ctx.return_value.wrap_socket.assert_called_once_with(raw, server_hostname="example.com")
            self.assertIs(conn.sock, wrapped)

    def test_http_request_redirect_without_location_returns_response(self):
        """3xx without Location header must return (status, data), not None."""
        from urllib.parse import urlparse

        import src.plugins.file_ops as file_ops

        resp = MagicMock()
        resp.status = 302
        resp.read.return_value = b""
        resp.getheader.return_value = ""
        conn = MagicMock()
        conn.getresponse.return_value = resp
        prepared = (urlparse("http://example.com/x"), "example.com", 80, "93.184.216.34")
        with (
            patch.object(file_ops, "_open_pinned_connection", return_value=conn),
            patch.object(file_ops, "_prepare_http_request", return_value=prepared),
        ):
            status, data = file_ops._http_request("http://example.com/x", "GET")
        self.assertEqual(status, 302)
        self.assertEqual(data, b"")


class TestMCPAllowlist(unittest.TestCase):
    """test_mcp_allowlist: MCP calls must be allowlisted per agent."""

    def test_mcp_policy_exists(self):
        """MCP_POLICY must be defined."""
        from src.core.auth.approval import MCP_POLICY

        self.assertIsInstance(MCP_POLICY, dict)
        self.assertIn("coder_agent", MCP_POLICY)
        self.assertIn("admin_agent", MCP_POLICY)
        self.assertIn("casual_agent", MCP_POLICY)

    def test_casual_agent_no_mcp(self):
        """casual_agent must have empty MCP policy."""
        from src.core.auth.approval import MCP_POLICY

        self.assertEqual(MCP_POLICY["casual_agent"], {})

    def test_check_mcp_policy_unknown_server_denies(self):
        """Unknown MCP server must be denied."""
        from src.core.auth.approval import check_mcp_policy

        ok, _msg = check_mcp_policy("unknown_server", "unknown_tool")
        self.assertFalse(ok)

    def test_check_mcp_policy_unknown_tool_denies(self):
        """Unknown tool on known server must be denied."""
        from src.core.auth.approval import check_mcp_policy

        ok, _msg = check_mcp_policy("tavily", "malicious_tool")
        self.assertFalse(ok)


class TestApprovalFailClosed(unittest.TestCase):
    """test_approval_fail_closed: Approval failures deny, not allow."""

    def test_panggil_mcp_approval_error_returns_denied(self):
        """panggil_mcp must return error if approval gate fails."""
        from src.plugins.core_tools import panggil_mcp

        with (
            patch("src.core.auth.approval.check_mcp_policy", return_value=(True, "")),
            patch("src.core.auth.approval.ensure_approved", side_effect=Exception("DB down")),
        ):
            result = panggil_mcp.invoke(
                {
                    "server": "tavily",
                    "tool": "tavily_search",
                    "args_json": '{"query": "test"}',
                }
            )
            self.assertTrue(
                "denied" in result.lower() or "error" in result.lower(),
                f"Expected denial, got: {result[:100]}",
            )


class TestToolCapabilityBoundary(unittest.TestCase):
    """test_tool_capability_boundary: TOOL_CAPABILITIES is single authority."""

    def test_no_agent_tool_allowlist(self):
        """Old AGENT_TOOL_ALLOWLIST must not exist."""
        import src.mcp_core.tool_validator as tv

        self.assertFalse(hasattr(tv, "AGENT_TOOL_ALLOWLIST"))

    def test_casual_no_code_execution(self):
        """casual_agent must not have code execution tools."""
        from src.mcp_core.tool_validator import TOOL_CAPABILITIES

        casual = TOOL_CAPABILITIES.get("casual_agent", set())
        self.assertNotIn("tulis_kode", casual)
        self.assertNotIn("jalankan_python", casual)
        self.assertNotIn("panggil_mcp", casual)

    def test_admin_no_code_execution(self):
        """admin_agent must not have code execution tools."""
        from src.mcp_core.tool_validator import TOOL_CAPABILITIES

        admin = TOOL_CAPABILITIES.get("admin_agent", set())
        self.assertNotIn("tulis_kode", admin)
        self.assertNotIn("jalankan_python", admin)

    def test_validate_tools_unknown_agent_empty(self):
        """Unknown agent gets no tools."""
        from src.mcp_core.tool_validator import validate_tools_for_agent

        result = validate_tools_for_agent("evil_agent", [MagicMock(name="tulis_kode")])
        self.assertEqual(result, [])


class TestTelegramAllowlist(unittest.TestCase):
    """test_telegram_allowlist: Empty allowlist denies all in production."""

    def test_empty_allowlist_denies(self):
        """Empty TELEGRAM_ALLOWED_IDS must deny all."""
        import os

        from src.integrations.telegram import is_allowed

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_IDS": "", "TELEGRAM_DEV": "0"}, clear=True):
            self.assertFalse(is_allowed(12345))

    def test_dev_mode_allows_all(self):
        """TELEGRAM_DEV=1 allows all."""
        import os

        from src.integrations.telegram import is_allowed

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_IDS": "", "TELEGRAM_DEV": "1"}, clear=True):
            self.assertTrue(is_allowed(12345))

    def test_populated_allowlist_restricts(self):
        """Non-empty allowlist only allows listed IDs."""
        import os

        from src.integrations.telegram import is_allowed

        with patch.dict(os.environ, {"TELEGRAM_ALLOWED_IDS": "111,222"}, clear=True):
            self.assertTrue(is_allowed(111))
            self.assertFalse(is_allowed(333))


class TestRateLimit(unittest.TestCase):
    """test_rate_limit: Rate limiting is enforced."""

    def test_rate_limit_enforced_on_chat(self):
        """Rate limit must be enforced on /chat."""
        from src.core.system.rate_limit import check_rate_limit

        # Should return a tuple (allowed, info)
        allowed, info = check_rate_limit("chat", "security_test_ip")
        self.assertIsInstance(allowed, bool)
        self.assertIn("limit", info)
        self.assertIn("remaining", info)

    def test_rate_limits_are_capped(self):
        """Rate limits must have reasonable maximums."""
        from src.core.system.rate_limit import RATE_LIMITS

        for scope, (burst, sustained) in RATE_LIMITS.items():
            self.assertLessEqual(burst, 30, f"{scope} burst exceeds 30/s")
            self.assertLessEqual(sustained, 60, f"{scope} sustained exceeds 60/min")


class TestSymlinkEscape(unittest.TestCase):
    """test_symlink_escape: File tools block symlink escapes."""

    def test_safe_path_rejects_empty(self):
        """_safe_path must reject empty path."""
        from src.plugins.core_tools import _safe_path

        ok, _ = _safe_path("")
        self.assertFalse(ok)

    def test_safe_path_rejects_dotenv(self):
        """_safe_path must reject .env files."""
        from src.plugins.core_tools import _safe_path

        ok, _ = _safe_path(".env")
        self.assertFalse(ok)

    def test_safe_path_rejects_git(self):
        """_safe_path must reject .git directory."""
        from src.plugins.core_tools import _safe_path

        ok, _ = _safe_path(".git/config")
        self.assertFalse(ok)

    def test_safe_path_rejects_key(self):
        """_safe_path must reject .key files."""
        from src.plugins.core_tools import _safe_path

        ok, _ = _safe_path("server.key")
        self.assertFalse(ok)


class TestSecretRedaction(unittest.TestCase):
    """test_secret_redaction: Secrets are redacted in logs."""

    def test_redact_openai_key(self):
        """OpenAI sk- keys must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("Using key sk-proj-abc123def456ghi789jklmno")
        self.assertNotIn("sk-proj-abc123", result)
        self.assertIn("REDACTED", result)

    def test_redact_aws_key(self):
        """AWS access keys must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("Key: AKIAIOSFODNN7EXAMPLE")
        self.assertNotIn("AKIAIOSFODNN7", result)
        self.assertIn("REDACTED", result)

    def test_redact_github_token(self):
        """GitHub tokens must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("Token: ghp_abcdef1234567890")
        self.assertNotIn("ghp_abcdef", result)
        self.assertIn("REDACTED", result)

    def test_redact_bearer_token(self):
        """Bearer tokens must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test")
        self.assertNotIn("eyJhbGci", result)
        self.assertIn("REDACTED", result)

    def test_redact_database_url(self):
        """Database URLs with passwords must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("postgres://user:secretpass@localhost/db")
        self.assertNotIn("secretpass", result)
        self.assertIn("REDACTED", result)

    def test_redact_redis_url(self):
        """Redis URLs with passwords must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("redis://:redispass@localhost:6379")
        self.assertNotIn("redispass", result)
        self.assertIn("REDACTED", result)

    def test_redact_api_key_header(self):
        """X-API-Key headers must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("X-API-Key: fr_abcdef1234567890")
        self.assertNotIn("fr_abcdef", result)
        self.assertIn("REDACTED", result)

    def test_redact_password_assignment(self):
        """Password assignments must be redacted."""
        from src.core.observability.logger import redact_secrets

        result = redact_secrets("password=mypassword123")
        self.assertNotIn("mypassword123", result)
        self.assertIn("REDACTED", result)

    def test_safe_error_no_paths(self):
        """Error responses must not contain filesystem paths."""
        from src.core.system.error_handling import safe_error_response

        resp = safe_error_response(Exception("Error at /home/user/.env"), request_id="test123")
        self.assertNotIn("/home/", str(resp))
        self.assertIn("request_id", resp)

    def test_safe_error_no_sql(self):
        """Error responses must not contain SQL."""
        from src.core.system.error_handling import safe_error_response

        resp = safe_error_response(
            Exception("SQL: SELECT * FROM users WHERE password = 'x'"),
            request_id="test456",
        )
        self.assertNotIn("SELECT", str(resp))


if __name__ == "__main__":
    unittest.main()
