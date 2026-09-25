from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import sessionmaker

from src.api.models import FeedbackRequest
from src.core.auth.audit import append_audit
from src.core.auth.auth import require_authenticated
from src.core.db.db_engine import get_engine
from src.core.db.models import Feedback
from src.core.memory.learning import learn_from_feedback
from src.core.system.error_handling import generate_request_id
from src.plugins.input_guard import validate_user_input

router = APIRouter()

_SessionLocal = sessionmaker(bind=get_engine())


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, request: Request):
    require_authenticated(request)
    request_id = generate_request_id()
    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="rating harus 1-5")
    if req.corrected_agent and req.corrected_agent not in {
        "coder_agent",
        "admin_agent",
        "casual_agent",
    }:
        raise HTTPException(
            status_code=400,
            detail="corrected_agent harus: coder_agent, admin_agent, atau casual_agent",
        )
    with _SessionLocal() as db:
        fb = Feedback(
            session_id=req.session_id,
            agent_type=req.agent_type,
            rating=req.rating,
            comment=req.comment,
            corrected_agent=req.corrected_agent,
        )
        db.add(fb)
        db.commit()
    # Trigger learning dari feedback — guard against prompt injection di comment
    if req.corrected_agent or req.rating <= 2:
        safe, reason = validate_user_input(req.comment or "")
        if not safe:
            import logging as _logging

            _logging.getLogger("feedback_guard").warning(
                "Feedback comment blocked: %s (session=%s)", reason, req.session_id
            )
        else:
            learn_from_feedback(
                session_id=req.session_id,
                user_input=req.comment or "",
                agent_type=req.agent_type,
                rating=req.rating,
                corrected_agent=req.corrected_agent,
            )
    try:
        append_audit(
            "feedback",
            actor=req.session_id,
            details={
                "agent": req.agent_type,
                "rating": req.rating,
                "corrected": req.corrected_agent,
            },
        )
    except Exception as _e:
        import logging

        logging.getLogger(__name__).debug("audit feedback error: %s", _e)
    return {
        "status": "ok",
        "request_id": request_id,
        "rating": req.rating,
        "agent_type": req.agent_type,
        "learned": bool(req.corrected_agent or req.rating <= 2),
    }
