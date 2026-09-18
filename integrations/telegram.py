"""Telegram bot interface untuk agen (aiogram 3.x).

Jalankan:  TELEGRAM_BOT_TOKEN=xxx python -m integrations.telegram
  - Tiap chat_id → session tg_<chat_id>
  - /start → sapaan; /bantuan → daftar; teks lain → route_request
  - Jawaban panjang dipecah per 4000 karakter
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
        return ("Halo! Aku adalah Ayesh, agent AI yang dibuat dengan cinta. "
                "Kirim pertanyaan apa saja — "
                "kode (/koding), riset (/riset-web), surat (/surat-resmi), "
                "atau obrolan biasa. /bantuan untuk daftar lengkap.")
    result = route_request(text, session_for_chat(chat_id))
    return str(result.get("answer", "")) or "(kosong)"


def _allowed_ids() -> set:
    raw = os.getenv("TELEGRAM_ALLOWED_IDS", "").strip()
    if not raw:
        return set()  # kosong = terbuka (default, kompatibel)
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_allowed(chat_id: int | str) -> bool:
    allowed = _allowed_ids()
    return not allowed or str(chat_id) in allowed


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
    bot = Bot(token=token)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
