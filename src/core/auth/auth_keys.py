"""API key management: create, verify, rotate, list, deactivate."""

import hashlib
import logging
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_

_ROTATION_COLUMNS = {
    "old_key_hash": "VARCHAR(128)",
    "old_prefix": "VARCHAR(20)",
    "old_key_expires_at": "TIMESTAMP",
}
_VIP_COLUMNS = {
    "vip_since": "TIMESTAMP",
    "vip_expires_at": "TIMESTAMP",
    "vip_ref": "VARCHAR(100)",
    "vip_amount_cents": "INTEGER",
}
_VALID_ROLES = {"owner", "vip", "user"}
_columns_ensured = False
_columns_lock = threading.Lock()
_vip_columns_ensured = False
_vip_tables_ensured = False

# ── Per-user config cache (TTL 5 min) ─────────────────────────────────
_CACHE_TTL = float(os.getenv("USER_CONFIG_CACHE_TTL", "300"))
_user_cache: dict[str, dict] = {}
_user_cache_lock = threading.Lock()


def _cache_key(uid: str, kind: str) -> str:
    return f"{uid}:{kind}"


def _cache_get(uid: str, kind: str) -> dict | None:
    key = _cache_key(uid, kind)
    with _user_cache_lock:
        entry = _user_cache.get(key)
        if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
            return entry["data"]
    return None


def _cache_set(uid: str, kind: str, data: dict | None) -> None:
    key = _cache_key(uid, kind)
    with _user_cache_lock:
        _user_cache[key] = {"data": data, "ts": time.time()}


def invalidate_user_cache(uid: str) -> None:
    """Hapus semua cache user (dipanggil saat update config)."""
    with _user_cache_lock:
        keys_to_del = [k for k in _user_cache if k.startswith(f"{uid}:")]
        for k in keys_to_del:
            del _user_cache[k]


def _hash_key(api_key: str) -> str:
    """Hash API key: salt acak per-key + SHA-256, format self-describing `salt$digest`.

    Format lama (sha256 hex polos) tetap divalidasi `_verify_hash` dan di-upgrade
    opportunistic ke format salted saat key cocok (legacy → salted, vuln-0003).
    """
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{api_key}".encode()).hexdigest()
    return f"{salt}${digest}"


def _verify_hash(api_key: str, stored: str) -> bool:
    """Validasi api_key terhadap stored hash — dukung format baru (`salt$digest`) dan lama (sha256 hex)."""
    stored = str(stored or "")
    if "$" in stored:
        salt, _, digest = stored.partition("$")
        calc = hashlib.sha256(f"{salt}:{api_key}".encode()).hexdigest()
        return secrets.compare_digest(calc, digest)
    return secrets.compare_digest(hashlib.sha256(api_key.encode("utf-8")).hexdigest(), stored)


def _ensure_table():
    """Ensure users table exists. Accepts cursor (no-op) for backward compat."""
    from src.core.db.db_engine import get_engine
    from src.core.db.models import Base, User

    Base.metadata.create_all(get_engine(), tables=[User.__table__])


def _ensure_rotation_columns():
    """Migrate users table in-place: tambah kolom rotasi bila belum ada.

    create_all() tidak menambah kolom pada tabel yang sudah ada, jadi untuk
    instalasi lama kolom ditambahkan lewat ALTER TABLE. dijalankan sekali per
    proses (thread-safe); kegagalan tidak ditelan diam-diam — logo via logging.
    """
    global _columns_ensured
    if _columns_ensured:
        return
    with _columns_lock:
        if _columns_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine

            engine = get_engine()
            cols = {c["name"] for c in inspect(engine).get_columns("users")}
            missing = [n for n in _ROTATION_COLUMNS if n not in cols]
            if missing:
                with engine.begin() as conn:
                    for name in missing:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {_ROTATION_COLUMNS[name]}"))
        except Exception:
            # Kolom belum ada → query berikutnya akan gagal dengan error eksplisit,
            # bukan dicegat. Catat supaya tidak retry tiap request.
            logging.getLogger(__name__).exception("Gagal migrasi kolom rotasi di tabel users")
        finally:
            _columns_ensured = True


