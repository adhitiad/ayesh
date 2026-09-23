"""Tool filtering by keywords and quarantine management."""

from datetime import UTC

from src.core.observability.logger import setup_logger

logger = setup_logger("orchestrator.tools")


def filter_tools_by_keywords(agent_type: str, user_input: str) -> list:
    """Filter tools berdasarkan allowed_tools per-keyword dari database.

    Referensi DB boleh memakai suffix `@vN` (tool versioning) — resolusi
    dilakukan via src.mcp_core.versioning agar format lama tetap kompatibel.
    """
    from src.config.routing_keywords_pg import get_routing_keywords_with_tools
    from src.mcp_core import versioning

    try:
        full_data, _ = get_routing_keywords_with_tools()
    except Exception as _e:
        logger.debug("filter_tools_by_keywords DB error: %s", _e)
        return []

    lowered = user_input.lower()
    matched_tools: set = set()

    agent_keywords = full_data.get(agent_type, {})
    for kw, kw_data in agent_keywords.items():
        if kw in lowered:
            tools_for_kw = kw_data.get("allowed_tools", [])
            matched_tools.update(tools_for_kw)

    if not matched_tools:
        return []

    from src.core.auth.auth_context import get_disabled_mcp

    disabled = get_disabled_mcp()
    if disabled:
        matched_tools = {t for t in matched_tools if t.split("@")[0] not in disabled}

    return versioning.tools_from_names(matched_tools)


def log_tool_failure(
    tool_name: str,
    error_message: str,
    agent_type: str,
    session_id: str,
    keyword: str = "",
):
    """Log tool failure ke database untuk analisis learning."""
    from src.mcp_core import versioning

    # Simpan nama basis kanonik (tanpa @vN) agar agregasi karantina konsisten.
    tool_name = versioning.normalize(tool_name)
    try:
        from sqlalchemy.orm import sessionmaker

        from src.core.db.db_engine import get_engine
        from src.core.db.models import ToolFailure

        engine = get_engine()
        Session = sessionmaker(bind=engine)
        with Session() as db:
            failure = ToolFailure(
                tool_name=tool_name,
                keyword=keyword,
                error_message=str(error_message)[:500],
                agent_type=agent_type,
                session_id=session_id,
            )
            db.add(failure)
            db.commit()
            logger.info(
                "[%s] Tool failure logged: %s - %s",
                session_id,
                tool_name,
                str(error_message)[:100],
            )
    except Exception as e:
        logger.error("Gagal log tool failure: %s", e)


def learn_from_tool_failure(tool_name: str, agent_type: str, session_id: str, user_input: str) -> list | None:
    """Jika tool gagal > 3 kali untuk keyword yang sama, coba ganti tool alternatif."""
    from src.mcp_core import versioning

    tool_name = versioning.normalize(tool_name)
    try:
        from sqlalchemy import func, select
        from sqlalchemy.orm import sessionmaker

        from src.core.db.db_engine import get_engine
        from src.core.db.models import ToolFailure

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        with Session() as db:
            result = db.execute(
                select(ToolFailure.tool_name, func.count())
                .where(ToolFailure.agent_type == agent_type)
                .where(ToolFailure.tool_name == tool_name)
                .group_by(ToolFailure.tool_name)
            ).all()

            for _t_name, count in result:
                if count >= 3:
                    alternatives = {
                        "cari_web": ["tulis_kode"],
                        "tulis_kode": ["baca_file"],
                        "baca_file": ["tulis_kode"],
                    }
                    alt_tools = alternatives.get(tool_name, [])
                    if alt_tools:
                        logger.info(
                            "[%s] Tool %s gagal %dx -> alternatif: %s",
                            session_id,
                            tool_name,
                            count,
                            alt_tools,
                        )
                        return alt_tools
        return None
    except Exception as e:
        logger.error("Gagal analisis tool failure: %s", e)
        return None


def get_quarantined_tools(minutes: int = 15, threshold: int = 3) -> set:
    """Tool dengan >=threshold kegagalan dalam N menit terakhir -> karantina sementara.

    Karantina kedaluwarsa otomatis seiring waktu (jendela geser), tanpa aksi manual.
    """
    try:
        from datetime import datetime, timedelta

        from sqlalchemy import func, select
        from sqlalchemy.orm import sessionmaker

        from src.core.db.db_engine import get_engine
        from src.core.db.models import ToolFailure

        engine = get_engine()
        Session = sessionmaker(bind=engine)
        since = datetime.now(UTC) - timedelta(minutes=minutes)
        with Session() as db:
            result = db.execute(
                select(ToolFailure.tool_name, func.count())
                .where(ToolFailure.created_at >= since)
                .group_by(ToolFailure.tool_name)
                .having(func.count() >= threshold)
            ).all()
            return {r[0] for r in result}
    except Exception as _e:
        logger.debug("get_quarantined_tools DB error: %s", _e)
        return set()
