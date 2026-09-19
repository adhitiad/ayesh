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
        if self.role not in (None, "user", "admin", "owner"):
            raise ValueError("role harus: user, admin, atau owner")
        if self.description and len(self.description) > 500:
            raise ValueError("description terlalu panjang (maks 500 karakter termasuk spasi)")


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