_user_config_tables_ensured = False
_user_config_tables_lock = threading.Lock()


def _ensure_user_config_tables():
    """Buat tabel user_llm_configs, user_skill_overrides, user_mcp_overrides bila belum ada.

    Juga migrate data dari kolom lama (llm_api_key/llm_model/llm_temperature di tabel users)
    ke tabel user_llm_configs, lalu drop kolom lama.
    """
    global _user_config_tables_ensured
    if _user_config_tables_ensured:
        return
    with _user_config_tables_lock:
        if _user_config_tables_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine
            from src.core.db.models import Base, UserLLMConfig, UserMCPOverride, UserSkillOverride

            engine = get_engine()
            Base.metadata.create_all(
                engine,
                tables=[UserLLMConfig.__table__, UserSkillOverride.__table__, UserMCPOverride.__table__],
            )

            # Auto-migrate old columns: llm_api_key, llm_model, llm_temperature
            insp = inspect(engine)
            cols = {c["name"] for c in insp.get_columns("users")}
            old_cols = ["llm_api_key", "llm_model", "llm_temperature"]
            has_old = [c for c in old_cols if c in cols]

            if has_old:
                logger_migrate = logging.getLogger(__name__)
                logger_migrate.info("Migrasi kolom lama users → user_llm_configs: %s", has_old)

                with engine.begin() as conn:
                    # Read data dari kolom lama
                    rows = conn.execute(
                        text(
                            "SELECT id, llm_api_key, llm_model, llm_temperature FROM users WHERE llm_api_key IS NOT NULL OR llm_model IS NOT NULL"
                        )
                    ).fetchall()

                    for row in rows:
                        uid = str(row[0])
                        api_key = row[1]
                        model = row[2]
                        temperature = row[3]

                        # Skip jika sudah ada config
                        existing = conn.execute(
                            text("SELECT 1 FROM user_llm_configs WHERE user_id = :uid LIMIT 1"),
                            {"uid": uid},
                        ).fetchone()
                        if existing:
                            continue

                        # Insert ke junction table
                        import uuid

                        cfg_id = str(uuid.uuid4())
                        # Deteksi provider dari model name
                        provider = "unknown"
                        model_lower = (model or "").lower()
                        if "gemini" in model_lower:
                            provider = "google"
                        elif "gpt" in model_lower or "o1" in model_lower:
                            provider = "openai"
                        elif "claude" in model_lower:
                            provider = "anthropic"
                        elif "llama" in model_lower:
                            provider = "groq"
                        elif "deepseek" in model_lower:
                            provider = "deepseek"
                        elif "grok" in model_lower:
                            provider = "grok"

                        conn.execute(
                            text(
                                "INSERT INTO user_llm_configs (id, user_id, provider, model, api_key, temperature, is_default, is_public, created_at) "
                                "VALUES (:id, :uid, :provider, :model, :api_key, :temperature, true, false, NOW())"
                            ),
                            {
                                "id": cfg_id,
                                "uid": uid,
                                "provider": provider,
                                "model": model or "",
                                "api_key": api_key,
                                "temperature": float(temperature) if temperature else None,
                            },
                        )
                        logger_migrate.info("Migrated LLM config untuk user %s → %s:%s", uid, provider, model)

                    # Drop kolom lama
                    for col_name in has_old:
                        conn.execute(text(f"ALTER TABLE users DROP COLUMN {col_name}"))
                        logger_migrate.info("Drop kolom users.%s", col_name)

            # Auto-migrate fallback_config_ids column
            cols_cfg = {c["name"] for c in insp.get_columns("user_llm_configs")}
            if "fallback_config_ids" not in cols_cfg:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE user_llm_configs ADD COLUMN fallback_config_ids TEXT"))
                logging.getLogger(__name__).info("Added fallback_config_ids ke user_llm_configs")

        except Exception:
            logging.getLogger(__name__).exception("Gagal migrasi tabel user config")
        finally:
            _user_config_tables_ensured = True


