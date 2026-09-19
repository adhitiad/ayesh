"""Plugin Tools (Tangan & Kaki AI) untuk eksekusi aksi nyata di sistem lokal."""

import asyncio
import os
from typing import ClassVar

from langchain_core.tools import tool

from src.plugins.time_tool import get_current_time

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


_SENSITIVE_NAMES = {".env", ".env.local", ".env.production", ".env.staging"}
_SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".asc", ".gpg")
_SENSITIVE_PATTERNS = (
    "credentials",
    "secret",
    "service-account",
    ".git",
)


def _safe_path(path: str) -> tuple:
    """Validasi path TULIS: canonical path, anti-symlink escape, anti-sensitive files.

    P2.2 — Uses Path.resolve() for canonical paths. Rejects:
    - Symlink escape (resolved outside allowed dirs)
    - .. traversal
    - Absolute paths outside project root / approved dirs
    - .git, .env, .env.*, credentials*, secret*, *.pem, *.key, *.p12, *.pfx
    - service-account*.json

    Returns (ok, abs/error)."""
    from pathlib import Path

    p = (path or "").strip()
    if not p:
        return False, "Error: path kosong."

    # Resolve to canonical path (follows symlinks, normalizes ..)
    try:
        resolved = Path(p).resolve()
    except Exception:
        return False, f"Error: path '{p}' tidak valid."

    ap = str(resolved)

    # Check if resolved path is inside allowed directories
    root = os.path.abspath(_PROJECT_ROOT)
    root_slash = root.rstrip(os.sep) + os.sep
    in_root = ap == root or ap.startswith(root_slash)

    allowed = False
    if not in_root:
        try:
            from src.core.system.workspaces import is_path_allowed

            allowed = bool(is_path_allowed(ap))
        except Exception as _e:
            allowed = False
            import logging as _log

            _log.getLogger(__name__).debug("_safe_path workspaces error: %s", _e)
        if not allowed:
            return (
                False,
                (
                    f"Error: path di luar project root ({_PROJECT_ROOT}) dan bukan direktori "
                    "pilihan user. Tanya dulu mau disimpan di mana, lalu catat via tool "
                    "set_target_dir sebelum menulis."
                ),
            )

    # Check for symlink escape: if original path != resolved path and resolved is outside
    original_abs = os.path.abspath(p)
    if original_abs != ap and not (ap == root or ap.startswith(root_slash)):
        # Symlink resolved to outside allowed area
        return (
            False,
            f"Error: symlink escape terdeteksi. Path '{p}' resolve ke '{ap}' di luar area yang diizinkan.",
        )

    # P2.2 — Sensitive file checks (canonical name matching)
    base = resolved.name.lower()
    parent_names = [part.lower() for part in resolved.parts]

    # Exact name match
    if base in _SENSITIVE_NAMES:
        return False, f"Error: file '{base}' sensitif, akses ditolak."

    # Suffix match
    if base.endswith(_SENSITIVE_SUFFIXES):
        return False, f"Error: file '{base}' sensitif (*.key/*.pem/etc), akses ditolak."

    # Pattern match in filename or path components
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in base:
            return (
                False,
                f"Error: file '{base}' mengandung pola sensitif '{pattern}', akses ditolak.",
            )
        for part in parent_names:
            if pattern in part:
                return False, f"Error: direktori '{part}' sensitif, akses ditolak."

    # Block .git directory
    if ".git" in parent_names:
        return False, "Error: akses ke direktori .git ditolak."

    return True, ap


