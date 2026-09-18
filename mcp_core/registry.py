"""MCP Registry: Memilih plugins berdasarkan rules agent."""

import os
import platform
import time
import asyncio
from typing import List, Any, Optional
from datetime import datetime, timezone, timedelta

from config.rules import AGENT_RULES
from plugins.core_tools import AVAILABLE_PLUGINS
from mcp_core.client import mcp_manager
from mcp_core.skills import get_skills_block
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "ayesh" / "rules"

WIB = timezone(timedelta(hours=7))

_REMOTE_CACHE: dict = {"tools": None, "ts": 0.0}
_REMOTE_CACHE_TTL: float = 300.0  # 5 menit

# Pola yang diadopsi dari system prompt Claude Code (Anthropic):
# Harness, Environment dinamis, dokumentasi tool per-item + trigger,
# Delivering work, Corrections, Tone. Berlaku umum untuk semua agent.
_IDENTITAS = (
    "## Identitas\n"
    "- Namamu Ayesh — agent AI serbaguna yang dibuat dengan cinta.\n"
    "- Bila user bertanya siapa kamu / minta perkenalan: jawab "
    "\"Aku adalah Ayesh, agent AI yang dibuat dengan cinta.\" lalu tawarkan bantuan sesuai peranmu.\n"
    "- Jangan pernah mengaku sebagai model/produk lain (Claude, ChatGPT, Gemini, dsb.) — kamu Ayesh, apa pun mesin di belakangmu."
)
_HARNESS = (    "## Harness\n"
    "- Teks yang kamu output di luar tool call ditampilkan langsung ke user sebagai markdown.\n"
    "- Tool call yang independen boleh dijalankan paralel dalam satu respons.\n"
    "- Jika sebuah tool call gagal atau ditolak, jangan ulangi verbatim — sesuaikan pendekatan atau jelaskan ke user.\n"
    "- Saat merujuk kode atau file, gunakan format file_path:line_number.\n"
    "- Laporkan hasil dengan jujur: jika gagal, katakan gagal beserta outputnya; jika ada langkah yang dilewati, katakan; klaim selesai hanya jika benar terverifikasi."
)

_DELIVERING_WORK = (
    "## Delivering Work\n"
    "- Kerjakan permintaan yang sebenarnya diminta, bukan spekulasi di baliknya. Scope yang diminta adalah deliverable — jangan diam-diam mempersempit, memperlebar, atau mengubahnya.\n"
    "- Selesaikan seluruh tugas, bukan hanya bagian mudah. Jika sebagian scope terhambat, selesaikan sisa yang lain penuh lalu nyatakan eksplisit apa yang belum dan mengapa.\n"
    "- Jika ada ambiguitas di tengah tugas, kerjakan dulu semua yang tidak bergantung pada jawaban; untuk sisanya, nyatakan asumsimu secara eksplisit atau tanyakan di waktu yang tepat."
)

_CORRECTIONS = (
    "## Corrections\n"
    "- Hindari koreksi diri yang tidak perlu. Koreksi pernyataan sebelumnya hanya jika kesalahan itu mengubah kesimpulan atau keputusan user.\n"
    "- Pertanyaan lanjutan tentang pekerjaanmu bukan sinyal bahwa kamu salah — jawab saja apa yang ditanya."
)

_TONE = (
    "## Tone\n"
    "- Gunakan Bahasa Indonesia kecuali diminta sebaliknya. Hangat, ringkas, dan fokus pada jawaban utama.\n"
    "- Gunakan list/bullet bila konten multifaset agar jelas. Jangan mengarang: jika informasi tidak ada, katakan tidak ada datanya.\n"
    "- Jangan pernah log atau sebut API key, password, atau token."
)


def _get_remote_tools() -> list:
    """Cache remote MCP tools selama 5 menit agar tidak blok tiap request."""
    now = time.time()
    if _REMOTE_CACHE["tools"] is not None and (now - _REMOTE_CACHE["ts"]) < _REMOTE_CACHE_TTL:
        return _REMOTE_CACHE["tools"]
    try:
        tools = asyncio.run(mcp_manager.list_all_tools())
    except Exception:
        tools = []
    _REMOTE_CACHE["tools"] = tools
    _REMOTE_CACHE["ts"] = now
    return tools


def _build_environment() -> str:
    """Blok environment dinamis ala Claude Code (working dir, platform, model, tanggal)."""
    current_time = datetime.now(WIB).strftime("%A, %d %B %Y %H:%M:%S WIB")
    model = os.getenv("LLM_MODEL", "unknown")
    return (
        "## Environment\n"
        f"- Working directory: {os.getcwd()}\n"
        f"- Platform: {platform.system()} ({platform.machine()}), Shell: PowerShell\n"
        f"- Model: {model}\n"
        f"- Current date/time: {current_time}."
    )