def _ensure_vip_columns():
    """Tambah kolom VIP di users bila belum ada + fix constraint + migrate legacy admin→vip."""
    global _vip_columns_ensured
    if _vip_columns_ensured:
        return
    with _columns_lock:
        if _vip_columns_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine

            engine = get_engine()
            cols = {c["name"] for c in inspect(engine).get_columns("users")}
            missing = [n for n in _VIP_COLUMNS if n not in cols]
            if missing:
                with engine.begin() as conn:
                    for name in missing:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {_VIP_COLUMNS[name]}"))
            # Fix constraint users_role_check to allow vip (and keep admin for compat)
            try:
                with engine.begin() as conn:
                    # Drop old check if exists and recreate with vip
                    conn.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check"))
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role = ANY (ARRAY['owner'::text, 'vip'::text, 'user'::text, 'admin'::text]))"
                        )
                    )
            except Exception as _e:
                logging.getLogger(__name__).debug("fix role constraint skipped: %s", _e)
            # Migrate legacy role admin → vip
            try:
                with engine.begin() as conn:
                    conn.execute(text("UPDATE users SET role='vip' WHERE role='admin'"))
            except Exception as _e:
                logging.getLogger(__name__).debug("migrate admin→vip skipped: %s", _e)
        except Exception:
            logging.getLogger(__name__).exception("Gagal migrasi kolom VIP di tabel users")
        finally:
            _vip_columns_ensured = True


def _ensure_vip_tables():
    """Buat tabel vip_upgrades bila belum ada + tambah kolom pending|sukses."""
    global _vip_tables_ensured
    if _vip_tables_ensured:
        return
    with _columns_lock:
        if _vip_tables_ensured:
            return
        try:
            from sqlalchemy import inspect, text

            from src.core.db.db_engine import get_engine
            from src.core.db.models import Base, VipUpgrade

            engine = get_engine()
            Base.metadata.create_all(engine, tables=[VipUpgrade.__table__])
            # Lazy add status columns untuk DB lama
            try:
                cols = {c["name"] for c in inspect(engine).get_columns("vip_upgrades")}
                wanted = {
                    "status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
                    "provider": "VARCHAR(50) NOT NULL DEFAULT 'manual'",
                    "raw_payload": "TEXT",
                    "paid_at": "TIMESTAMP",
                    "applied_at": "TIMESTAMP",
                    "updated_at": "TIMESTAMP NOT NULL DEFAULT NOW()",
                }
                for col, ddl in wanted.items():
                    if col not in cols:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE vip_upgrades ADD COLUMN {col} {ddl}"))
                # Backfill: pending existing yang user sudah vip → success
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE vip_upgrades SET status='success', paid_at=COALESCE(paid_at, created_at), updated_at=NOW() WHERE status='pending' AND user_id IN (SELECT id FROM users WHERE role='vip')"
                        )
                    )
                    # Baris success lama pasti sudah memberi hak → tandai applied
                    # (mencegah replay ref lama memberi perpanjangan gratis).
                    conn.execute(
                        text(
                            "UPDATE vip_upgrades SET applied_at=COALESCE(applied_at, paid_at, created_at) WHERE status='success' AND applied_at IS NULL"
                        )
                    )
            except Exception as _e:
                logging.getLogger(__name__).debug("migrasi kolom vip_upgrades skipped: %s", _e)
        except Exception:
            logging.getLogger(__name__).exception("Gagal migrasi tabel vip_upgrades")
        finally:
            _vip_tables_ensured = True


