import re

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.message) > 50000:
            raise ValueError("message terlalu panjang (maks 50000 karakter)")
        if self.session_id is not None:
            if len(self.session_id) > 128:
                raise ValueError("session_id terlalu panjang (maks 128 karakter)")
            if not re.match(r"^[a-zA-Z0-9_\-]+$", self.session_id):
                raise ValueError("session_id hanya boleh huruf/angka/underscore/hyphen")


class FeedbackRequest(BaseModel):
    session_id: str
    agent_type: str
    rating: int
    comment: str | None = ""
    corrected_agent: str | None = None

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.session_id) > 128:
            raise ValueError("session_id terlalu panjang (maks 128 karakter)")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", self.session_id):
            raise ValueError("session_id hanya boleh huruf/angka/underscore/hyphen")
        if len(self.agent_type) > 50:
            raise ValueError("agent_type terlalu panjang (maks 50 karakter)")
        if not (1 <= self.rating <= 5):
            raise ValueError("rating harus 1-5")
        if self.comment and len(self.comment) > 10000:
            raise ValueError("comment terlalu panjang (maks 10000 karakter)")
        if self.corrected_agent and len(self.corrected_agent) > 50:
            raise ValueError("corrected_agent terlalu panjang")


class TaskRequest(BaseModel):
    message: str
    session_id: str | None = None

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.message) > 50000:
            raise ValueError("message terlalu panjang (maks 50000 karakter)")
        if self.session_id is not None:
            if len(self.session_id) > 128:
                raise ValueError("session_id terlalu panjang (maks 128 karakter)")
            if not re.match(r"^[a-zA-Z0-9_\-]+$", self.session_id):
                raise ValueError("session_id hanya boleh huruf/angka/underscore/hyphen")


class UserRequest(BaseModel):
    name: str
    role: str | None = "user"
    jobs: bool | None = False
    description: str | None = ""

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.name) > 100:
            raise ValueError("name terlalu panjang (maks 100 karakter)")
        if not self.name.strip():
            raise ValueError("name tidak boleh kosong")
        # admin legacy → vip; valid: user, vip, owner
        if self.role == "admin":
            self.role = "vip"  # type: ignore
        if self.role not in (None, "user", "vip", "owner"):
            raise ValueError("role harus: user, vip, atau owner")
        if self.description and len(self.description) > 500:
            raise ValueError("description terlalu panjang (maks 500 karakter termasuk spasi)")


class RegisterRequest(BaseModel):
    name: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.name) > 100:
            raise ValueError("name terlalu panjang (maks 100 karakter)")
        if not self.name.strip():
            raise ValueError("name tidak boleh kosong")
        if not re.match(r"^[a-zA-Z0-9 _\-]+$", self.name.strip()):
            raise ValueError("name hanya boleh huruf/angka/spasi/underscore/hyphen")


class VipUpgradeRequest(BaseModel):
    uid: str | None = None
    user_id: str | None = None
    external_ref: str
    amount_cents: int | None = 1387
    currency: str | None = "USD"

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if not self.external_ref or len(self.external_ref) > 100:
            raise ValueError("external_ref wajib 1-100 karakter")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", self.external_ref):
            raise ValueError("external_ref hanya huruf/angka/underscore/hyphen")
        if self.amount_cents is not None and self.amount_cents < 0:
            raise ValueError("amount_cents tidak boleh negatif")


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""
    username: str | None = None  # opsional (W9a); kosong → auto dari local-part email

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.email) > 255:
            raise ValueError("email terlalu panjang (maks 255 karakter)")
        if len(self.password) > 128:
            raise ValueError("password terlalu panjang (maks 128 karakter)")
        if len(self.name) > 100:
            raise ValueError("name terlalu panjang (maks 100 karakter)")
        if self.username is not None and len(self.username) > 64:
            raise ValueError("username terlalu panjang (maks 64 karakter)")


class AuthLoginRequest(BaseModel):
    email: str = ""  # backward-compat; tanpa "@" → diperlakukan username
    password: str
    identifier: str | None = None  # email ATAU username (W9b); bila ada, menang

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.email) > 255 or len(self.password) > 128:
            raise ValueError("kredensial terlalu panjang")
        if self.identifier is not None and len(self.identifier) > 255:
            raise ValueError("identifier terlalu panjang")


class AuthLogin2FARequest(BaseModel):
    challenge: str
    code: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.challenge) > 200 or len(self.code) > 64:
            raise ValueError("challenge/code terlalu panjang")


class AuthEmailVerifyRequest(BaseModel):
    token: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.token) > 200:
            raise ValueError("token terlalu panjang")


class AuthResendVerifyRequest(BaseModel):
    email: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.email) > 255:
            raise ValueError("email terlalu panjang")


class AuthPasswordResetRequest(BaseModel):
    email: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.email) > 255:
            raise ValueError("email terlalu panjang")


class AuthPasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.token) > 200 or len(self.new_password) > 128:
            raise ValueError("token/password terlalu panjang")


class AuthPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.current_password) > 128 or len(self.new_password) > 128:
            raise ValueError("password terlalu panjang")


class AuthTotpConfirmRequest(BaseModel):
    code: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.code) > 64:
            raise ValueError("code terlalu panjang")


class AuthTotpDisableRequest(BaseModel):
    password: str

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.password) > 128:
            raise ValueError("password terlalu panjang")


class UserLLMConfigRequest(BaseModel):
    provider: str
    model: str
    api_key: str | None = None
    temperature: float | None = None
    is_default: bool | None = False
    is_public: bool | None = False
    fallback_config_ids: list[str] | None = None

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.provider) > 50:
            raise ValueError("provider terlalu panjang (maks 50 karakter)")
        if len(self.model) > 200:
            raise ValueError("model terlalu panjang (maks 200 karakter)")
        if self.temperature is not None and not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature harus 0.0-2.0")


class SkillOverrideRequest(BaseModel):
    skill_name: str
    enabled: bool

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.skill_name) > 100:
            raise ValueError("skill_name terlalu panjang (maks 100 karakter)")


class UserMcpOverrideRequest(BaseModel):
    mcp_name: str
    enabled: bool

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.mcp_name) > 100:
            raise ValueError("mcp_name terlalu panjang (maks 100 karakter)")


class JobRequest(BaseModel):
    name: str
    prompt: str
    interval_detik: int | None = None
    daily_at: str | None = None  # "HH:MM" WIB

    model_config = {"strict": True}

    def model_post_init(self, __context):
        if len(self.name) > 100:
            raise ValueError("name terlalu panjang (maks 100 karakter)")
        if not re.match(r"^[a-zA-Z0-9_\- ]+$", self.name):
            raise ValueError("name hanya boleh huruf/angka/underscore/hyphen/spasi")
        if len(self.prompt) > 50000:
            raise ValueError("prompt terlalu panjang (maks 50000 karakter)")
        if self.interval_detik is not None:
            if self.interval_detik < 60:
                raise ValueError("interval_detik minimal 60 detik")
            if self.interval_detik > 86400:
                raise ValueError("interval_detik maksimal 86400 detik (24 jam)")
        if self.daily_at is not None:
            if not re.match(r"^\d{2}:\d{2}$", self.daily_at):
                raise ValueError("daily_at format harus HH:MM")
            h, m = self.daily_at.split(":")
            if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                raise ValueError("daily_at jam/minute tidak valid")
