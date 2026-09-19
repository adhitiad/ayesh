from fastapi import Depends
from fastapi import Request, HTTPException
from src.core.auth import (
    require_auth,
    require_admin,
    require_owner,
    require_owner_or_admin,
    require_owner_only,
    get_current_user_id,
)
from src.core.db import connect
from src.core.models import Session

require_auth = Depends(require_auth)
require_admin = Depends(require_admin)
require_owner = Depends(require_owner)
require_owner_or_admin = Depends(require_owner_or_admin)
require_owner_only = Depends(require_owner_only)
get_current_user_id = Depends(get_current_user_id)

async def get_db():
    db = connect()
    try:
        yield db
    finally:
        db.close()