def create_user(name: str, role: str = "user") -> dict:
    """Buat user, return {id, name, api_key (plaintext, tampil SEKALI), prefix, role}."""
    _ensure_rotation_columns()
    _ensure_vip_columns()
    _ensure_vip_tables()
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    name = (name or "").strip()[:100] or "tanpa-nama"
    role = (role or "user").lower()
    # admin deprecated → vip
    if role == "admin":
        role = "vip"
    if role not in _VALID_ROLES:
        raise ValueError("role harus: user, vip, atau owner")
    api_key = f"fr_{secrets.token_hex(16)}"
    uid = str(uuid.uuid4())

    with get_session() as db:
        user = User(
            id=uid,
            name=name,
            key_hash=_hash_key(api_key),
            prefix=api_key[:11],
            role=role,
            active=True,
        )
        db.add(user)
        db.commit()
    return {
        "id": uid,
        "name": name,
        "api_key": api_key,
        "prefix": api_key[:11],
        "role": role,
    }


def verify_key(api_key: str) -> dict | None:
    """Return {id, name, role} bila key valid+aktif, else None.

    Mengakui key lama selama masa tenggang rotasi (old_key_hash/old_prefix/
    old_key_expires_at) sehingga integrasi yang belum di-update tidak terputus.
    """
    if not api_key:
        return None
    _ensure_rotation_columns()
    _ensure_vip_columns()
    _ensure_vip_tables()
    _ensure_user_config_tables()
    from src.core.auth.auth_context import _utcnow
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    # Cari berdasarkan prefix — kolom non-rahasia, mencegah user enumeration via hash.
    key_prefix = api_key[:11] if api_key else ""
    with get_session() as db:
        user = (
            db.query(User)
            .filter(or_(User.prefix == key_prefix, User.old_prefix == key_prefix), User.active.is_(True))
            .first()
        )
        if not user:
            return None
        if user.prefix == key_prefix:
            stored = str(user.key_hash or "")
            valid = _verify_hash(api_key.strip(), stored)
            if valid and "$" not in stored:
                try:
                    user.key_hash = _hash_key(api_key.strip())  # type: ignore[assignment]
                    db.commit()
                except Exception:
                    logging.getLogger(__name__).exception("Gagal upgrade key_hash legacy user=%s", user.id)
        else:
            # Key lama: hanya dalam masa tenggang
            expires: datetime | None = user.old_key_expires_at  # type: ignore[assignment]
            valid = (
                expires is not None
                and _utcnow() < expires
                and _verify_hash(api_key.strip(), str(user.old_key_hash or ""))
            )
        if valid:
            role = str(user.role or "user")
            expires: datetime | None = user.vip_expires_at  # type: ignore[assignment]
            # Masa aktif vip habis → turunkan peran ke user (lazy, fail-closed).
            # Hanya role yang ditulis; vip_since/vip_expires_at/vip_ref dipertahankan
            # sebagai riwayat (tampilan billing & audit).
            if role == "vip" and expires is not None:
                try:
                    expired = expires <= _utcnow()
                except Exception:
                    # timestamp tidak kompatibel (aware/naive campur) → anggap kedaluwarsa
                    expired = True
                if expired:
                    user.role = "user"  # type: ignore[assignment]
                    db.commit()
                    invalidate_user_cache(str(user.id))
                    logging.getLogger(__name__).info("vip expired → user: uid=%s expires=%s", user.id, expires)
                    role = "user"
            return {
                "id": str(user.id),
                "name": user.name,
                "role": role,
                "vip_expires_at": expires,
            }
        return None


