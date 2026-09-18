"""Plugin Tools (Tangan & Kaki AI) untuk eksekusi aksi nyata di sistem lokal."""

import os
import asyncio
from langchain_core.tools import tool

from plugins.time_tool import get_current_time


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


_SENSITIVE_NAMES = {".env"}
_SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".asc", ".gpg")


def _safe_path(path: str) -> tuple:
    """Validasi path: di dalam root DAN bukan file sensitif. Return (ok, abs/error)."""
    p = (path or "").strip()
    if not p:
        return False, "Error: path kosong."
    ap = os.path.abspath(os.path.join(_PROJECT_ROOT, p))
    if ap != _PROJECT_ROOT and not ap.startswith(_PROJECT_ROOT + os.sep):
        return False, f"Error: path di luar project root ({_PROJECT_ROOT})."
    base = os.path.basename(ap).lower()
    if base in _SENSITIVE_NAMES or base.endswith(_SENSITIVE_SUFFIXES):
        return False, f"Error: file '{base}' sensitif, akses ditolak."
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
            from core.approval import ensure_approved
            _ok, _msg = ensure_approved("tulis_kode", {"filepath": filepath, "overwrite": overwrite})
            if not _ok:
                return _msg
        except Exception:
            pass
        if os.path.exists(filepath) and not overwrite:
            return f"Error: File '{filepath}' sudah ada. Gunakan overwrite=True untuk menimpa."
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(konten)
        return f"File berhasil dibuat di {filepath}"
    except Exception as e:
        return f"Gagal menulis file: {str(e)}"


@tool
def baca_file(filepath: str) -> str:
    """Membaca isi dari file lokal (terbatas di dalam project root)."""
    try:
        _path_ok, filepath = _safe_path(filepath)
        if not _path_ok:
            return filepath
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Error: File tidak ditemukan."
    except Exception as e:
        return f"Error saat membaca file: {str(e)}"


@tool
def cari_web(query: str) -> str:
    """Melakukan pencarian informasi terkini di internet menggunakan Tavily MCP."""
    try:
        from mcp_core.client import mcp_manager

        async def _search():
            # Tavily dulu, fallback ke Exa bila gagal
            result = await mcp_manager.call_tool(
                "tavily", "tavily_search", {"query": query, "max_results": 5}
            )
            if isinstance(result, str) and result.startswith("Error"):
                result = await mcp_manager.call_tool(
                    "exa", "exa_search", {"query": query, "max_results": 5}
                )
            return result

        result = asyncio.run(_search())
        # Extract text from MCP result
        from core.text import extract_text
        if hasattr(result, "content") and result.content:
            text = extract_text(result.content, sep="\n\n")
            return text or str(result)
        return str(result)
    except Exception as e:
        return f"Gagal mencari web: {str(e)}"


