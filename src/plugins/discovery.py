"""Plugin discovery: auto-scan folder plugins/ dan registrasi tool @tool.

Menggantikan / melengkapi AVAILABLE_PLUGINS manual dengan discovery otomatis.
Struktur:
  - src/plugins/*.py (kecuali __pycache__, __init__, discovery.py)
  - Setiap modul diekspor, attribute yang StructuredTool (langchain) dikumpulkan.
  - Nama tool = StructuredTool.name (nama fungsi asli).
  - Jika ada duplikat nama: modul yang ditemukan duluan menang (deterministik via sort nama file).
"""

import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_structured_tool(obj) -> bool:
    """Cek apakah objek adalah StructuredTool (langchain) atau memiliki .name + .func."""
    return hasattr(obj, "name") and hasattr(obj, "func") and callable(getattr(obj, "func", None))


def _load_module(module_name: str, file_path: Path):
    """Import module dari file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        logger.warning("Gagal import plugin %s: %s", file_path, e)
        return None
    return module


def discover_plugins(plugins_dir: str | None = None) -> dict:
    """Scan folder plugins, return dict nama_tool -> StructuredTool.

    Args:
        plugins_dir: Path ke folder plugins. Default: src/plugins/ relatif ke file ini.

    Returns:
        dict[str, StructuredTool]: Tool yang ditemukan.
    """
    base = Path(__file__).resolve().parent if plugins_dir is None else Path(plugins_dir)

    if not base.exists():
        logger.warning("Plugin directory tidak ditemukan: %s", base)
        return {}

    plugins: dict = {}
    # Urutkan file agar deterministik. Skip core_tools.py (caller) untuk hindari circular import.
    py_files = sorted(base.glob("*.py"))

    for py_file in py_files:
        if py_file.name.startswith("__") or py_file.name in ("discovery.py", "core_tools.py"):
            continue
        module_name = f"src.plugins.{py_file.stem}"
        module = _load_module(module_name, py_file)
        if module is None:
            continue
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name)
            if _is_structured_tool(obj):
                # Gunakan nama tool bawaan (obj.name), bukan nama variabel modul
                tool_name = getattr(obj, "name", attr_name)
                if tool_name in plugins:
                    logger.debug("Plugin duplikat dilewati: %s (dari %s)", tool_name, py_file.name)
                else:
                    plugins[tool_name] = obj
                    logger.debug("Plugin ditemukan: %s dari %s", tool_name, py_file.name)

    return plugins


def build_available_plugins(manual_overrides: dict | None = None) -> dict:
    """Bangun AVAILABLE_PLUGINS: discovery + marketplace installed + manual overrides.

    Prioritas (menang di kanan): tool marketplace terpasang < tool bawaan
    < manual_overrides — tool bawaan tidak bisa di-shadow tool marketplace.
    manual_overrides (dict nama->tool) menimpa hasil discovery.
    """
    try:
        from src.plugins.marketplace import load_installed

        installed = load_installed()
    except Exception as e:  # marketplace rusak tidak boleh menjatuhkan app
        logger.warning("Marketplace tools gagal dimuat: %s", e)
        installed = {}
    discovered = discover_plugins()
    installed.update(discovered)
    if manual_overrides:
        installed.update(manual_overrides)
    return installed