def rotate_user_key(uid: str, grace_hours: int | None = None) -> dict | None:
    """Rotasi API key user.

    Key baru langsung aktif; key lama dipertahankan valid selama grace_hours
    (default env API_KEY_ROTATION_GRACE_HOURS, default 24 jam). Key plaintext
    baru dikembalikan SEKALI. Return None bila user tidak ditemukan / non-aktif.
    """
    _ensure_rotation_columns()
    from src.core.auth.auth_context import _utcnow
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    grace = int(grace_hours if grace_hours is not None else os.getenv("API_KEY_ROTATION_GRACE_HOURS", "24"))
    new_key = f"fr_{secrets.token_hex(16)}"
    now = _utcnow()
    with get_session() as db:
        user = db.query(User).filter(User.id == uid).first()
        if not user or not user.active:
            return None
        if user.key_hash:
            user.old_key_hash = user.key_hash  # type: ignore[assignment]
            user.old_prefix = user.prefix  # type: ignore[assignment]
            user.old_key_expires_at = now + timedelta(hours=grace)  # type: ignore[assignment]
        user.key_hash = _hash_key(new_key)  # type: ignore[assignment]
        user.prefix = new_key[:11]  # type: ignore[assignment]
        db.commit()
        invalidate_user_cache(uid)
        valid_until = user.old_key_expires_at
        name, role = user.name, user.role
    try:
        from src.core.auth.audit import append_audit

        append_audit("rotate_user_key", actor="api", details=f"user={uid}")
    except Exception:
        logging.getLogger(__name__).exception("Gagal mencatat audit rotasi key user=%s", uid)
    return {
        "id": uid,
        "name": name,
        "role": role,
        "api_key": new_key,
        "prefix": new_key[:11],
        "old_key_valid_until": valid_until.isoformat() if valid_until else None,
    }


def list_users() -> list:
    _ensure_rotation_columns()
    _ensure_vip_columns()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        users = db.query(User).order_by(User.id).all()
        return [
            {
                "id": u.id,
                "name": u.name,
                "prefix": u.prefix,
                "role": u.role,
                "active": u.active,
                "old_key_valid_until": u.old_key_expires_at.isoformat() if u.old_key_expires_at else None,
                "vip_since": u.vip_since.isoformat() if getattr(u, "vip_since", None) else None,
                "vip_expires_at": u.vip_expires_at.isoformat() if getattr(u, "vip_expires_at", None) else None,
                "vip_ref": getattr(u, "vip_ref", None),
            }
            for u in users
        ]


def get_user_by_id(uid: str) -> dict | None:
    """Ambil user by id dengan vip metadata."""
    _ensure_rotation_columns()
    _ensure_vip_columns()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        u = db.query(User).filter(User.id == uid).first()
        if not u:
            return None
        return {
            "id": u.id,
            "name": u.name,
            "prefix": u.prefix,
            "role": u.role,
            "active": u.active,
            "vip_since": u.vip_since.isoformat() if getattr(u, "vip_since", None) else None,
            "vip_expires_at": u.vip_expires_at.isoformat() if getattr(u, "vip_expires_at", None) else None,
            "vip_ref": getattr(u, "vip_ref", None),
            "vip_amount_cents": getattr(u, "vip_amount_cents", None),
        }


