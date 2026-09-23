"""Plugin Tools (Tangan & Kaki AI) untuk eksekusi aksi nyata di sistem lokal.

Thin re-export layer: implementation moved to submodules for line-count compliance.
jalankan_python uses: sandbox = CodeExecutionSandbox()
"""

from src.plugins.code_tools import (
    CodeExecutionSandbox,
    jalankan_python,
)
from src.plugins.file_ops import (
    buat_folder,
    buka_url,
    download_file,
    hapus_file,
    info_file,
    list_folder,
    rename_file,
    search_folder,
    upload_file,
)
from src.plugins.file_safety import (
    _PROJECT_ROOT,
    _safe_path,
)

# ── Re-export all tools from submodules ───────────────────────────
from src.plugins.file_tools import (
    baca_file,
    info_sistem,
    set_target_dir,
    tulis_kode,
)
from src.plugins.mcp_tools import (
    panggil_mcp,
)
from src.plugins.memory_tools import (
    cari_fakta,
    ingat_fakta,
    lihat_fakta,
)
from src.plugins.office_tool import (
    office_tool,
)
from src.plugins.planning_tools import (
    batal_plan,
    buat_plan,
    cari_plan,
    jalankan_langkah,
    lihat_plan,
    tandai_selesai,
)
from src.plugins.preferences import (
    _pref_user,
    get_preferences_block,
    ingat_preferensi,
    lihat_preferensi,
)
from src.plugins.projects import (
    _proj_user,
    catat_proyek,
    lihat_proyek,
    simpan_proyek,
)
from src.plugins.time_tool import get_current_time
from src.plugins.web_tools import (
    baca_url,
    cari_web,
    learn_keyword,
    minta_review,
)

__all__ = [
    "_PROJECT_ROOT",
    "CodeExecutionSandbox",
    "_pref_user",
    "_proj_user",
    "_safe_path",
    "baca_file",
    "baca_url",
    "batal_plan",
    "buat_folder",
    "buat_plan",
    "buka_url",
    "cari_fakta",
    "cari_plan",
    "cari_web",
    "catat_proyek",
    "download_file",
    "get_current_time",
    "get_preferences_block",
    "hapus_file",
    "info_file",
    "info_sistem",
    "ingat_fakta",
    "ingat_preferensi",
    "jalankan_langkah",
    "jalankan_python",
    "learn_keyword",
    "lihat_fakta",
    "lihat_plan",
    "lihat_preferensi",
    "lihat_proyek",
    "list_folder",
    "minta_review",
    "office_tool",
    "panggil_mcp",
    "rename_file",
    "search_folder",
    "set_target_dir",
    "simpan_proyek",
    "tandai_selesai",
    "tulis_kode",
    "upload_file",
]

# --- Plugin Discovery (otomatis scan src/plugins/) ---
# build_available_plugins() menggabungkan discovery otomatis + manual overrides.
# Tool manual di bawah ini berfungsi sebagai override/pinning bila diperlukan.
try:
    from src.plugins.discovery import build_available_plugins
except Exception as _e:
    import logging

    logging.getLogger(__name__).warning("Plugin discovery gagal, fallback manual: %s", _e)

    def build_available_plugins(manual_overrides=None):
        return manual_overrides or {}


# Manual overrides (bisa kosong). Gunakan untuk pinning versi atau tool non-file.
_MANUAL_PLUGINS: dict = {
    "tulis_kode": tulis_kode,
    "baca_file": baca_file,
    "info_sistem": info_sistem,
    "set_target_dir": set_target_dir,
    "cari_web": cari_web,
    "baca_url": baca_url,
    "jalankan_python": jalankan_python,
    "panggil_mcp": panggil_mcp,
    "learn_keyword": learn_keyword,
    "get_current_time": get_current_time,
    "minta_review": minta_review,
    "ingat_fakta": ingat_fakta,
    "lihat_fakta": lihat_fakta,
    "cari_fakta": cari_fakta,
    "ingat_preferensi": ingat_preferensi,
    "lihat_preferensi": lihat_preferensi,
    "buat_plan": buat_plan,
    "lihat_plan": lihat_plan,
    "cari_plan": cari_plan,
    "jalankan_langkah": jalankan_langkah,
    "tandai_selesai": tandai_selesai,
    "batal_plan": batal_plan,
    "simpan_proyek": simpan_proyek,
    "catat_proyek": catat_proyek,
    "lihat_proyek": lihat_proyek,
    "list_folder": list_folder,
    "buat_folder": buat_folder,
    "hapus_file": hapus_file,
    "rename_file": rename_file,
    "download_file": download_file,
    "upload_file": upload_file,
    "buka_url": buka_url,
    "search_folder": search_folder,
    "info_file": info_file,
    "office_tool": office_tool,
}

AVAILABLE_PLUGINS = build_available_plugins(_MANUAL_PLUGINS)

# --- Tool versioning ---
# Registrasi otomatis ke src.mcp_core.versioning. Bila sebuah tool menerbitkan
# versi baru, naikkan nomornya di _TOOL_VERSIONS di atas: versi lama tetap
# dipanggil via `nama@vN`, referensi tanpa suffix otomatis memakai versi tertinggi.
_TOOL_VERSIONS: dict[str, int] = {}


def _register_plugin_versions() -> None:
    from src.mcp_core import versioning

    for _name, _tool in AVAILABLE_PLUGINS.items():
        versioning.register(_name, _tool, version=_TOOL_VERSIONS.get(_name, 1))


_register_plugin_versions()
