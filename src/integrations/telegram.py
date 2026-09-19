"""Telegram bot interface untuk agen (aiogram 3.x).

Jalankan:  TELEGRAM_BOT_TOKEN=xxx python -m integrations.telegram
  - Tiap chat_id → session tg_<chat_id>
  - /start → sapaan; /bantuan → daftar; teks lain → route_request
  - Jawaban panjang dipecah per 4000 karakter

P1.7 — Fail-closed: TELEGRAM_ALLOWED_IDS is mandatory in production.
Empty allowlist = DENY all messages (not open to everyone).
Set TELEGRAM_DEV=1 to allow empty allowlist (development mode only).
"""

import asyncio
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart

MAX_TG_LEN = 4000


def session_for_chat(chat_id: int | str) -> str:
    return f"tg_{chat_id}"


def split_message(text: str, limit: int = MAX_TG_LEN) -> list:
    """Pecah pesan panjang per baris agar tiap bagian <= limit."""
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > limit and buf:
            parts.append(buf)
            buf = ""
        buf = f"{buf}\n{line}".strip() if buf else line
    if buf:
        parts.append(buf)
    return parts or [""]


def build_reply(text: str, chat_id: int | str) -> str:
    """Bangun teks balasan (tanpa I/O agar testable)."""
    from main import route_request

    text = (text or "").strip()
    if text == "/start":
        return (
            "Halo! Aku adalah Ayesh, agent AI yang dibuat dengan cinta. "
            "Kirim pertanyaan apa saja — "
            "kode (/koding), riset (/riset-web), surat (/surat-resmi), "
            "atau obrolan biasa. /bantuan untuk daftar lengkap."
        )
    result = route_request(text, session_for_chat(chat_id))
    return str(result.get("answer", "")) or "(kosong)"


def _is_dev_mode() -> bool:
    """Check if running in development mode (TELEGRAM_DEV=1)."""
    return os.getenv("TELEGRAM_DEV", "0").strip() == "1"


def _allowed_ids() -> set | None:
    """P1.7 — Fail-closed: empty allowlist = deny all (not open to everyone).

    Returns:
        set of allowed IDs if TELEGRAM_ALLOWED_IDS is set
        None if dev mode (allow all)
        empty set if production and no IDs configured (deny all)
    """
    raw = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
    if not raw:
        if _is_dev_mode():
            return None  # dev mode: None = allow all
        # Production: empty = DENY ALL
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_allowed(chat_id: int | str) -> bool:
    """P1.7 — Fail-closed: empty allowlist = deny all (not open to everyone).

    None = allow all (dev mode), empty set = deny all, otherwise check membership.
    """
    allowed = _allowed_ids()
    if allowed is None:
        return True  # dev mode: allow all
    if not allowed:
        return False  # production: empty = deny all
    return str(chat_id) in allowed


dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    if not is_allowed(message.chat.id):
        await message.answer("Akses ditolak.")
        return
    await message.answer(build_reply("/start", message.chat.id))


@dp.message(Command("bantuan"))
async def bantuan_handler(message: types.Message) -> None:
    if not is_allowed(message.chat.id):
        await message.answer("Akses ditolak.")
        return
    await message.answer(build_reply("/bantuan", message.chat.id))


@dp.message()
async def chat_handler(message: types.Message) -> None:
    if not is_allowed(message.chat.id):
        await message.answer("Akses ditolak.")
        return
    if not message.text:
        await message.answer("Saya hanya bisa memproses pesan teks.")
        return
    chat_id = message.chat.id
    try:
        reply = await asyncio.to_thread(build_reply, message.text, chat_id)
    except Exception as e:
        reply = f"Maaf, terjadi galat: {str(e)[:200]}"
    for part in split_message(reply):
        await message.answer(part)


async def amain() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Isi TELEGRAM_BOT_TOKEN dulu.")
    # P1.7 — Fail-closed: fail startup if no allowed IDs in production
    if not _is_dev_mode() and not os.getenv("TELEGRAM_ALLOWED_IDS", "").strip():
        raise SystemExit(
            "TELEGRAM_ALLOWED_IDS kosong dan bukan mode development. "
            "Set TELEGRAM_ALLOWED_IDS atau TELEGRAM_DEV=1 untuk development."
        )
    if _is_dev_mode():
        import logging

        logging.getLogger(__name__).warning(
            "TELEGRAM_DEV=1 active: ALL chat IDs allowed. Do NOT use in production."
        )
    bot = Bot(token=token)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