def set_user_vip(
    uid: str, external_ref: str | None = None, amount_cents: int | None = None, days: int = 30
) -> dict | None:
    """Upgrade user → vip. Return dict atau None bila user tidak ditemukan."""
    _ensure_rotation_columns()
    _ensure_vip_columns()
    _ensure_vip_tables()
    from src.core.auth.auth_context import _utcnow
    from src.core.db.db_engine import get_session
    from src.core.db.models import User, VipUpgrade

    with get_session() as db:
        user = db.query(User).filter(User.id == uid).first()
        if not user or not user.active:
            return None
        if user.role == "owner":
            return None  # owner tidak perlu vip
        # Idempotency: external_ref unik. applied_at terisi = ref ini SUDAH pernah
        # memberi hak → replay tidak boleh memberi perpanjangan (juga setelah vip
        # expired / di-demote). Ref baru = pembelian baru → boleh apply/extend.
        now = _utcnow()
        if external_ref:
            exists = db.query(VipUpgrade).filter(VipUpgrade.external_ref == external_ref).first()
            if exists:
                if getattr(exists, "applied_at", None) is not None:
                    return {"id": uid, "role": user.role, "vip_ref": user.vip_ref, "already": True}
                # belum ke-apply (pending→success, atau success dari percobaan yang gagal)
                exists.status = "success"  # type: ignore[assignment]
                exists.paid_at = exists.paid_at or now  # type: ignore[assignment]
                exists.updated_at = now  # type: ignore[assignment]
                exists.applied_at = now  # type: ignore[assignment]
            else:
                db.add(
                    VipUpgrade(
                        id=str(uuid.uuid4()),
                        user_id=uid,
                        external_ref=external_ref,
                        amount_cents=amount_cents or 1387,
                        currency="USD",
                        status="success",
                        paid_at=now,
                        applied_at=now,
                    )
                )
        user.role = "vip"  # type: ignore[assignment]
        user.vip_since = now  # type: ignore[assignment]
        user.vip_ref = external_ref  # type: ignore[assignment]
        user.vip_amount_cents = amount_cents or 1387  # type: ignore[assignment]
        if days:
            try:
                user.vip_expires_at = now + timedelta(days=days)  # type: ignore[assignment]
            except Exception as _e:
                logging.getLogger(__name__).debug("vip_expires set skipped: %s", _e)
        db.commit()
        invalidate_user_cache(uid)
        return {"id": uid, "role": "vip", "vip_since": now.isoformat(), "vip_ref": external_ref}


def demote_user_vip(uid: str) -> dict | None:
    """Downgrade vip → user (owner-only)."""
    _ensure_rotation_columns()
    _ensure_vip_columns()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User

    with get_session() as db:
        user = db.query(User).filter(User.id == uid).first()
        if not user or not user.active:
            return None
        if user.role != "vip":
            return None
        user.role = "user"  # type: ignore[assignment]
        user.vip_since = None  # type: ignore[assignment]
        user.vip_expires_at = None  # type: ignore[assignment]
        user.vip_ref = None  # type: ignore[assignment]
        user.vip_amount_cents = None  # type: ignore[assignment]
        db.commit()
        invalidate_user_cache(uid)
        return {"id": uid, "role": "user"}


def deactivate_user(uid: str) -> bool:
    _ensure_rotation_columns()
    from src.core.db.db_engine import get_session
    from src.core.db.models import User, UserLLMConfig, UserMCPOverride, UserSkillOverride

    with get_session() as db:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            return False
        user.active = False  # type: ignore[assignment]
        db.query(UserLLMConfig).filter(UserLLMConfig.user_id == uid).delete()
        db.query(UserSkillOverride).filter(UserSkillOverride.user_id == uid).delete()
        db.query(UserMCPOverride).filter(UserMCPOverride.user_id == uid).delete()
        db.commit()
        invalidate_user_cache(uid)
        return True


# ── Per-user LLM configs CRUD ─────────────────────────────────────────


