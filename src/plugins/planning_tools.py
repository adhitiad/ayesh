"""Multi-step planning tools: buat_plan, lihat_plan, cari_plan, jalankan_langkah, tandai_selesai, batal_plan."""

import logging
import re
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.core.db.db_engine import get_engine
from src.core.db.models import Plan, PlanStep
from src.plugins.tool_error import tool_error_from_exception

logger = logging.getLogger(__name__)

engine = get_engine()
SessionLocal = sessionmaker(bind=engine)

MAX_LANGKAH = 20
_PLAN_STATUS = {"aktif", "selesai", "batal"}
_STEP_ICON = {"pending": "?", "berjalan": "->", "selesai": "OK", "gagal": "X"}


def _plan_user() -> str:
    """Get current owner user ID for plan scoping. Never returns 'default'."""
    try:
        from src.core.auth.auth import get_current_user_id

        uid = get_current_user_id()
        if uid and uid != "default":
            return uid
    except Exception as _e:
        logger.debug("_plan_user error: %s", _e)
    return "anonymous"


def _utcnow():
    """Current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def _parse_langkah(raw: str) -> list[str]:
    """Split raw multi-line step text into a clean list of step descriptions."""
    steps = []
    for raw_line in raw.splitlines():
        cleaned = re.sub(r"^\s*\d+[.)]\s+", "", raw_line.strip())
        if cleaned:
            steps.append(cleaned[:500])
    return steps


def _format_plan(plan, steps) -> str:
    """Render a plan + its steps into a readable block."""
    lines = [
        f"Rencana '{plan.judul}' [{plan.status}]",
        f"Tujuan: {plan.tujuan}",
        f"Progress: {plan.langkah_selesai}/{plan.total_langkah}",
    ]
    for step in steps:
        icon = _STEP_ICON.get(step.status, "?")
        line = f"  {step.urutan}. [{icon}] {step.deskripsi}"
        if step.status == "selesai" and step.hasil:
            line += f"\n     => {step.hasil[:300]}"
        lines.append(line)
    lines.append(f"ID: {plan.id}")
    return "\n".join(lines)


def _run_step_llm(judul: str, tujuan: str, urutan: int, deskripsi: str, steps_text: str) -> str:
    """Execute one plan step via a single direct LLM call (no tool recursion)."""
    from src.core.llm.task_routing import get_llm_for_task
    from src.core.llm.text import extract_text

    system = (
        "Kamu adalah pelaksana langkah dari rencana Ayesh.\n"
        f"Judul rencana: {judul}\n"
        f"Tujuan: {tujuan}\n\n"
        "Kerjakan HANYA langkah yang diminta dengan teliti. "
        "Tulis hasil yang konkret dan ringkas (maksimal ~400 kata). "
        "Jangan mengulang seluruh rencana dan jangan mengeksekusi langkah lain."
    )
    user_msg = f"Langkah-langkah rencana:\n{steps_text}\n\nKerjakan langkah {urutan}: {deskripsi}"
    try:
        llm = get_llm_for_task("plan")
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user_msg)])
        hasil = extract_text(response.content if hasattr(response, "content") else str(response))
        if not hasil or not hasil.strip():
            return ""
        return hasil.strip()[:6000]
    except Exception as _e:
        logger.warning("jalankan_langkah LLM gagal: %s", _e)
        return ""


@tool
def buat_plan(judul: str, tujuan: str, langkah: str) -> str:
    """Buat rencana multi-langkah untuk tugas kompleks (lintas session & bisa dilanjutkan).

    Pakai saat task butuh >1 langkah berurutan (minta langkah ke agent satu per satu,
    bukan sekaligus). Simpan rencana lalu jalankan langkah via tool jalankan_langkah.

    Args:
        judul: Judul pendek rencana. Contoh: "migrasi-db".
        tujuan: Tujuan akhir rencana dalam 1-2 kalimat.
        langkah: Uraian langkah, satu langkah per baris. Contoh:
            "1. Analisis skema lama
             2. Buat migrasi
             3. Uji data"
    """
    try:
        judul = judul.strip()[:200]
        tujuan = tujuan.strip()[:2000]
        steps = _parse_langkah(langkah)
        if not judul or not tujuan:
            return "Error: judul dan tujuan tidak boleh kosong."
        if not steps:
            return "Error: langkah tidak boleh kosong (pisahkan tiap langkah dengan baris baru)."
        if len(steps) > MAX_LANGKAH:
            return f"Error: maksimal {MAX_LANGKAH} langkah per rencana."

        owner_id = _plan_user()
        with SessionLocal() as session:
            plan = Plan(owner_user_id=owner_id, judul=judul, tujuan=tujuan, total_langkah=len(steps))
            session.add(plan)
            session.flush()
            for i, desk in enumerate(steps, start=1):
                session.add(PlanStep(plan_id=plan.id, urutan=i, deskripsi=desk))
            session.commit()
            plan_id = plan.id

        return (
            f"Rencana dibuat: {judul} ({len(steps)} langkah). ID: {plan_id}\n"
            "Mulai dengan tool jalankan_langkah plan_id=<id> urutan=1."
        )
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def lihat_plan(plan_id: str) -> str:
    """Lihat detail rencana beserta status setiap langkah dan hasil yang sudah berjalan.

    Args:
        plan_id: ID rencana (dari buat_plan / cari_plan).
    """
    try:
        owner_id = _plan_user()
        with SessionLocal() as session:
            plan = session.execute(
                select(Plan).where(Plan.id == plan_id.strip(), Plan.owner_user_id == owner_id)
            ).scalar_one_or_none()
            if not plan:
                return "Error: rencana tidak ditemukan (atau bukan milik Anda)."
            steps = (
                session.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.urutan))
                .scalars()
                .all()
            )
            return _format_plan(plan, steps)
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def cari_plan(status: str = "aktif", limit: int = 5) -> str:
    """Cari daftar rencana milik user.

    Args:
        status: Filter status: aktif / selesai / batal / semua.
        limit: Maksimal hasil (isi 1-20).
    """
    try:
        status = status.strip().lower()
        limit = max(1, min(20, int(limit)))
        owner_id = _plan_user()
        with SessionLocal() as session:
            stmt = select(Plan).where(Plan.owner_user_id == owner_id)
            if status != "semua":
                stmt = stmt.where(Plan.status == status)
            rows = list(session.execute(stmt.order_by(Plan.updated_at.desc()).limit(limit)).scalars())
            if not rows:
                return f"Tidak ada rencana berstatus '{status}'."
            blocks = []
            for plan in rows:
                steps = (
                    session.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.urutan))
                    .scalars()
                    .all()
                )
                blocks.append(_format_plan(plan, steps))
            return "\n\n".join(blocks)
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def jalankan_langkah(plan_id: str, urutan: int) -> str:
    """Kerjakan satu langkah dari rencana dan simpan hasilnya.

    Panggil berurutan (1, 2, 3, ...) sampai semua langkah selesai. Rencana
    tetap tersimpan lintas session, jadi bisa dilanjutkan belakangan.

    Args:
        plan_id: ID rencana (dari buat_plan / cari_plan).
        urutan: Nomor langkah yang dikerjakan (mulai 1).
    """
    try:
        owner_id = _plan_user()
        with SessionLocal() as session:
            plan = session.execute(
                select(Plan).where(Plan.id == plan_id.strip(), Plan.owner_user_id == owner_id)
            ).scalar_one_or_none()
            if not plan:
                return "Error: rencana tidak ditemukan (atau bukan milik Anda)."
            if plan.status != "aktif":
                return f"Error: rencana berstatus '{plan.status}', tidak bisa dijalankan."
            all_steps = list(
                session.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.urutan)).scalars()
            )
            step = next((s for s in all_steps if s.urutan == urutan), None)
            if step is None:
                return f"Error: langkah {urutan} tidak ada (total {plan.total_langkah})."
            if step.status == "selesai":
                return f"Langkah {urutan} sudah selesai.\n{step.hasil or ''}"
            step.status = "berjalan"
            step.updated_at = _utcnow()
            plan.updated_at = _utcnow()
            session.commit()

            plan_id_snap = plan.id
            plan_judul_snap = plan.judul
            plan_tujuan_snap = plan.tujuan
            step_desk_snap = step.deskripsi
            steps_lines = []
            for s in all_steps:
                mark = f"{s.urutan}. [{_STEP_ICON.get(s.status, '?')}] {s.deskripsi}"
                if s.status == "selesai" and s.hasil and s.urutan < urutan:
                    mark += f"\n   hasil: {s.hasil[:500]}"
                steps_lines.append(mark)

        hasil = _run_step_llm(plan_judul_snap, plan_tujuan_snap, urutan, step_desk_snap, "\n".join(steps_lines))

        with SessionLocal() as session:
            plan = session.get(Plan, plan_id_snap)
            if plan is None:
                return "Error: rencana tidak ditemukan."
            step = session.execute(
                select(PlanStep).where(PlanStep.plan_id == plan.id, PlanStep.urutan == urutan)
            ).scalar_one()
            if hasil:
                step.hasil = hasil
                step.status = "selesai"
                plan.langkah_selesai += 1
                if plan.langkah_selesai >= plan.total_langkah:
                    plan.status = "selesai"
            else:
                step.status = "gagal"
            plan.updated_at = _utcnow()
            session.commit()
            plan_status = plan.status
            plan_progress = f"{plan.langkah_selesai}/{plan.total_langkah}"
            plan_judul = plan.judul
            step_deskripsi = step.deskripsi

        if not hasil:
            return f"Error: langkah {urutan} gagal dieksekusi. Coba ulang dengan jalankan_langkah."
        out = f"Langkah {urutan} '{step_deskripsi}' selesai.\n{hasil}\n\nProgress: {plan_progress}"
        if plan_status == "selesai":
            out += f"\n\nRencana '{plan_judul}' SELESAI. Semua langkah sudah dikerjakan."
        return out
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def tandai_selesai(plan_id: str) -> str:
    """Tandai seluruh rencana sebagai selesai (walau masih ada langkah tersisa).

    Args:
        plan_id: ID rencana.
    """
    try:
        owner_id = _plan_user()
        with SessionLocal() as session:
            plan = session.execute(
                select(Plan).where(Plan.id == plan_id.strip(), Plan.owner_user_id == owner_id)
            ).scalar_one_or_none()
            if not plan:
                return "Error: rencana tidak ditemukan (atau bukan milik Anda)."
            plan.status = "selesai"
            plan.updated_at = _utcnow()
            session.commit()
            return f"Rencana '{plan.judul}' ditandai selesai."
    except Exception as e:
        return tool_error_from_exception(e)


@tool
def batal_plan(plan_id: str) -> str:
    """Batalkan rencana (status 'batal'); langkah berjalan dihentikan.

    Args:
        plan_id: ID rencana.
    """
    try:
        owner_id = _plan_user()
        with SessionLocal() as session:
            plan = session.execute(
                select(Plan).where(Plan.id == plan_id.strip(), Plan.owner_user_id == owner_id)
            ).scalar_one_or_none()
            if not plan:
                return "Error: rencana tidak ditemukan (atau bukan milik Anda)."
            if plan.status == "selesai":
                return f"Error: rencana '{plan.judul}' sudah selesai, tidak bisa dibatalkan."
            plan.status = "batal"
            plan.updated_at = _utcnow()
            session.commit()
            return f"Rencana '{plan.judul}' dibatalkan."
    except Exception as e:
        return tool_error_from_exception(e)
