from fastapi import APIRouter
from fastapi import Request, HTTPException
from src.api.models import FeedbackRequest
from main import route_request
from src.core.auth import require_auth, require_admin
from src.core.learning import learn_from_feedback
from src.core.audit import append_audit
from sqlalchemy.orm import sessionmaker
from src.core.models import Feedback
from src.core.db_engine import get_engine

router = APIRouter()

_SessionLocal = sessionmaker(bind=get_engine())


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, request: Request):
    user_id = require_auth(request)
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
    # Trigger learning dari feedback
    if req.corrected_agent or req.rating <= 2:
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
        "rating": req.rating,
        "agent_type": req.agent_type,
        "learned": bool(req.corrected_agent or req.rating <= 2),
    }