def list_user_llm_configs(
    uid: str,
    viewer_uid: str | None = None,
    viewer_role: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list:
    """List LLM config milik user.

    - Owner bisa lihat semua user, api_key dimask.
    - vip/user hanya bisa lihat config sendiri (api_key ditampilkan) atau config public user lain (api_key dimask).
    """
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    is_self = viewer_uid == uid
    is_privileged = viewer_role == "owner"
    limit = min(limit, 100)

    with get_session() as db:
        rows = (
            db.query(UserLLMConfig)
            .filter(UserLLMConfig.user_id == uid)
            .order_by(UserLLMConfig.created_at)
            .offset(offset)
            .limit(limit)
            .all()
        )
        result = []
        for r in rows:
            # Filter: non-privileged, non-self, non-public → skip
            if not is_self and not is_privileged and not r.is_public:
                continue
            entry = {
                "id": r.id,
                "provider": r.provider,
                "model": r.model,
                "temperature": r.temperature,
                "is_default": r.is_default,
                "is_public": r.is_public,
            }
            # API key: tampilkan hanya untuk owner sendiri
            if is_self:
                entry["api_key_set"] = bool(r.api_key)
            else:
                entry["api_key_set"] = "***" if r.api_key else None
            result.append(entry)
        return result


def add_user_llm_config(
    uid: str,
    provider: str,
    model: str,
    api_key: str | None = None,
    temperature: float | None = None,
    is_default: bool = False,
    is_public: bool = False,
) -> dict:
    """Tambah LLM config baru untuk user. Jika is_default=True, unset default lain."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    with get_session() as db:
        if is_default:
            db.query(UserLLMConfig).filter(UserLLMConfig.user_id == uid, UserLLMConfig.is_default.is_(True)).update(
                {"is_default": False}
            )
        cfg_id = str(uuid.uuid4())
        cfg = UserLLMConfig(
            id=cfg_id,
            user_id=uid,
            provider=provider,
            model=model,
            api_key=api_key,
            temperature=temperature,
            is_default=is_default,
            is_public=is_public,
        )
        db.add(cfg)
        db.commit()
        invalidate_user_cache(uid)
        return {"id": cfg_id, "provider": provider, "model": model, "is_default": is_default, "is_public": is_public}


def update_user_llm_config_entry(
    uid: str,
    config_id: str,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    is_default: bool | None = None,
    is_public: bool | None = None,
    fallback_config_ids: str | None = None,
) -> dict | None:
    """Update LLM config user. Return None jika tidak ditemukan."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    with get_session() as db:
        cfg = db.query(UserLLMConfig).filter(UserLLMConfig.id == config_id, UserLLMConfig.user_id == uid).first()
        if not cfg:
            return None
        if api_key is not None:
            cfg.api_key = api_key  # type: ignore[assignment]
        if model is not None:
            cfg.model = model  # type: ignore[assignment]
        if temperature is not None:
            cfg.temperature = temperature  # type: ignore[assignment]
        if is_public is not None:
            cfg.is_public = is_public  # type: ignore[assignment]
        if is_default is not None and is_default:
            db.query(UserLLMConfig).filter(UserLLMConfig.user_id == uid, UserLLMConfig.is_default.is_(True)).update(
                {"is_default": False}
            )
            cfg.is_default = True  # type: ignore[assignment]
        if fallback_config_ids is not None:
            cfg.fallback_config_ids = fallback_config_ids  # type: ignore[assignment]
        db.commit()
        invalidate_user_cache(uid)
        return {
            "id": cfg.id,
            "provider": cfg.provider,
            "model": cfg.model,
            "is_default": cfg.is_default,
            "is_public": cfg.is_public,
            "fallback_config_ids": cfg.fallback_config_ids,
        }


def delete_user_llm_config(uid: str, config_id: str) -> bool:
    """Hapus LLM config user."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    with get_session() as db:
        cfg = db.query(UserLLMConfig).filter(UserLLMConfig.id == config_id, UserLLMConfig.user_id == uid).first()
        if not cfg:
            return False
        db.delete(cfg)
        db.commit()
        invalidate_user_cache(uid)
        return True


def get_user_llm_config_by_id(uid: str, config_id: str) -> dict | None:
    """Ambil LLM config by ID. Return dict atau None."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    with get_session() as db:
        cfg = db.query(UserLLMConfig).filter(UserLLMConfig.id == config_id, UserLLMConfig.user_id == uid).first()
        if not cfg:
            return None
        return {
            "id": cfg.id,
            "user_id": cfg.user_id,
            "provider": cfg.provider,
            "model": cfg.model,
            "api_key": cfg.api_key,
            "temperature": cfg.temperature,
            "is_default": cfg.is_default,
            "is_public": cfg.is_public,
        }


def get_user_default_llm(uid: str) -> dict | None:
    """Ambil default LLM config user. Return {provider, model, api_key, temperature} atau None. Cached 5 min."""
    cached = _cache_get(uid, "llm")
    if cached is not None:
        return cached

    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserLLMConfig

    with get_session() as db:
        cfg = db.query(UserLLMConfig).filter(UserLLMConfig.user_id == uid, UserLLMConfig.is_default.is_(True)).first()
        if not cfg:
            cfg = db.query(UserLLMConfig).filter(UserLLMConfig.user_id == uid).first()
        if not cfg:
            _cache_set(uid, "llm", None)
            return None
        result = {"provider": cfg.provider, "model": cfg.model, "api_key": cfg.api_key, "temperature": cfg.temperature}
        _cache_set(uid, "llm", result)
        return result


# ── Per-user skill overrides CRUD ──────────────────────────────────────


def list_user_skill_overrides(uid: str) -> list:
    cached = _cache_get(uid, "skills")
    if cached is not None:
        return cached

    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserSkillOverride

    with get_session() as db:
        rows = db.query(UserSkillOverride).filter(UserSkillOverride.user_id == uid).all()
        result = [{"id": r.id, "skill_name": r.skill_name, "enabled": r.enabled} for r in rows]
        _cache_set(uid, "skills", result)
        return result


def set_user_skill_override(uid: str, skill_name: str, enabled: bool) -> dict:
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserSkillOverride

    with get_session() as db:
        existing = (
            db.query(UserSkillOverride)
            .filter(UserSkillOverride.user_id == uid, UserSkillOverride.skill_name == skill_name)
            .first()
        )
        if existing:
            existing.enabled = enabled  # type: ignore[assignment]
        else:
            db.add(UserSkillOverride(id=str(uuid.uuid4()), user_id=uid, skill_name=skill_name, enabled=enabled))
        db.commit()
        invalidate_user_cache(uid)
        return {"skill_name": skill_name, "enabled": enabled}


def is_skill_enabled_for_user(uid: str, skill_name: str) -> bool:
    """True bila skill diizinkan user. Default True jika tidak ada override."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserSkillOverride

    with get_session() as db:
        override = (
            db.query(UserSkillOverride)
            .filter(UserSkillOverride.user_id == uid, UserSkillOverride.skill_name == skill_name)
            .first()
        )
        if override is None:
            return True
        return override.enabled


# ── Per-user MCP overrides CRUD ───────────────────────────────────────


def list_user_mcp_overrides(uid: str) -> list:
    cached = _cache_get(uid, "mcp")
    if cached is not None:
        return cached

    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserMCPOverride

    with get_session() as db:
        rows = db.query(UserMCPOverride).filter(UserMCPOverride.user_id == uid).all()
        result = [{"id": r.id, "mcp_name": r.mcp_name, "enabled": r.enabled} for r in rows]
        _cache_set(uid, "mcp", result)
        return result


def set_user_mcp_override(uid: str, mcp_name: str, enabled: bool) -> dict:
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserMCPOverride

    with get_session() as db:
        existing = (
            db.query(UserMCPOverride)
            .filter(UserMCPOverride.user_id == uid, UserMCPOverride.mcp_name == mcp_name)
            .first()
        )
        if existing:
            existing.enabled = enabled  # type: ignore[assignment]
        else:
            db.add(UserMCPOverride(id=str(uuid.uuid4()), user_id=uid, mcp_name=mcp_name, enabled=enabled))
        db.commit()
        invalidate_user_cache(uid)
        return {"mcp_name": mcp_name, "enabled": enabled}


def is_mcp_enabled_for_user(uid: str, mcp_name: str) -> bool:
    """True bila MCP server diizinkan user. Default True jika tidak ada override."""
    _ensure_user_config_tables()
    from src.core.db.db_engine import get_session
    from src.core.db.models import UserMCPOverride

    with get_session() as db:
        override = (
            db.query(UserMCPOverride)
            .filter(UserMCPOverride.user_id == uid, UserMCPOverride.mcp_name == mcp_name)
            .first()
        )
        if override is None:
            return True
        return override.enabled
