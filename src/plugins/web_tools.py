"""Web tools: cari_web, learn_keyword, minta_review, baca_url."""

import asyncio
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from langchain_core.tools import tool

from src.plugins.tool_error import tool_error, tool_error_from_exception


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
        return tool_error_from_exception(e)


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

    from src.config.routing_keywords_pg import sanitize_keyword_tools

    tools_list = [t.strip() for t in allowed_tools.split(",") if t.strip()] if allowed_tools else []
    sanitized = sanitize_keyword_tools(agent, tools_list)
    if sanitized is None:
        return f"Error: agent '{agent}' tidak valid."

    ok = add_keyword_with_tools(agent, keyword, sanitized)
    if ok:
        invalidate_routing_cache()
        tools_str = ", ".join(sanitized) if sanitized else "(no tools)"
        dropped = [t for t in tools_list if t not in sanitized]
        note = f" Tool ditolak (di luar kapasitas {agent}): {', '.join(dropped)}." if dropped else ""
        return f"Keyword '{keyword}' berhasil disimpan untuk {agent}. Allowed tools: [{tools_str}].{note}"
    return tool_error("Gagal menyimpan keyword")


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
    from src.core.llm.factory import get_llm

    try:
        llm = get_llm()
        response = llm.invoke(
            f"{_ADVISOR_PROMPT}\n\n## Konteks pekerjaan\n{konteks[:3000]}\n\n## Pertanyaan agen\n{pertanyaan}"
        )
        from src.core.llm.text import extract_text

        content = extract_text(response.content if hasattr(response, "content") else str(response))
        return f"Nasihat reviewer:\n{content}"
    except Exception as e:
        return tool_error_from_exception(e)


# --- baca_url with SSRF Protection ---

_PRIVATENETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
]
_PRIVATENETWORKS_V6 = [
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
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
        return True
    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _PRIVATENETWORKS)
    elif isinstance(addr, ipaddress.IPv6Address):
        return any(addr in net for net in _PRIVATENETWORKS_V6)
    return True


def _resolve_public_address(hostname: str, port: int | None = None) -> str:
    """Resolve DNS once and reject any private, loopback, or link-local result."""
    if not hostname:
        return ""
    try:
        infos = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return ""
    for _family, _socktype, _proto, _canonname, sockaddr in infos:
        if _is_ip_private(str(sockaddr[0])):
            return ""
    return str(infos[0][4][0]) if infos else ""


def _resolve_and_validate(hostname: str, port: int | None = None) -> str:
    """Return the hostname only when every resolved address is public."""
    return hostname if _resolve_public_address(hostname, port) != "" else ""


def _validate_url_shape(target_url: str, depth: int = 0) -> bool:
    """Validate URL syntax before performing DNS resolution."""
    if depth > _MAX_REDIRECTS:
        return False
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    blocked_hostnames = {
        "169.254.169.254",
        "metadata.google.internal",
        "instance-data.ec2.internal",
        "metadata.tencentyun.com",
        "kubernetes.default",
        "100.100.100.200",
        "fd00:ec2::254",
    }
    hostname_l = hostname.lower().rstrip(".")
    if hostname_l in blocked_hostnames:
        return False
    if hostname_l.endswith((".internal", ".local", ".svc")):
        return False
    return bool(re.match(r"^[a-zA-Z0-9._-]+$", hostname))


def _validate_url_with_address(target_url: str, depth: int = 0) -> tuple:
    """Validate a URL and resolve its DNS address without a second lookup."""
    if not _validate_url_shape(target_url, depth):
        return False, ""
    parsed = urlparse(target_url)
    hostname = parsed.hostname
    if not hostname:
        return False, ""
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False, ""
    address = _resolve_public_address(hostname=hostname, port=port)
    if not address:
        return False, ""
    return True, address


def _open_pinned_connection(hostname: str, port: int, scheme: str, address: str, timeout: float):
    """Open an HTTP(S) connection pinned to a validated IP (anti DNS-rebinding).

    For HTTPS, SNI and certificate verification stay bound to the original hostname.
    """
    import http.client

    if scheme == "https":
        context = ssl.create_default_context()
        sock = socket.create_connection((address, port), timeout=timeout)
        conn = http.client.HTTPSConnection(hostname, port, timeout=timeout, context=context)
        conn.sock = context.wrap_socket(sock, server_hostname=hostname)
        return conn
    return http.client.HTTPConnection(address, port, timeout=timeout)


def _fetch_with_ssrf_protection(target_url: str, address: str | None = None) -> str:
    """Fetch URL with SSRF protection: scheme/host/IP validation, redirect revalidation."""
    if address is None:
        valid, address = _validate_url_with_address(target_url)
        if not valid or not address:
            return ""
    parsed = urlparse(target_url)
    hostname = parsed.hostname
    if not hostname:
        return ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    conn = _open_pinned_connection(hostname, port, parsed.scheme, address, _CONNECT_TIMEOUT)

    headers = {"User-Agent": "Mozilla/5.0", "Host": hostname or ""}
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

        data = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            data += chunk
            if len(data) > _MAX_RESPONSE_BYTES:
                resp.close()
                return ""

        status = resp.status
        location = resp.getheader("Location", "")
        resp.close()
        if 300 <= status < 400:
            if not location:
                break
            next_url = urljoin(current_url, location)
            redirect_count += 1
            if redirect_count > _MAX_REDIRECTS:
                return ""
            valid, address = _validate_url_with_address(next_url, redirect_count)
            if not valid or not address:
                return ""
            conn.close()
            parsed = urlparse(next_url)
            hostname = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            conn = _open_pinned_connection(hostname, port, parsed.scheme, address, _CONNECT_TIMEOUT)
            headers["Host"] = hostname
            current_url = next_url
            continue

        break

    conn.close()
    return data.decode("utf-8", errors="replace")


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


@tool
def baca_url(url: str, max_karakter: int = 8000) -> str:
    """Membaca isi teks halaman web (deep-read lanjutan dari hasil cari_web).

    Args:
        url: URL http/https yang ingin dibaca.
        max_karakter: Batas panjang teks (default 8000).
    """
    # SSRF protection constants: _CONNECT_TIMEOUT, _MAX_REDIRECTS, _MAX_RESPONSE_BYTES, _READ_TIMEOUT
    # DNS resolution via socket.getaddrinfo
    try:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "Error: URL harus http/https."

        parsed = urlparse(url)
        if not parsed.hostname:
            return "Error: URL tidak valid."

        valid, address = _validate_url_with_address(url, 0)
        if not valid or not address:
            return "Error: URL ditolak (private/loopback/link-local/metadata endpoint)."

        raw = _fetch_with_ssrf_protection(url, address)
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
        return tool_error_from_exception(e)