@tool
def learn_keyword(agent: str, keyword: str, allowed_tools: str = "") -> str:
    """Simpan keyword routing baru ke database agar request serupa bisa langsung di-route ke agent yang tepat di masa depan.

    Args:
        agent: Nama agent yang sesuai (coder_agent, admin_agent, atau casual_agent).
        keyword: Kata kunci yang ingin disimpan (huruf kecil).
        allowed_tools: Daftar tool yang diizinkan untuk keyword ini, dipisah koma. Contoh: "tulis_kode,baca_file". Kosongkan jika tidak perlu tool.
    """
    from config.routing_keywords_pg import (
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

    tools_list = (
        [t.strip() for t in allowed_tools.split(",") if t.strip()]
        if allowed_tools
        else []
    )

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
    from agents.llm_config import get_llm

    try:
        llm = get_llm()
        response = llm.invoke(
            f"{_ADVISOR_PROMPT}\n\n## Konteks pekerjaan\n{konteks[:3000]}\n\n## Pertanyaan agen\n{pertanyaan}"
        )
        from core.text import extract_text
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
    import re
    import urllib.request
    from html.parser import HTMLParser

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

    try:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return "Error: URL harus http/https."
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(2_000_000).decode("utf-8", errors="replace")
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

    Args:
        kode: Kode Python untuk dieksekusi langsung.
        filepath: Path file .py lokal untuk dijalankan.
        timeout_detik: Batas waktu eksekusi (default 30, maks 120).
    """
    import subprocess
    import sys

    try:
        try:
            from core.approval import ensure_approved
            _ok, _msg = ensure_approved("jalankan_python", {"filepath": filepath, "has_code": bool(kode)})
            if not _ok:
                return _msg
        except Exception:
            pass
        if not kode and not filepath:
            return "Error: Isi salah satu: kode atau filepath."
        timeout_detik = max(1, min(int(timeout_detik), 120))
        root = _PROJECT_ROOT
        if filepath:
            if not filepath.endswith(".py"):
                return "Error: Hanya file .py yang boleh dijalankan."
            _path_ok, filepath = _safe_path(filepath)
            if not _path_ok:
                return filepath
            cmd = [sys.executable, filepath]
        else:
            cmd = [sys.executable, "-c", kode]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_detik, cwd=root)
        out = (proc.stdout or "") + (proc.stderr or "")
        out = out.strip()[:6000] or "(tidak ada output)"
        return f"exit={proc.returncode}\n{out}"
    except subprocess.TimeoutExpired:
        return f"Error: Eksekusi melebihi {timeout_detik}s (timeout)."
    except Exception as e:
        return f"Gagal menjalankan Python: {str(e)[:200]}"


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
        from mcp_core.client import mcp_manager

        server = server.strip()
        if server in _MCP_BLOCKED_SERVERS:
            return f"Error: Server '{server}' diblokir. Untuk file lokal pakai tulis_kode/baca_file."
        try:
            args = _json.loads(args_json) if args_json.strip() else {}
        except _json.JSONDecodeError:
            return "Error: args_json bukan JSON valid."
        if not isinstance(args, dict):
            return "Error: args_json harus object JSON."
        try:
            from core.approval import ensure_approved
            _ok, _msg = ensure_approved("panggil_mcp", {"server": server, "tool": tool})
            if not _ok:
                return _msg
        except Exception:
            pass

        async def _call():
            return await mcp_manager.call_tool(server, tool, args)

        result = asyncio.run(_call())
        from core.text import extract_text
        if hasattr(result, "content") and result.content:
            text = extract_text(result.content, sep="\n\n")
            return text or str(result)
        return str(result)
    except Exception as e:
        return f"Gagal memanggil MCP {server}/{tool}: {str(e)[:200]}"


def _pref_user() -> str:
    try:
        from core.auth import get_current_user
        return get_current_user()
    except Exception:
        return "default"


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
        from config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _pref_ensure_table(cur)
        conn.commit()
        cur.execute("SELECT key, value FROM preferensi WHERE user_id = %s ORDER BY key;", (_pref_user(),))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["Preferensi user yang tersimpan:"]
        lines += [f"- {k}: {v}" for k, v in rows]
        return "\n".join(lines)
    except Exception:
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
        from config.routing_keywords_pg import DATABASE_URL

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
    try:
        from core.auth import get_current_user
        return get_current_user()
    except Exception:
        return "default"


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
        from config.routing_keywords_pg import DATABASE_URL

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _proj_ensure_table(cur)
        conn.commit()
        cur.execute("SELECT nama, goal, status, catatan FROM proyek WHERE user_id = %s AND status <> 'selesai' ORDER BY updated_at DESC;", (_proj_user(),))
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
    except Exception:
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
        from config.routing_keywords_pg import DATABASE_URL

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
        from config.routing_keywords_pg import DATABASE_URL

        nama = nama.strip().lower().replace(" ", "-")[:60]
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        _proj_ensure_table(cur)
        cur.execute("SELECT catatan FROM proyek WHERE user_id = %s AND nama = %s;", (_proj_user(), nama))
        row = cur.fetchone()
        if not row:
            conn.close()
            return f"Error: proyek '{nama}' tidak ada. Simpan dulu via simpan_proyek."
        merged = ((row[0] + " | " if row[0] else "") + catatan.strip())[:2000]
        cur.execute("UPDATE proyek SET catatan = %s, updated_at = NOW() WHERE user_id = %s AND nama = %s;", (merged, _proj_user(), nama))
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


AVAILABLE_PLUGINS = {
    "tulis_kode": tulis_kode,
    "baca_file": baca_file,
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
}
