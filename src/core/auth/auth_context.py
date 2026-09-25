"""Auth context variables and helpers."""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

current_user: ContextVar[str] = ContextVar("current_user", default="default")
current_user_role: ContextVar[str] = ContextVar("current_user_role", default="user")
_authenticated: ContextVar[bool] = ContextVar("auth_authenticated", default=False)
# Masa aktif vip request berjalan (None = bukan vip / tanpa batas). Dipakai require_vip
# sebagai pemeriksaan kedua (fail-closed) di samping normalisasi role di verify_key.
current_user_vip_expires: ContextVar[datetime | None] = ContextVar("current_user_vip_expires", default=None)


@dataclass
class UserLLMConfig:
    """Konfigurasi LLM per-user. None = pakai global default."""

    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    temperature: float | None = None


current_user_llm_config: ContextVar[UserLLMConfig | None] = ContextVar("current_user_llm_config", default=None)
disabled_skills: ContextVar[set[str]] = ContextVar("disabled_skills", default=frozenset())
disabled_mcp: ContextVar[set[str]] = ContextVar("disabled_mcp", default=frozenset())


def _utcnow() -> datetime:
    """Naive UTC now. Kolom database timestamp tanpa timezone — kunci naive agar
    komparasi Python tidak mencampur aware/naive."""
    return datetime.now(UTC).replace(tzinfo=None)


def is_authenticated() -> bool:
    """True bila request saat ini membawa API key yang valid.

    Digunakan untuk memisahkan pemakai anonim ("default") dari user
    terautentikasi, terutama saat REQUIRE_API_KEY=0.
    """
    return _authenticated.get() and get_current_user() != "default"


def set_current_user(user_id: str) -> None:
    current_user.set(user_id or "default")


def get_current_user() -> str:
    return current_user.get() or "default"


def set_current_user_role(role: str) -> None:
    current_user_role.set(role or "user")


def get_current_user_role() -> str:
    return current_user_role.get() or "user"


def set_current_user_vip_expires(value: datetime | None) -> None:
    current_user_vip_expires.set(value)


def get_current_user_vip_expires() -> datetime | None:
    return current_user_vip_expires.get()


def vip_expires_active() -> bool:
    """True bila masa aktif vip request berjalan belum lewat.

    None (tanpa batas / bukan vip) dianggap aktif — keputusan role tetap di
    require_vip; fungsi ini hanya penjaga kedua agar expired tidak lolos.
    """
    expires = current_user_vip_expires.get()
    if expires is None:
        return True
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        return expires > now
    except Exception:
        # gagal komparasi = masa aktif tidak terbukti → fail-closed
        return False


def get_current_user_id() -> str:
    """Get current authenticated user_id from ContextVar."""
    return get_current_user()


def get_current_user_llm_config() -> UserLLMConfig | None:
    """Ambil config LLM user saat ini. None = pakai global default."""
    return current_user_llm_config.get()


def set_current_user_llm_config(cfg: UserLLMConfig | None) -> None:
    """Set config LLM user untuk request berjalan."""
    current_user_llm_config.set(cfg)


def set_disabled_skills(skills: frozenset[str]) -> None:
    disabled_skills.set(skills)


def get_disabled_skills() -> frozenset[str]:
    return disabled_skills.get()


def set_disabled_mcp(names: frozenset[str]) -> None:
    disabled_mcp.set(names)


def get_disabled_mcp() -> frozenset[str]:
    return disabled_mcp.get()
