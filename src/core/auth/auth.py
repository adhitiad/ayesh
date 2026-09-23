"""Multi-user + API keys with RBAC — re-export layer.

- users: id, name, key_hash (sha256), prefix (8 char awal, untuk identifikasi),
  role (owner|admin|user), active, created_at. Rotasi: old_key_hash / old_prefix /
  old_key_expires_at menahan key lama agar tetap valid selama masa tenggang.
- Auth: header X-API-Key atau Authorization: Bearer. Default produksi: REQUIRE_API_KEY=1
  (key wajib; tanpa key valid → 401). Bila REQUIRE_API_KEY=0 eksplisit, /chat* boleh
  tanpa key (user "default"); endpoint control-plane TETAP wajib key (fail-closed).
- Scope data: preferensi & proyek difilter per user via ContextVar current_user.
  Single-user lama otomatis jadi user "default" (kolom DEFAULT 'default').
- Rotasi API key: rotate_user_key() membuat key baru; key lama tetap diakui oleh
  verify_key() selama `API_KEY_ROTATION_GRACE_HOURS` (default 24). Masa tenggang
  memberhentikan key lama TANPA memutus integrasi yang belum di-update.
- RBAC roles:
  owner: users, jobs, approvals, logs, audit, analytics, system configuration
  admin: operational endpoints (tasks, sessions, memory, chat)
  user: chat, own sessions, own memory, own tasks
"""

# ── Re-export all public symbols from submodules ───────────────────────
from src.core.auth.auth_context import (
    UserLLMConfig,
    _authenticated,
    _utcnow,
    current_user,
    current_user_llm_config,
    current_user_role,
    get_current_user,
    get_current_user_id,
    get_current_user_llm_config,
    get_current_user_role,
    is_authenticated,
    set_current_user,
    set_current_user_llm_config,
    set_current_user_role,
)
from src.core.auth.auth_guards import (
    bootstrap_owner,
    require_admin,
    require_auth,
    require_authenticated,
    require_owner,
    require_owner_only,
    require_owner_or_admin,
)
from src.core.auth.auth_keys import (
    _ensure_rotation_columns,
    _ensure_user_config_tables,
    _hash_key,
    add_user_llm_config,
    create_user,
    deactivate_user,
    delete_user_llm_config,
    get_user_default_llm,
    invalidate_user_cache,
    is_mcp_enabled_for_user,
    is_skill_enabled_for_user,
    list_user_llm_configs,
    list_user_mcp_overrides,
    list_user_skill_overrides,
    list_users,
    rotate_user_key,
    set_user_mcp_override,
    set_user_skill_override,
    update_user_llm_config_entry,
    verify_key,
)
from src.core.auth.auth_request import bind_request_user

__all__ = [
    "UserLLMConfig",
    "_authenticated",
    "_ensure_rotation_columns",
    "_ensure_user_config_tables",
    "_hash_key",
    "_utcnow",
    "add_user_llm_config",
    "bind_request_user",
    "bootstrap_owner",
    "create_user",
    "current_user",
    "current_user_llm_config",
    "current_user_role",
    "deactivate_user",
    "delete_user_llm_config",
    "get_current_user",
    "get_current_user_id",
    "get_current_user_llm_config",
    "get_current_user_role",
    "get_user_default_llm",
    "invalidate_user_cache",
    "is_authenticated",
    "is_mcp_enabled_for_user",
    "is_skill_enabled_for_user",
    "list_user_llm_configs",
    "list_user_mcp_overrides",
    "list_user_skill_overrides",
    "list_users",
    "require_admin",
    "require_auth",
    "require_authenticated",
    "require_owner",
    "require_owner_only",
    "require_owner_or_admin",
    "rotate_user_key",
    "set_current_user",
    "set_current_user_llm_config",
    "set_current_user_role",
    "set_user_mcp_override",
    "set_user_skill_override",
    "update_user_llm_config_entry",
    "verify_key",
]
