"""FastAPI dependency injection helpers.

Usage:
    from src.api.dependencies import require_auth, require_admin

    @router.get("/endpoint")
    def my_endpoint(user_id: str = require_auth):
        ...

Note: These are currently unused — auth checks are done directly in route functions.
Kept for future DI refactoring if needed.
"""

from src.core.auth.auth import (
    get_current_user_id,
    require_admin,
    require_auth,
    require_owner,
    require_owner_only,
    require_owner_or_admin,
)

__all__ = [
    "get_current_user_id",
    "require_admin",
    "require_auth",
    "require_owner",
    "require_owner_only",
    "require_owner_or_admin",
]