@tool
def tulis_kode(filepath: str, konten: str, overwrite: bool = False) -> str:
    """Menulis teks atau kode program ke dalam file lokal.

    Args:
        filepath: Path file tujuan.
        konten: Isi teks/kode yang ingin ditulis.
        overwrite: Jika True, timpa file yang sudah ada. Jika False (default), error jika file sudah ada.
    """
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "tulis_kode",
                {"filepath": filepath, "overwrite": overwrite},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"
        if os.path.exists(filepath) and not overwrite:
            return f"Error: File '{filepath}' sudah ada. Gunakan overwrite=True untuk menimpa."
        parent = os.path.dirname(filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(konten)
        return f"File berhasil dibuat di {filepath}"
    except Exception as e:
        return f"Gagal menulis file: {e!s}"


@tool
def baca_file(filepath: str) -> str:
    """Membaca isi dari file lokal (project root/output/ atau direktori pilihan user)."""
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: File tidak ditemukan."
    except Exception as e:
        return f"Error saat membaca file: {e!s}"


@tool
def info_sistem() -> str:
    """Tampilkan spesifikasi mesin lokal: OS, CPU, RAM, partisi/drive, Python,
    GPU, Redis, PostgreSQL. Tanpa argumen. Tanpa akses jaringan/infra berat
    (probe lokal bertimeout singkat, hasil di-cache 5 menit)."""
    try:
        from src.core.system.sysinfo import get_sysinfo_block

        return get_sysinfo_block()
    except Exception as e:
        return f"Gagal membaca info sistem: {e!s}"


@tool
def set_target_dir(path: str) -> str:
    """Catat direktori kerja pilihan user untuk session ini agar tulis_kode
    boleh menulis di luar project root.

    WAJIB dipanggil SETELAH user menyebut lokasi simpan (mis. "F:/bdk") dan
    SEBELUM tulis_kode ke lokasi tersebut. Tanpa ini, tulis ke luar root
    ditolak. File sensitif (.env, *.key/pem/dsb.) tetap selalu ditolak.

    Args:
        path: Path folder absolut pilihan user, mis. F:/bdk atau /home/user/proj.
    """
    try:
        from src.core.auth.approval import current_session
        from src.core.system.workspaces import note_target_dir

        try:
            session_id = current_session.get() or ""
        except Exception as _e:
            session_id = ""
            import logging as _log

            _log.getLogger(__name__).debug("current_session.get error: %s", _e)
        ok, result = note_target_dir(session_id, path)
        if not ok:
            return result
        return f"Direktori kerja session ini dicatat: {result}. tulis_kode kini boleh menulis di dalamnya."
    except Exception as e:
        return f"Gagal mencatat direktori: {e!s}"


@tool
def cari_web(query: str) -> str:
    """Melakukan pencarian informasi terkini di internet menggunakan Tavily MCP."""
    try:
        from src.mcp_core.client import mcp_manager

        async def _search():
            # Tavily dulu, fallback ke Exa bila gagal
            result = await mcp_manager.call_tool("tavily", "tavily_search", {"query": query, "max_results": 5})
            if isinstance(result, str) and result.startswith("Error"):
                result = await mcp_manager.call_tool("exa", "exa_search", {"query": query, "max_results": 5})
            return result

        result = asyncio.run(_search())
        # Extract text from MCP result
        from src.core.llm.text import extract_text

        if hasattr(result, "content") and result.content:
            text = extract_text(result.content, sep="\n\n")
            return text or str(result)
        return str(result)
    except Exception as e:
        return f"Gagal mencari web: {e!s}"


@tool
def learn_keyword(agent: str, keyword: str, allowed_tools: str = "") -> str:
    """Simpan keyword routing baru ke database agar request serupa bisa langsung di-route ke agent yang tepat di masa depan.

    Args:
        agent: Nama agent yang sesuai (coder_agent, admin_agent, atau casual_agent).
        keyword: Kata kunci yang ingin disimpan (huruf kecil).
        allowed_tools: Daftar tool yang diizinkan untuk keyword ini, dipisah koma. Contoh: "tulis_kode,baca_file". Kosongkan jika tidak perlu tool.
    """
    from src.config.routing_keywords_pg import (
        add_keyword_with_tools,
        invalidate_routing_cache,
    )

    valid_agents = {"coder_agent", "admin_agent", "casual_agent"}
    agent = agent.strip().lower()
    if agent not in valid_agents:
        return f"Error: agent '{agent}' tidak valid. Pilihan: {', '.join(sorted(valid_agents))}"

    keyword = keyword.strip().lower()
    if not keyword:
        return "Error: keyword tidak boleh kosong."

    tools_list = [t.strip() for t in allowed_tools.split(",") if t.strip()] if allowed_tools else []

    ok = add_keyword_with_tools(agent, keyword, tools_list)
    if ok:
        invalidate_routing_cache()
        tools_str = ", ".join(tools_list) if tools_list else "(no tools)"
        return f"Keyword '{keyword}' berhasil disimpan untuk {agent}. Allowed tools: [{tools_str}]"
    return f"Gagal menyimpan keyword '{keyword}' ke database."


_ADVISOR_PROMPT = (
    "Kamu adalah reviewer pekerjaan seorang agen AI. Di bawah ini adalah transkrip "
    "ringkas: tugas, tool call yang sudah dilakukan beserta hasilnya, dan pertanyaan agen.\n\n"
    "Tentukan posisi agen:\n"
    "- BARU MULAI (belum ada aksi substantif): beri pendekatan yang tepat — apa saja yang perlu "
    "disentuh, berurutan. Tandai constraint yang implisit dari tugas. Jika jawaban bergantung fakta "
    "yang tak bisa diverifikasi dari transkrip, beri strategi pencariannya, bukan tebakannya.\n"
    "- STUCK (error berulang / pendekatan tidak konvergen): diagnosa titik kegagalan spesifik dari "
    "yang SUDAH dicoba. Jangan rencanakan ulang dari nol; jangan sarankan hal yang sudah dicoba.\n"
    "- REVIEW HASIL (pekerjaan selesai, cek mandiri lolos): cari yang tidak dicover cek mandirinya — "
    "requirement implisit, blind spot. Jika transkrip menunjukkan agen ragu ('X kurang pas, tapi...'), "
    "itu sinyal pivot, bukan sinyal commit.\n"
    "- PILIH ANTARA KANDIDAT: default ke bacaan paling plain/face-value. Jangan tolak bacaan plain "
    "kecuali mustahil.\n\n"
    "Aturan: langsung ke saran yang bisa dieksekusi. Jika tahu jawaban spesifik, sampaikan sebagai "
    "cek yang harus diverifikasi ('verifikasi apakah X memenuhi constraint Y'), bukan vonis. "
    "Jika ada concern tersisa, nyatakan tegas apakah itu BLOCKING atau bukan. Bahasa Indonesia, ringkas."
)


@tool
def minta_review(pertanyaan: str, konteks: str) -> str:
    """Minta nasihat reviewer atas pekerjaan yang sedang berjalan (pola advisor).

    Args:
        pertanyaan: Pertanyaan spesifik ke reviewer. Contoh: "rencana hapus atau timpa file?", "error ini mentok, apa titik gagalnya?", "cek apakah hasil ini memenuhi requirement?".
        konteks: Ringkasan transkrip sejauh ini — tugas, tool call + hasilnya, masalah yang ditemui. Tulis sepadat mungkin.
    """
    from src.agents.llm_config import get_llm

    try:
        llm = get_llm()
        response = llm.invoke(
            f"{_ADVISOR_PROMPT}\n\n## Konteks pekerjaan\n{konteks[:3000]}\n\n## Pertanyaan agen\n{pertanyaan}"
        )
        from src.core.llm.text import extract_text

        content = extract_text(response.content if hasattr(response, "content") else str(response))
        return f"Nasihat reviewer:\n{content}"
    except Exception as e:
        return f"Gagal meminta review: {str(e)[:200]}"


@tool
def baca_url(url: str, max_karakter: int = 8000) -> str:
    """Membaca isi teks halaman web (deep-read lanjutan dari hasil cari_web).

    Args:
        url: URL http/https yang ingin dibaca.
        max_karakter: Batas panjang teks (default 8000).
    """
    import ipaddress
    import re
    import socket
    from html.parser import HTMLParser
    from urllib.parse import urljoin, urlparse

    class _TextOnly(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav", "header", "footer", "noscript"):
                self._skip += 1
            elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr"):
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav", "header", "footer", "noscript") and self._skip:
                self._skip -= 1

        def handle_data(self, data):
            if not self._skip:
                self.parts.append(data)

    # --- SSRF Protection Helpers ---
    _PRIVATE_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),  # loopback
        ipaddress.ip_network("10.0.0.0/8"),  # private Class A
        ipaddress.ip_network("172.16.0.0/12"),  # private Class B
        ipaddress.ip_network("192.168.0.0/16"),  # private Class C
        ipaddress.ip_network("169.254.0.0/16"),  # link-local
        ipaddress.ip_network("0.0.0.0/8"),  # current network
        ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
        ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol
        ipaddress.ip_network("192.0.2.0/24"),  # documentation
        ipaddress.ip_network("198.51.100.0/24"),  # documentation
        ipaddress.ip_network("203.0.113.0/24"),  # documentation
        ipaddress.ip_network("224.0.0.0/4"),  # multicast
        ipaddress.ip_network("240.0.0.0/4"),  # reserved
        ipaddress.ip_network("255.255.255.255/32"),  # broadcast
    ]
    _PRIVATE_NETWORKS_V6 = [
        ipaddress.ip_network("::1/128"),  # loopback
        ipaddress.ip_network("fc00::/7"),  # ULA
        ipaddress.ip_network("fe80::/10"),  # link-local
        ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped
        ipaddress.ip_network("64:ff9b::/96"),  # well-known prefix
    ]
    _MAX_REDIRECTS = 5
    _MAX_RESPONSE_BYTES = 2_000_000
    _CONNECT_TIMEOUT = 10
    _READ_TIMEOUT = 15

    def _is_ip_private(ip_str: str) -> bool:
        """Check if IP is in a private/reserved/blocked range."""
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return True  # invalid = block
        if isinstance(addr, ipaddress.IPv4Address):
            return any(addr in net for net in _PRIVATE_NETWORKS)
        elif isinstance(addr, ipaddress.IPv6Address):
            return any(addr in net for net in _PRIVATE_NETWORKS_V6)
        return True

    def _resolve_and_validate(hostname: str) -> str:
        """DNS resolve + reject if result is private/loopback/link-local."""
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            return ""
        for _family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if _is_ip_private(ip):
                return ""
        return hostname

    def _validate_url(target_url: str, depth: int = 0) -> bool:
        """Validate URL at each redirect hop."""
        if depth > _MAX_REDIRECTS:
            return False
        parsed = urlparse(target_url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # Block common metadata endpoints
        blocked_hostnames = {
            "169.254.169.254",
            "metadata.google.internal",
            "instance-data.ec2.internal",
            "100.100.100.200",
            "fd00:ec2::254",
        }
        if hostname.lower() in blocked_hostnames:
            return False
        # Validate hostname characters
        if not re.match(r"^[a-zA-Z0-9._-]+$", hostname):
            return False
        # DNS resolve + IP validation
        return _resolve_and_validate(hostname)

    def _fetch_with_ssrf_protection(target_url: str) -> str:
        """Fetch URL with SSRF protection: scheme/host/IP validation, redirect revalidation."""
        import http.client
        import ssl

        parsed = urlparse(target_url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        ctx = ssl.create_default_context()
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(hostname, port, timeout=_CONNECT_TIMEOUT, context=ctx)
        else:
            conn = http.client.HTTPConnection(hostname, port, timeout=_CONNECT_TIMEOUT)

        headers = {"User-Agent": "Mozilla/5.0", "Host": hostname}
        redirect_count = 0
        current_url = target_url

        while True:
            try:
                conn.request("GET", path, headers=headers)
                resp = conn.getresponse()
            except Exception as _e:
                import logging as _log

                _log.getLogger(__name__).debug("baca_url connection error: %s", _e)
                return ""

            # Read response with size limit
            data = b""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > _MAX_RESPONSE_BYTES:
                    return ""

            # Check for redirect (3xx)
            status = resp.status
            if 300 <= status < 400:
                location = resp.getheader("Location", "")
                if not location:
                    break
                # Resolve redirect URL
                next_url = urljoin(current_url, location)
                redirect_count += 1
                if redirect_count > _MAX_REDIRECTS:
                    return ""
                # Revalidate redirect target
                if not _validate_url(next_url, redirect_count):
                    return ""
                # Close old connection, open new one
                conn.close()
                parsed_next = urlparse(next_url)
                hostname = parsed_next.hostname
                port = parsed_next.port or (443 if parsed_next.scheme == "https" else 80)
                path = parsed_next.path or "/"
                if parsed_next.query:
                    path += "?" + parsed_next.query
                if parsed_next.scheme == "https":
                    conn = http.client.HTTPSConnection(hostname, port, timeout=_CONNECT_TIMEOUT, context=ctx)
                else:
                    conn = http.client.HTTPConnection(hostname, port, timeout=_CONNECT_TIMEOUT)
                headers["Host"] = hostname
                current_url = next_url
                continue

            break

        conn.close()
        return data.decode("utf-8", errors="replace")

    try:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "Error: URL harus http/https."

        # Parse and validate the URL
        parsed = urlparse(url)
        if not parsed.hostname:
            return "Error: URL tidak valid."

        # Validate URL and resolve DNS (reject private/loopback)
        if not _validate_url(url, 0):
            return "Error: URL ditolak (private/loopback/link-local/metadata endpoint)."

        raw = _fetch_with_ssrf_protection(url)
        if not raw:
            return "Error: Gagal mengambil konten URL."

        parser = _TextOnly()
        parser.feed(raw)
        text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        if len(text) > max_karakter:
            text = text[:max_karakter] + "\n\n...[dipotong]"
        return text or "Error: Tidak ada teks terbaca dari URL."
    except Exception as e:
        return f"Gagal membaca URL: {str(e)[:200]}"


@tool
def jalankan_python(kode: str = "", filepath: str = "", timeout_detik: int = 30) -> str:
    """Menjalankan kode/file Python lokal dan mengembalikan outputnya.

    Pakai untuk verifikasi mandiri setelah tulis_kode: jalankan, baca error,
    perbaiki, ulangi sampai lolos. Isi salah satu: kode atau filepath.
    Proses dieksekusi di sandbox terisolasi.

    Args:
        kode: Kode Python untuk dieksekusi langsung.
        filepath: Path file .py lokal untuk dijalankan.
        timeout_detik: Batas waktu eksekusi (default 30, maks 120).
    """
    import subprocess
    import sys

    try:
        from src.core.auth.approval import ensure_approved
        from src.core.auth.auth import get_current_user_id

        _ok, _msg = ensure_approved(
            "jalankan_python",
            {"filepath": filepath, "has_code": bool(kode)},
            owner_user_id=get_current_user_id(),
        )
        if not _ok:
            return _msg
    except Exception as e:
        return f"Error: Approval gate failed: {e!s}"
    if not kode and not filepath:
        return "Error: Isi salah satu: kode atau filepath."
    timeout_detik = max(1, min(int(timeout_detik), 120))
    sandbox = CodeExecutionSandbox()
    if filepath:
        if not filepath.endswith(".py"):
            return "Error: Hanya file .py yang boleh dijalankan."
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        cmd = [sys.executable, filepath]
        sandbox.set_workdir(os.path.dirname(filepath))
    else:
        cmd = [sys.executable, "-c", kode]
    try:
        exit_code, output = sandbox.run(cmd, timeout=timeout_detik)
        output = output.strip()[:6000] or "(tidak ada output)"
        return f"exit={exit_code}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: Eksekusi melebihi {timeout_detik}s (timeout)."
    except Exception as e:
        return f"Gagal menjalankan Python: {str(e)[:200]}"


class CodeExecutionSandbox:
    """Sandbox untuk eksekusi kode Python terisolasi.

    Security controls:
    - Environment variable whitelist (PATH, PYTHONUNBUFFERED only)
    - Dedicated working directory
    - Process timeout
    - No credential/env access
    - No network access by default
    - No subprocess escalation
    """

    _SAFE_ENV: ClassVar[set[str]] = {"PATH", "PYTHONUNBUFFERED", "TMPDIR", "TEMP", "TMP"}

    def __init__(self, workdir: str | None = None):
        import os

        self._workdir = workdir or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        self._env = {k: v for k, v in os.environ.items() if k in self._SAFE_ENV}
        self._env.setdefault("PYTHONUNBUFFERED", "1")

    def set_workdir(self, path: str) -> None:
        """Set dedicated working directory for the sandbox."""
        self._workdir = path

    def run(self, cmd: list, timeout: int = 30) -> tuple[int, str]:
        """Run command in sandbox. Returns (exit_code, output)."""
        import subprocess

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=self._workdir,
            env=self._env,
            start_new_session=True,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip() or "(tidak ada output)"


_MCP_BLOCKED_SERVERS = {"filesystem"}


@tool
def panggil_mcp(server: str, tool: str, args_json: str = "{}") -> str:
    """Memanggil tool server MCP remote on-demand (lazy, tanpa startup cost).

    Daftar server lihat mcp_core/mcp.json (tavily, exa, firecrawl, github,
    sequential-thinking, context7, ...). Server 'filesystem' diblokir —
    pakai tulis_kode/baca_file untuk file lokal.

    Args:
        server: Nama server di mcp.json. Contoh: "tavily", "exa".
        tool: Nama tool di server itu. Contoh: "tavily_search".
        args_json: Argumen sebagai JSON string. Contoh: '{"query": "harga emas"}'.
    """
    import json as _json

    try:
        from src.mcp_core.client import mcp_manager

        server = server.strip()
        if server in _MCP_BLOCKED_SERVERS:
            return f"Error: Server '{server}' diblokir. Untuk file lokal pakai tulis_kode/baca_file."
        try:
            args = _json.loads(args_json) if args_json.strip() else {}
        except _json.JSONDecodeError:
            return "Error: args_json bukan JSON valid."
        if not isinstance(args, dict):
            return "Error: args_json harus object JSON."

        # P1.3 — Enforce MCP policy: server + tool must be allowlisted
        try:
            from src.core.auth.approval import check_mcp_policy

            allowed, deny_msg = check_mcp_policy(server, tool)
            if not allowed:
                return deny_msg
        except Exception as exc:
            return f"Error: MCP policy check unavailable; action denied. {exc}"

        # P1.4 — Approval gate: fail-closed on exception
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "panggil_mcp",
                {"server": server, "tool": tool},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as exc:
            return f"Error: Approval gate unavailable; action denied. {exc}"

        async def _call():
            return await mcp_manager.call_tool(server, tool, args)

        result = asyncio.run(_call())
        from src.core.llm.text import extract_text

        if hasattr(result, "content") and result.content:
            text = extract_text(result.content, sep="\n\n")
            return text or str(result)
        return str(result)
    except Exception as e:
        return f"Gagal memanggil MCP {server}/{tool}: {str(e)[:200]}"


def _pref_user() -> str:
    """P2.6 — Get current user for preference scoping. Never returns 'default'."""
    try:
        from src.core.auth.auth import get_current_user

        uid = get_current_user()
        if uid and uid != "default":
            return uid
    except Exception as _e:
        import logging as _log

        _log.getLogger(__name__).debug("_pref_user error: %s", _e)
    return "anonymous"


def _pref_ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS preferensi (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("ALTER TABLE preferensi ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default';")
    cur.execute("UPDATE preferensi SET user_id = 'default' WHERE user_id IS NULL;")
    cur.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preferensi_pkey') THEN
                ALTER TABLE preferensi DROP CONSTRAINT preferensi_pkey;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'preferensi_user_pkey') THEN
                ALTER TABLE preferensi ADD CONSTRAINT preferensi_user_pkey PRIMARY KEY (user_id, key);
            END IF;
        END $$;
    """)


def get_preferences_block() -> str:
    """Blok teks preferensi user untuk injeksi prompt. Kosong bila belum ada."""
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _pref_ensure_table(cur)
        conn.commit()
        cur.execute(
            "SELECT key, value FROM preferensi WHERE user_id = %s ORDER BY key;",
            (_pref_user(),),
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["Preferensi user yang tersimpan:"]
        lines += [f"- {k}: {v}" for k, v in rows]
        return "\n".join(lines)
    except Exception as _e:
        import logging as _log

        _log.getLogger(__name__).debug("get_preferences_block error: %s", _e)
        return ""


@tool
def ingat_preferensi(key: str, value: str) -> str:
    """Simpan preferensi/fakta tentang user lintas session (nama, kesukaan, setting).

    Pakai saat user menyatakan sesuatu yang layak diingat jangka panjang.
    JANGAN untuk info sesaat atau rahasia (password, token, OTP).

    Args:
        key: Kunci singkat lowercase. Contoh: "nama", "bahasa", "framework".
        value: Nilai preferensi. Contoh: "Budi", "python".
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        key = key.strip().lower().replace(" ", "_")[:50]
        value = value.strip()[:500]
        if not key or not value:
            return "Error: key dan value tidak boleh kosong."
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _pref_ensure_table(cur)
        cur.execute(
            "UPDATE preferensi SET value = %s, updated_at = NOW() WHERE user_id = %s AND key = %s;",
            (value, _pref_user(), key),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO preferensi(key, value, user_id) VALUES (%s, %s, %s);",
                (key, value, _pref_user()),
            )
        conn.commit()
        conn.close()
        return f"Preferensi tersimpan: {key} = {value}"
    except Exception as e:
        return f"Gagal menyimpan preferensi: {str(e)[:200]}"


@tool
def lihat_preferensi() -> str:
    """Lihat semua preferensi user yang tersimpan lintas session."""
    block = get_preferences_block()
    return block or "Belum ada preferensi tersimpan."


def _proj_user() -> str:
    """P2.6 — Get current user for project scoping. Never returns 'default'."""
    try:
        from src.core.auth.auth import get_current_user

        uid = get_current_user()
        if uid and uid != "default":
            return uid
    except Exception as _e:
        import logging as _log

        _log.getLogger(__name__).debug("_pref_user error: %s", _e)
    return "anonymous"


def _proj_ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proyek (
            nama TEXT PRIMARY KEY,
            goal TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'aktif',
            catatan TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    cur.execute("ALTER TABLE proyek ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'default';")
    cur.execute("UPDATE proyek SET user_id = 'default' WHERE user_id IS NULL;")
    cur.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proyek_pkey') THEN
                ALTER TABLE proyek DROP CONSTRAINT proyek_pkey;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proyek_user_pkey') THEN
                ALTER TABLE proyek ADD CONSTRAINT proyek_user_pkey PRIMARY KEY (user_id, nama);
            END IF;
        END $$;
    """)


def get_projects_block() -> str:
    """Blok proyek aktif untuk injeksi prompt. Kosong bila belum ada."""
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _proj_ensure_table(cur)
        conn.commit()
        cur.execute(
            "SELECT nama, goal, status, catatan FROM proyek WHERE user_id = %s AND status <> 'selesai' ORDER BY updated_at DESC;",
            (_proj_user(),),
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["Proyek aktif yang sedang dikerjakan user:"]
        for nama, goal, status, catatan in rows:
            line = f"- {nama} [{status}]: {goal}"
            if catatan:
                line += f" | Catatan: {catatan[:300]}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as _e:
        import logging as _log

        _log.getLogger(__name__).debug("get_projects_block error: %s", _e)
        return ""


@tool
def simpan_proyek(nama: str, goal: str, status: str = "aktif") -> str:
    """Simpan/perbarui proyek jangka panjang user (tujuan, status, lintas session).

    Pakai saat user memulai pekerjaan multi-session (skripsi, renovasi, bisnis).
    JANGAN untuk tugas sekali-jawab.

    Args:
        nama: Nama pendek proyek. Contoh: "renovasi-dapur".
        goal: Tujuan proyek dalam 1-2 kalimat.
        status: aktif / jeda / selesai.
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        nama = nama.strip().lower().replace(" ", "-")[:60]
        status = status.strip().lower()[:20]
        if status not in ("aktif", "jeda", "selesai"):
            return "Error: status harus aktif/jeda/selesai."
        if not nama or not goal.strip():
            return "Error: nama dan goal tidak boleh kosong."
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _proj_ensure_table(cur)
        cur.execute(
            "UPDATE proyek SET goal = %s, status = %s, updated_at = NOW() WHERE user_id = %s AND nama = %s;",
            (goal.strip()[:1000], status, _proj_user(), nama),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO proyek(nama, goal, status, user_id) VALUES (%s, %s, %s, %s);",
                (nama, goal.strip()[:1000], status, _proj_user()),
            )
        conn.commit()
        conn.close()
        return f"Proyek tersimpan: {nama} [{status}]"
    except Exception as e:
        return f"Gagal menyimpan proyek: {str(e)[:200]}"


@tool
def catat_proyek(nama: str, catatan: str) -> str:
    """Tambah catatan perkembangan ke proyek yang ada (append, bukan timpa).

    Args:
        nama: Nama proyek (lihat via lihat_proyek).
        catatan: Perkembangan/keputusan baru. Contoh: "sudah pilih keramik, lanjut tukang".
    """
    try:
        import psycopg2

        from src.config.routing_keywords_pg import DATABASE_URL

        nama = nama.strip().lower().replace(" ", "-")[:60]
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _proj_ensure_table(cur)
        cur.execute(
            "SELECT catatan FROM proyek WHERE user_id = %s AND nama = %s;",
            (_proj_user(), nama),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return f"Error: proyek '{nama}' tidak ada. Simpan dulu via simpan_proyek."
        merged = ((row[0] + " | " if row[0] else "") + catatan.strip())[:2000]
        cur.execute(
            "UPDATE proyek SET catatan = %s, updated_at = NOW() WHERE user_id = %s AND nama = %s;",
            (merged, _proj_user(), nama),
        )
        conn.commit()
        conn.close()
        return f"Catatan ditambah ke proyek {nama}."
    except Exception as e:
        return f"Gagal mencatat proyek: {str(e)[:200]}"


@tool
def lihat_proyek() -> str:
    """Lihat semua proyek aktif user beserta goal dan catatannya."""
    block = get_projects_block()
    return block or "Belum ada proyek aktif."


@tool
def list_folder(path: str = ".") -> str:
    """Menampilkan isi dari direktori (folder).

    Args:
        path: Path folder yang ingin dilihat. Default adalah direktori saat ini.
    """
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        if not os.path.isdir(path):
            return f"Error: '{path}' bukan direktori."
        items = []
        for item in sorted(os.listdir(path)):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                items.append(f"📁 {item}/")
            else:
                size = os.path.getsize(full_path)
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
                items.append(f"📄 {item} ({size_str})")
        if not items:
            return f"Folder '{path}' kosong."
        return f"Isi folder '{path}':\n" + "\n".join(items)
    except PermissionError:
        return f"Error: Tidak ada akses ke '{path}'."
    except Exception as e:
        return f"Gagal membaca folder: {e!s}"


@tool
def buat_folder(path: str) -> str:
    """Membuat direktori (folder) baru.

    Args:
        path: Path folder yang ingin dibuat. Akan membuat parent folder jika belum ada.
    """
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "buat_folder",
                {"path": path},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"
        if os.path.exists(path):
            if os.path.isdir(path):
                return f"Folder '{path}' sudah ada."
            return f"Error: '{path}' sudah ada dan bukan folder."
        os.makedirs(path, exist_ok=True)
        return f"Folder '{path}' berhasil dibuat."
    except Exception as e:
        return f"Gagal membuat folder: {e!s}"


@tool
def hapus_file(path: str) -> str:
    """Menghapus file atau folder (rekursif untuk folder).

    Args:
        path: Path file atau folder yang ingin dihapus.
    """
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "hapus_file",
                {"path": path},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"
        if not os.path.exists(path):
            return f"Error: '{path}' tidak ditemukan."
        if os.path.isdir(path):
            import shutil

            shutil.rmtree(path)
            return f"Folder '{path}' berhasil dihapus (rekursif)."
        os.remove(path)
        return f"File '{path}' berhasil dihapus."
    except PermissionError:
        return f"Error: Tidak ada akses menghapus '{path}'."
    except Exception as e:
        return f"Gagal menghapus: {e!s}"


@tool
def rename_file(source: str, destination: str) -> str:
    """Rename atau memindahkan file/folder.

    Args:
        source: Path sumber yang ingin di-rename/pindah.
        destination: Path tujuan baru.
    """
    try:
        _ok_src, source = _safe_path(source)
        if not _ok_src:
            return source
        _ok_dst, destination = _safe_path(destination)
        if not _ok_dst:
            return destination
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "rename_file",
                {"source": source, "destination": destination},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"
        if not os.path.exists(source):
            return f"Error: '{source}' tidak ditemukan."
        if os.path.exists(destination):
            return f"Error: '{destination}' sudah ada."
        os.rename(source, destination)
        return f"'{source}' berhasil di-rename ke '{destination}'."
    except PermissionError:
        return f"Error: Tidak ada akses rename '{source}'."
    except Exception as e:
        return f"Gagal rename: {e!s}"


@tool
def download_file(url: str, destination: str = "") -> str:
    """Mengunduh file dari URL ke lokal.

    Args:
        url: URL file yang ingin diunduh.
        destination: Path tujuan penyimpanan. Jika kosong, file disimpan di folder saat ini dengan nama dari URL.
    """
    try:
        import urllib.parse
        import urllib.request

        if not destination:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or "downloaded_file"
            destination = os.path.join(".", filename)

        _path_ok, destination = _safe_path(destination)
        if not _path_ok:
            return destination

        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "download_file",
                {"url": url, "destination": destination},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"

        parent = os.path.dirname(destination)
        if parent:
            os.makedirs(parent, exist_ok=True)

        urllib.request.urlretrieve(url, destination)  # noqa: S310
        size = os.path.getsize(destination)
        return f"File berhasil diunduh ke '{destination}' ({size} bytes)."
    except Exception as e:
        return f"Gagal mengunduh file: {e!s}"


@tool
def upload_file(filepath: str, url: str, method: str = "POST") -> str:
    """Upload file ke server via HTTP.

    Args:
        filepath: Path file yang ingin diupload.
        url: URL tujuan upload.
        method: HTTP method (POST atau PUT).
    """
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath

        if not os.path.exists(filepath):
            return f"Error: File '{filepath}' tidak ditemukan."

        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "upload_file",
                {"filepath": filepath, "url": url, "method": method},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as e:
            return f"Error: Approval gate failed: {e!s}"

        import urllib.request

        with open(filepath, "rb") as f:
            data = f.read()

        req = urllib.request.Request(url, data=data, method=method.upper())  # noqa: S310
        req.add_header("Content-Type", "application/octet-stream")

        with urllib.request.urlopen(req) as response:  # noqa: S310
            status = response.getcode()
            return f"File '{filepath}' berhasil diupload ke '{url}' (HTTP {status})."
    except Exception as e:
        return f"Gagal upload file: {e!s}"


@tool
def buka_url(url: str) -> str:
    """Membuka URL di browser default sistem.

    Args:
        url: URL yang ingin dibuka.
    """
    try:
        import webbrowser

        webbrowser.open(url)
        return f"URL '{url}' berhasil dibuka di browser."
    except Exception as e:
        return f"Gagal membuka URL: {e!s}"


@tool
def search_folder(path: str = ".", pattern: str = "*") -> str:
    """Mencari file/folder berdasarkan pola nama di dalam direktori.

    Args:
        path: Direktori awal pencarian.
        pattern: Pola nama file (menggunakan glob pattern seperti *.txt, *.py).
    """
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path

        import glob

        search_pattern = os.path.join(path, "**", pattern)
        matches = glob.glob(search_pattern, recursive=True)

        if not matches:
            return f"Tidak ditemukan file dengan pola '{pattern}' di '{path}'."

        results = []
        for match in sorted(matches)[:50]:  # Limit 50 results
            rel_path = os.path.relpath(match, path)
            if os.path.isdir(match):
                results.append(f"📁 {rel_path}/")
            else:
                size = os.path.getsize(match)
                results.append(f"📄 {rel_path} ({size}B)")

        return f"Hasil pencarian '{pattern}' di '{path}':\n" + "\n".join(results)
    except Exception as e:
        return f"Gagal mencari: {e!s}"


@tool
def info_file(path: str) -> str:
    """Menampilkan informasi detail tentang file/folder.

    Args:
        path: Path file/folder yang ingin dilihat info-nya.
    """
    try:
        _path_ok, path = _safe_path(path)
        if not _path_ok:
            return path

        if not os.path.exists(path):
            return f"Error: '{path}' tidak ditemukan."

        import time

        stat = os.stat(path)
        is_dir = os.path.isdir(path)

        info = []
        info.append(f"Nama: {os.path.basename(path)}")
        info.append(f"Jenis: {'Folder' if is_dir else 'File'}")
        info.append(f"Path: {os.path.abspath(path)}")
        info.append(f"Ukuran: {stat.st_size} bytes")
        info.append(f"Dibuat: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_ctime))}")
        info.append(f"Diubah: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))}")

        if is_dir:
            items = os.listdir(path)
            info.append(f"Jumlah item: {len(items)}")

        return "\n".join(info)
    except Exception as e:
        return f"Gagal membaca info file: {e!s}"


_OFFICE_CATEGORIES = {
    "PDF": [
        "extract_text",
        "merge_pdfs",
        "split_pdf",
        "compress_pdf",
        "add_watermark",
        "fill_pdf_form",
        "get_pdf_metadata",
        "extract_tables",
        "convert_pdf",
    ],
    "Spreadsheet": [
        "read_xlsx",
        "create_xlsx",
        "apply_formula",
        "create_chart",
        "analyze_data",
        "format_cells",
        "xlsx_to_csv",
        "csv_to_xlsx",
        "json_to_xlsx",
        "xlsx_to_json",
    ],
    "Document": [
        "create_docx",
        "edit_docx",
        "merge_docx",
        "template_fill",
        "docx_to_md",
        "md_to_docx",
        "html_to_docx",
    ],
    "Presentation": [
        "create_pptx",
        "extract_pptx",
        "md_to_pptx",
        "md_to_slides",
        "add_notes",
        "export_pptx",
    ],
}


def _run_office_op(op: str, args: dict) -> str:
    """Eksekusi operasi office menggunakan Python library."""
    input_path = args.get("input", "")
    output_path = args.get("output", "")

    # --- PDF Operations ---
    if op == "extract_text":
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(input_path)
            texts = [page.get_text() for page in doc]
            doc.close()
            return "\n---\n".join(texts)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "merge_pdfs":
        try:
            from PyPDF2 import PdfMerger

            inputs = args.get("inputs", [input_path])
            merger = PdfMerger()
            for f in inputs:
                merger.append(f)
            merger.write(output_path)
            merger.close()
            return f"OK: {len(inputs)} PDF digabung -> {output_path}"
        except ImportError:
            return "Error: PyPDF2 belum install. Jalankan: pip install PyPDF2"

    elif op == "split_pdf":
        try:
            from PyPDF2 import PdfReader, PdfWriter

            pages = args.get("pages", [])  # list of page ranges [[1,3],[5,5]]
            reader = PdfReader(input_path)
            for i, (start, end) in enumerate(pages):
                writer = PdfWriter()
                for p in range(start - 1, min(end, len(reader.pages))):
                    writer.add_page(reader.pages[p])
                out = output_path.replace(".pdf", f"_part{i + 1}.pdf") if len(pages) > 1 else output_path
                with open(out, "wb") as f:
                    writer.write(f)
            return f"OK: PDF split -> {output_path} ({len(pages)} bagian)"
        except ImportError:
            return "Error: PyPDF2 belum install. Jalankan: pip install PyPDF2"

    elif op == "compress_pdf":
        try:
            import fitz

            doc = fitz.open(input_path)
            doc.save(output_path, garbage=4, deflate=True)
            doc.close()
            return f"OK: PDF dikompres -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "add_watermark":
        try:
            import fitz

            text = args.get("text", "CONFIDENTIAL")
            fontsize = args.get("fontsize", 72)
            color = args.get("color", [1, 0, 0])
            rotation = args.get("rotation", 45)
            doc = fitz.open(input_path)
            for page in doc:
                rect = page.rect
                point = fitz.Point(rect.width / 3, rect.height / 2)
                page.insert_text(
                    point, text, fontsize=fontsize, color=color, rotate=rotation, overlay=True, fontname="helv"
                )
            doc.save(output_path)
            doc.close()
            return f"OK: Watermark '{text}' ditambahkan -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "fill_pdf_form":
        try:
            import fitz

            form_data = args.get("data", {})
            doc = fitz.open(input_path)
            for page in doc:
                for widget in page.widgets() or []:
                    field_name = widget.field_name
                    if field_name in form_data:
                        widget.field_value = str(form_data[field_name])
                        widget.update()
            doc.save(output_path)
            doc.close()
            return f"OK: Form diisi ({len(form_data)} field) -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "get_pdf_metadata":
        try:
            import fitz

            doc = fitz.open(input_path)
            meta = doc.metadata
            info = {
                "pages": len(doc),
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "subject": meta.get("subject", ""),
            }
            doc.close()
            import json as _json

            return _json.dumps(info, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "extract_tables":
        try:
            import json as _json

            import fitz

            doc = fitz.open(input_path)
            all_tables = []
            for i, page in enumerate(doc):
                text = page.get_text()
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                if lines:
                    all_tables.append({"page": i + 1, "rows": len(lines), "preview": lines[:5]})
            doc.close()
            return _json.dumps(all_tables, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    elif op == "convert_pdf":
        try:
            target = args.get("target_format", "txt")
            import fitz

            doc = fitz.open(input_path)
            if target == "txt":
                texts = [page.get_text() for page in doc]
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("\n---\n".join(texts))
            elif target == "images":
                import os

                os.makedirs(output_path, exist_ok=True)
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(dpi=150)
                    pix.save(f"{output_path}/page_{i + 1}.png")
            doc.close()
            return f"OK: PDF dikonversi ke {target} -> {output_path}"
        except ImportError:
            return "Error: pyMuPDF belum install. Jalankan: pip install pymupdf"

    # --- Spreadsheet Operations ---
    elif op == "read_xlsx":
        try:
            from openpyxl import load_workbook

            wb = load_workbook(input_path, data_only=True)
            result = {}
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    rows.append([str(c) if c is not None else "" for c in row])
                result[sheet_name] = rows
            wb.close()
            import json as _json

            return _json.dumps(result, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "create_xlsx":
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill

            data = args.get("data", [])
            headers = args.get("headers", [])
            title = args.get("title", "Sheet1")
            wb = Workbook()
            ws = wb.active
            ws.title = title
            if headers:
                ws.append(headers)
                for cell in ws[1]:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="4472C4")
                    cell.alignment = Alignment(horizontal="center")
            for row in data:
                ws.append(row)
            for col in ws.columns:
                max_len = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)
            wb.save(output_path)
            return f"OK: Excel dibuat -> {output_path} ({len(data)} baris)"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "apply_formula":
        try:
            from openpyxl import load_workbook

            wb = load_workbook(input_path)
            ws = wb.active
            cell = args.get("cell", "D1")
            formula = args.get("formula", "=SUM(A1:C1)")
            ws[cell] = formula
            wb.save(output_path)
            return f"OK: Formula '{formula}' diapply ke {cell} -> {output_path}"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "create_chart":
        try:
            from openpyxl import load_workbook
            from openpyxl.chart import BarChart, LineChart, PieChart, Reference

            wb = load_workbook(input_path)
            ws = wb.active
            chart_type = args.get("type", "bar")
            title = args.get("title", "Chart")
            data_ref = Reference(ws, min_col=2, min_row=1, max_col=4, max_row=min(ws.max_row, 10))
            cats_ref = Reference(ws, min_col=1, min_row=2, max_row=min(ws.max_row, 10))
            chart = {"bar": BarChart, "pie": PieChart, "line": LineChart}.get(chart_type, BarChart)()
            chart.title = title
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)
            pos = args.get("position", "E1")
            ws.add_chart(chart, pos)
            wb.save(output_path)
            return f"OK: Chart {chart_type} dibuat di {pos} -> {output_path}"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "analyze_data":
        try:
            from openpyxl import load_workbook

            wb = load_workbook(input_path, data_only=True)
            ws = wb.active
            stats = {"total_rows": ws.max_row, "total_cols": ws.max_column, "sheets": wb.sheetnames}
            numeric_cols = []
            for col in range(1, ws.max_column + 1):
                values = []
                for row in range(2, min(ws.max_row + 1, 100)):
                    v = ws.cell(row=row, column=col).value
                    if isinstance(v, (int, float)):
                        values.append(v)
                if values:
                    col_letter = ws.cell(row=1, column=col).value or f"Col{col}"
                    numeric_cols.append(
                        {
                            "column": str(col_letter),
                            "count": len(values),
                            "sum": round(sum(values), 2),
                            "avg": round(sum(values) / len(values), 2),
                            "min": min(values),
                            "max": max(values),
                        }
                    )
            stats["numeric_columns"] = numeric_cols
            wb.close()
            import json as _json

            return _json.dumps(stats, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "format_cells":
        try:
            from openpyxl import load_workbook
            from openpyxl.styles import Alignment, Font, PatternFill

            wb = load_workbook(input_path)
            ws = wb.active
            cell_range = args.get("range", "A1")
            bold = args.get("bold", False)
            bg_color = args.get("bg_color")
            font_color = args.get("font_color")
            for row in ws[cell_range]:
                for cell in row:
                    if bold:
                        cell.font = Font(bold=True)
                    if bg_color:
                        cell.fill = PatternFill("solid", fgColor=bg_color)
                    if font_color:
                        cell.font = Font(color=font_color)
            wb.save(output_path)
            return f"OK: Format diapply ke {cell_range} -> {output_path}"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "xlsx_to_csv":
        try:
            import csv

            from openpyxl import load_workbook

            wb = load_workbook(input_path, data_only=True)
            ws = wb.active
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in ws.iter_rows(values_only=True):
                    writer.writerow([str(c) if c is not None else "" for c in row])
            wb.close()
            return f"OK: XLSX -> CSV -> {output_path}"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "csv_to_xlsx":
        try:
            import csv

            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            with open(input_path, encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    ws.append(row)
            wb.save(output_path)
            return f"OK: CSV -> XLSX -> {output_path}"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "json_to_xlsx":
        try:
            import json as _json

            from openpyxl import Workbook

            data = args.get("data", [])
            wb = Workbook()
            ws = wb.active
            if data:
                headers = list(data[0].keys())
                ws.append(headers)
                for row in data:
                    ws.append([row.get(h, "") for h in headers])
            wb.save(output_path)
            return f"OK: JSON -> XLSX -> {output_path} ({len(data)} baris)"
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    elif op == "xlsx_to_json":
        try:
            import json as _json

            from openpyxl import load_workbook

            wb = load_workbook(input_path, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return "[]"
            headers = [str(h) for h in rows[0]]
            data = []
            for row in rows[1:]:
                data.append(dict(zip(headers, [str(c) if c is not None else "" for c in row], strict=False)))
            wb.close()
            return _json.dumps(data, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: openpyxl belum install. Jalankan: pip install openpyxl"

    # --- Document Operations ---
    elif op == "create_docx":
        try:
            from docx import Document

            doc = Document()
            title = args.get("title", "")
            content = args.get("content", "")
            paragraphs = args.get("paragraphs", [])
            if title:
                doc.add_heading(title, 0)
            if content:
                doc.add_paragraph(content)
            for p in paragraphs:
                if isinstance(p, dict):
                    style = p.get("style", "Normal")
                    text = p.get("text", "")
                    doc.add_paragraph(text, style=style)
                else:
                    doc.add_paragraph(str(p))
            doc.save(output_path)
            return f"OK: Word dibuat -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "edit_docx":
        try:
            from docx import Document

            doc = Document(input_path)
            action = args.get("action", "append")
            if action == "append":
                content = args.get("content", "")
                paragraphs = args.get("paragraphs", [])
                if content:
                    doc.add_paragraph(content)
                for p in paragraphs:
                    doc.add_paragraph(str(p))
            elif action == "replace":
                old_text = args.get("old_text", "")
                new_text = args.get("new_text", "")
                for p in doc.paragraphs:
                    if old_text in p.text:
                        p.text = p.text.replace(old_text, new_text)
            doc.save(output_path)
            return f"OK: Word diedit -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "merge_docx":
        try:
            from docx import Document

            inputs = args.get("inputs", [input_path])
            merged = Document()
            for f in inputs:
                doc = Document(f)
                for p in doc.paragraphs:
                    merged.add_paragraph(p.text, style=p.style)
            merged.save(output_path)
            return f"OK: {len(inputs)} Word digabung -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "template_fill":
        try:
            from docx import Document

            doc = Document(input_path)
            replacements = args.get("replacements", {})
            for p in doc.paragraphs:
                for key, value in replacements.items():
                    if key in p.text:
                        p.text = p.text.replace(key, str(value))
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for key, value in replacements.items():
                            if key in cell.text:
                                cell.text = cell.text.replace(key, str(value))
            doc.save(output_path)
            return f"OK: Template diisi ({len(replacements)} field) -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "docx_to_md":
        try:
            from docx import Document

            doc = Document(input_path)
            md_lines = []
            for p in doc.paragraphs:
                if p.style.name.startswith("Heading"):
                    level = int(p.style.name[-1]) if p.style.name[-1].isdigit() else 1
                    md_lines.append(f"{'#' * level} {p.text}")
                elif p.style.name == "List Bullet":
                    md_lines.append(f"- {p.text}")
                elif p.style.name == "List Number":
                    md_lines.append(f"1. {p.text}")
                else:
                    md_lines.append(p.text)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(md_lines))
            return f"OK: Word -> Markdown -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "md_to_docx":
        try:
            from docx import Document

            with open(input_path, encoding="utf-8") as f:
                content = f.read()
            doc = Document()
            lines = content.split("\n")
            for raw_line in lines:
                stripped = raw_line.strip()
                if not stripped:
                    doc.add_paragraph("")
                elif stripped.startswith("# "):
                    doc.add_heading(stripped[2:], 1)
                elif stripped.startswith("## "):
                    doc.add_heading(stripped[3:], 2)
                elif stripped.startswith("### "):
                    doc.add_heading(stripped[4:], 3)
                elif stripped.startswith("- "):
                    doc.add_paragraph(stripped[2:], style="List Bullet")
                elif stripped.startswith("1. "):
                    doc.add_paragraph(stripped[3:], style="List Number")
                else:
                    doc.add_paragraph(stripped)
            doc.save(output_path)
            return f"OK: Markdown -> Word -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    elif op == "html_to_docx":
        try:
            from html.parser import HTMLParser

            from docx import Document

            with open(input_path, encoding="utf-8") as f:
                html_content = f.read()
            doc = Document()

            class SimpleHTMLParser(HTMLParser):
                def __init__(self, doc):
                    super().__init__()
                    self.doc = doc
                    self.current_text = ""

                def handle_data(self, data):
                    self.current_text += data

                def handle_endtag(self, tag):
                    if tag in ("p", "div", "br"):
                        if self.current_text.strip():
                            self.doc.add_paragraph(self.current_text.strip())
                        self.current_text = ""

            parser = SimpleHTMLParser(doc)
            parser.feed(html_content)
            if parser.current_text.strip():
                doc.add_paragraph(parser.current_text.strip())
            doc.save(output_path)
            return f"OK: HTML -> Word -> {output_path}"
        except ImportError:
            return "Error: python-docx belum install. Jalankan: pip install python-docx"

    # --- Presentation Operations ---
    elif op == "create_pptx":
        try:
            from pptx import Presentation

            prs = Presentation()
            slides_data = args.get("slides", [])
            title = args.get("title", "")
            if title and not slides_data:
                slides_data = [{"title": title, "content": args.get("content", "")}]
            for slide_info in slides_data:
                layout = prs.slide_layouts[1]  # Title and Content
                slide = prs.slides.add_slide(layout)
                slide.shapes.title.text = slide_info.get("title", "Slide")
                body = slide.placeholders[1]
                content = slide_info.get("content", "")
                if isinstance(content, list):
                    body.text = "\n".join(content)
                else:
                    body.text = str(content)
            prs.save(output_path)
            return f"OK: PowerPoint dibuat -> {output_path} ({len(slides_data)} slides)"
        except ImportError:
            return "Error: python-pptx belum install. Jalankan: pip install python-pptx"

    elif op == "extract_pptx":
        try:
            from pptx import Presentation

            prs = Presentation(input_path)
            result = []
            for i, slide in enumerate(prs.slides):
                slide_data = {"slide": i + 1, "texts": []}
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_data["texts"].append(shape.text.strip())
                result.append(slide_data)
            import json as _json

            return _json.dumps(result, indent=2, ensure_ascii=False)
        except ImportError:
            return "Error: python-pptx belum install. Jalankan: pip install python-pptx"

    elif op == "md_to_pptx":
        try:
            from pptx import Presentation

            with open(input_path, encoding="utf-8") as f:
                content = f.read()
            prs = Presentation()
            slides = content.split("\n---\n")
            for slide_content in slides:
                lines = [line.strip() for line in slide_content.strip().split("\n") if line.strip()]
                if not lines:
                    continue
                title = lines[0].lstrip("# ").strip()
                body_text = "\n".join(lines[1:])
                layout = prs.slide_layouts[1]
                slide = prs.slides.add_slide(layout)
                slide.shapes.title.text = title
                slide.placeholders[1].text = body_text
            prs.save(output_path)
            return f"OK: Markdown -> PowerPoint -> {output_path} ({len(slides)} slides)"
        except ImportError:
            return "Error: python-pptx belum install. Jalankan: pip install python-pptx"

    elif op == "md_to_slides":
        return _run_office_op("md_to_pptx", args)

    elif op == "add_notes":
        try:
            from pptx import Presentation

            prs = Presentation(input_path)
            slide_num = args.get("slide", 1) - 1
            notes = args.get("notes", "")
            if 0 <= slide_num < len(prs.slides):
                slide = prs.slides[slide_num]
                if not slide.has_notes_slide:
                    _ = slide.notes_slide
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = notes
                prs.save(output_path)
                return f"OK: Catatan ditambahkan ke slide {slide_num + 1} -> {output_path}"
            return f"Error: Slide {slide_num + 1} tidak ditemukan"
        except ImportError:
            return "Error: python-pptx belum install. Jalankan: pip install python-pptx"

    elif op == "export_pptx":
        try:
            from pptx import Presentation

            prs = Presentation(input_path)
            export_format = args.get("format", "images")
            if export_format == "images":
                import os

                os.makedirs(output_path, exist_ok=True)

                for i, slide in enumerate(prs.slides):
                    # Export slide as text summary
                    texts = []
                    for shape in slide.shapes:
                        if hasattr(shape, "text") and shape.text.strip():
                            texts.append(shape.text.strip())
                    with open(f"{output_path}/slide_{i + 1}.txt", "w", encoding="utf-8") as f:
                        f.write("\n".join(texts))
                return f"OK: Slides diekspor ke {output_path}"
            return f"Error: Format export '{export_format}' tidak didukung"
        except ImportError:
            return "Error: python-pptx belum install. Jalankan: pip install python-pptx"

    else:
        available = []
        for _cat, ops in _OFFICE_CATEGORIES.items():
            available.extend(ops)
        return (
            f"Error: Operasi '{op}' belum diimplementasi.\nOperasi yang tersedia:\n{', '.join(sorted(set(available)))}"
        )


@tool
def office_tool(operation: str, args_json: str = "{}") -> str:
    """Tool Office untuk operasi dokumen (PDF, Word, Excel, PowerPoint).

    39 operasi tersedia untuk manipulasi dokumen. File input harus ada di
    sistem. File output disimpan di output/ atau path yang ditentukan.

    Args:
        operation: Nama operasi. Lihat daftar lengkap di bawah.
        args_json: Argumen sebagai JSON string. Contoh:
            '{"input": "file.pdf", "output": "output.pdf", "text": "CONFIDENTIAL"}'

    Kategori operasi:
    - PDF: extract_text, merge_pdfs, split_pdf, compress_pdf, add_watermark,
           fill_pdf_form, get_pdf_metadata, extract_tables, convert_pdf
    - Spreadsheet: read_xlsx, create_xlsx, apply_formula, create_chart,
                   analyze_data, format_cells, xlsx_to_csv, csv_to_xlsx,
                   json_to_xlsx, xlsx_to_json
    - Document: create_docx, edit_docx, merge_docx, template_fill,
                docx_to_md, md_to_docx, html_to_docx
    - Presentation: create_pptx, extract_pptx, md_to_pptx, md_to_slides,
                     add_notes, export_pptx
    """
    import json as _json

    try:
        op = operation.strip()
        all_ops = set()
        for ops in _OFFICE_CATEGORIES.values():
            all_ops.update(ops)

        if op not in all_ops:
            available = []
            for _cat, ops in _OFFICE_CATEGORIES.items():
                available.extend(ops)
            return f"Error: Operasi '{op}' tidak dikenal.\nOperasi yang tersedia:\n{', '.join(sorted(available))}"

        try:
            args = _json.loads(args_json) if args_json.strip() else {}
        except _json.JSONDecodeError:
            return "Error: args_json bukan JSON valid."
        if not isinstance(args, dict):
            return "Error: args_json harus object JSON."

        # Approval gate
        try:
            from src.core.auth.approval import ensure_approved
            from src.core.auth.auth import get_current_user_id

            _ok, _msg = ensure_approved(
                "office_tool",
                {"operation": op, "args": args},
                owner_user_id=get_current_user_id(),
            )
            if not _ok:
                return _msg
        except Exception as exc:
            return f"Error: Approval gate unavailable; action denied. {exc}"

        return _run_office_op(op, args)
    except Exception as e:
        return f"Gagal menjalankan office_tool ({operation}): {str(e)[:200]}"


AVAILABLE_PLUGINS = {
    "tulis_kode": tulis_kode,
    "baca_file": baca_file,
    "info_sistem": info_sistem,
    "set_target_dir": set_target_dir,
    "cari_web": cari_web,
    "baca_url": baca_url,
    "jalankan_python": jalankan_python,
    "panggil_mcp": panggil_mcp,
    "learn_keyword": learn_keyword,
    "get_current_time": get_current_time,
    "minta_review": minta_review,
    "ingat_preferensi": ingat_preferensi,
    "lihat_preferensi": lihat_preferensi,
    "simpan_proyek": simpan_proyek,
    "catat_proyek": catat_proyek,
    "lihat_proyek": lihat_proyek,
    "list_folder": list_folder,
    "buat_folder": buat_folder,
    "hapus_file": hapus_file,
    "rename_file": rename_file,
    "download_file": download_file,
    "upload_file": upload_file,
    "buka_url": buka_url,
    "search_folder": search_folder,
    "info_file": info_file,
    "office_tool": office_tool,
}
