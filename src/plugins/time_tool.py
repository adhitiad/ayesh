import locale
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

# Set Indonesian locale for month/day names
try:
    locale.setlocale(locale.LC_TIME, "id_ID.UTF-8")
except Exception:
    try:
        locale.setlocale(locale.LC_TIME, "Indonesian_Indonesia.1252")
    except Exception:  # noqa: S110
        pass  # fallback to default

WIB = timezone(timedelta(hours=7))

HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID = [
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
]


@tool
def get_current_time(fmt: str = "lengkap") -> str:
    """Dapatkan tanggal dan jam saat ini di zona waktu WIB (GMT+7).

    Args:
        fmt: "lengkap" (default) = "Hari, DD Bulan YYYY HH:MM:SS WIB"
                "pendek" = "DD/MM/YYYY HH:MM"
                "iso" = "YYYY-MM-DDTHH:MM:SS+07:00"
    """
    now = datetime.now(WIB)
    if fmt == "pendek":
        return now.strftime("%d/%m/%Y %H:%M")
    elif fmt == "iso":
        return now.isoformat()

    hari = HARI_ID[now.weekday()]
    bulan = BULAN_ID[now.month - 1]
    return f"{hari}, {now.day:02d} {bulan} {now.year} {now.strftime('%H:%M:%S')} WIB"
