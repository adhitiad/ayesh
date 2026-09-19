"""Feedback-based learning — process user corrections and low ratings."""

from src.core.logger import setup_logger

logger = setup_logger("orchestrator.learning")


def learn_from_feedback(
    session_id: str,
    user_input: str,
    agent_type: str,
    rating: int,
    corrected_agent: str = None,
):
    """Proses feedback untuk belajar. Rating <= 2 = perlu perbaikan."""
    try:
        from src.core.db_engine import get_engine
        from src.core.models import RoutingLearning
        from sqlalchemy.orm import sessionmaker
        from src.config.routing_keywords_pg import (
            add_keyword_with_tools,
            invalidate_routing_cache,
        )

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        if corrected_agent and corrected_agent != agent_type:
            valid_agents = {"coder_agent", "admin_agent", "casual_agent"}
            if corrected_agent not in valid_agents:
                return

            keyword = user_input.lower().strip()[:50]

            ok = add_keyword_with_tools(corrected_agent, keyword, [])
            if ok:
                invalidate_routing_cache()
                with Session() as db:
                    learning = RoutingLearning(
                        source="feedback_correction",
                        user_input=user_input[:500],
                        old_agent=agent_type,
                        new_agent=corrected_agent,
                        keyword=keyword,
                        tools=[],
                    )
                    db.add(learning)
                    db.commit()
                logger.info(
                    "Feedback learn: '%s' -> %s (sebelumnya: %s)",
                    keyword,
                    corrected_agent,
                    agent_type,
                )

        if rating <= 2:
            with Session() as db:
                learning = RoutingLearning(
                    source="low_rating",
                    user_input=user_input[:500],
                    old_agent=agent_type,
                    new_agent=None,
                    keyword=user_input.lower().strip()[:50],
                    tools=[],
                )
                db.add(learning)
                db.commit()
            logger.info("Feedback learn: Low rating (%d) untuk %s", rating, agent_type)

    except Exception as e:
        logger.error("Gagal proses feedback learning: %s", e)


def process_pending_learnings():
    """Proses learning dari feedback yang belum diproses (dipanggil secara periodik)."""
    try:
        from src.core.db_engine import get_engine
        from src.core.models import Feedback, RoutingLearning
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select

        engine = get_engine()
        Session = sessionmaker(bind=engine)

        with Session() as db:
            feedbacks = (
                db.execute(
                    select(Feedback)
                    .where(Feedback.corrected_agent.isnot(None))
                    .order_by(Feedback.created_at.desc())
                    .limit(10)
                )
                .scalars()
                .all()
            )

            for fb in feedbacks:
                exists = db.execute(
                    select(RoutingLearning)
                    .where(RoutingLearning.source == "feedback_correction")
                    .where(RoutingLearning.user_input == (fb.comment or ""))
                ).first()

                if not exists and fb.comment:
                    learn_from_feedback(
                        session_id=fb.session_id,
                        user_input=fb.comment,
                        agent_type=fb.agent_type,
                        rating=fb.rating,
                        corrected_agent=fb.corrected_agent,
                    )
    except Exception as e:
        logger.error("Gagal process pending learnings: %s", e)