def _build_sop_block() -> str:
    """Blok SOP dari ayesh/rules/*.md sebagai teks langsung (tanpa FAISS — murah token)."""
    if not RULES_DIR.exists():
        return ""
    chunks = []
    for path in sorted(RULES_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            chunks.append(f"--- [{path.name}] ---\n{text}")
    if not chunks:
        return ""
    return "## SOP\n" + "\n\n".join(chunks)


def _build_tools_section(skills: list, tool_policy: dict) -> str:
    """Dokumentasi tool per-item beserta trigger pemakaian (pola '# Skills' Claude Code)."""
    if not skills:
        return "## Tools\n- Tidak ada tool yang tersedia. Jawab langsung dari pengetahuanmu."
    lines = ["## Tools"]
    for name in skills:
        tool = AVAILABLE_PLUGINS.get(name)
        desc = ""
        if tool is not None and getattr(tool, "description", None):
            desc = tool.description.strip().splitlines()[0]
        policy = tool_policy.get(name, "")
        lines.append(f"- {name}: {desc}")
        if policy:
            lines.append(f"  Kapan dipakai: {policy}")
    return "\n".join(lines)


def load_mcp_context(
    agent_type: str,
    session_nama: Optional[str] = None,
    session_context: Optional[str] = None,
    variant: Optional[str] = None,
) -> tuple[str, List[Any]]:
    """
    Membaca AGENT_RULES dari config/rules.py berdasarkan agent_type.
    Hanya menggunakan tools lokal (plugins) — remote MCP tools di-skip untuk performa.

    Args:
        agent_type: coder_agent, admin_agent, atau casual_agent.
        session_nama: nama session (jika sesi lanjutan) untuk konteks.
        session_context: konteks/topik session (jika sesi lanjutan).
        variant: "full" (default, dari env PROMPT_VARIANT), "no-sop", atau
            "minimal" (tanpa SOP + skills invokable + Delivering Work).
            Untuk A/B testing prompt.

    Returns:
        tuple: (system_prompt, list_of_tools)
    """
    if agent_type not in AGENT_RULES:
        raise ValueError(f"Agent type '{agent_type}' tidak dikenal. Pilihan: {list(AGENT_RULES.keys())}")
    if variant is None:
        variant = os.getenv("PROMPT_VARIANT", "full").strip().lower() or "full"
    if variant not in ("full", "no-sop", "minimal"):
        raise ValueError(f"Variant '{variant}' tidak dikenal. Pilihan: full, no-sop, minimal.")

    agent_config = AGENT_RULES[agent_type]
    skills = agent_config.get("skills", [])
    tool_policy = agent_config.get("tool_policy", {})

    # Tools Lokal saja (plugins) — skip remote MCP untuk performa
    tools = []
    for skill in skills:
        if skill in AVAILABLE_PLUGINS:
            tools.append(AVAILABLE_PLUGINS[skill])

    role = agent_config.get("role", "Agent")
    description = agent_config.get("description", "")
    tone = agent_config.get("tone", "")
    rules = agent_config.get("rules", [])
    rules_text = "\n".join([f"- {r}" for r in rules])

    sections = [f"# {role}"]
    if description:
        sections.append(description)
    sections.append(_IDENTITAS)
    sections.append(_HARNESS)
    sections.append(_build_environment())
    sections.append("## Reasoning Instructions\n- Sebelum setiap action, tulis reasoning eksplisit. Format: [REASONING] ... [ACTION] ...\n- Reasoning harus mencakup: (1) analisis user intent, (2) pertimbangan tool yang tersedia, (3) justifikasi action, (4) potensi risiko dan mitigasi.")
    if session_nama or session_context:
        session_block = "## Session"
        if session_nama:
            session_block += f"\n- Nama session: {session_nama}"
        if session_context:
            session_block += f"\n- Konteks session: {session_context}"
        session_block += "\n- Riwayat percakapan session dimuat dari memori; baca sebelum menjawab."
        sections.append(session_block)
    sections.append(_build_tools_section(skills, tool_policy))
    if variant in ("full", "no-sop"):
        skills_block = get_skills_block()
        if skills_block:
            sections.append(skills_block)
    if variant == "full":
        sop_block = _build_sop_block()
        if sop_block:
            sections.append(sop_block)
    if rules_text:
        sections.append(f"## Rules\n{rules_text}")
    if variant in ("full", "no-sop"):
        sections.append(_DELIVERING_WORK)
    sections.append(_CORRECTIONS)
    sections.append(_TONE if not tone else f"## Tone\n- {tone}")

    system_prompt = "\n\n".join(sections)

    return system_prompt, tools
