"""Marketplace tool: registry lokal + instalasi tool ber-pin hash (fail-closed).

Registry: ``.ayesh/marketplace/index.json`` (ikut git). Tiap entry:
  name, version, description, source (path relatif di dalam root marketplace),
  sha256 (wajib cocok dengan isi file), agents (subset kunci TOOL_CAPABILITIES).

Alur install — gagal di langkah mana pun → DENY + rollback penuh:
  1. validasi nama (regex) + entry registry (hash hex, path tanpa ``..``)
  2. sha256(source) wajib sama dengan registry (deteksi tampering)
  3. modul dimuat: wajib >=1 tool, nama tool valid & tidak menabrak tool
     yang sudah terdaftar (built-in menang)
  4. file ditulis ke ``installed/<name>.py`` + manifest ``installed/<name>.json``
  5. tool didaftarkan ke AVAILABLE_PLUGINS + TOOL_CAPABILITIES (grant admin)
  6. audit hash-chain dicatat; audit gagal → rollback (fail-closed)

API: GET /marketplace (auth), POST /marketplace/{name}/install (admin),
DELETE /marketplace/{name} (admin) — src/api/routes_marketplace.py.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import re
from pathlib import Path

from src.mcp_core.tool_validator import TOOL_CAPABILITIES

logger = logging.getLogger(__name__)

# Root marketplace. Tests mem-patch _ROOT (dibaca saat runtime, bukan default arg).
_ROOT = Path(__file__).resolve().parents[2] / ".ayesh" / "marketplace"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class MarketplaceError(Exception):
    """Error marketplace; ``status`` dipakai route sebagai HTTP status."""

    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code


def _registry_path() -> Path:
    return _ROOT / "index.json"


def _install_dir() -> Path:
    return _ROOT / "installed"


def _installed_py(name: str) -> Path:
    return _install_dir() / f"{name}.py"


def _manifest_path(name: str) -> Path:
    return _install_dir() / f"{name}.json"


def _get_plugins() -> dict:
    """Lazy akses AVAILABLE_PLUGINS (di-patch saat test)."""
    from src.plugins.core_tools import AVAILABLE_PLUGINS

    return AVAILABLE_PLUGINS


def _audit(action: str, actor: str, details: dict) -> None:
    """Catat audit hash-chain; gagal → lempar (caller wajib rollback)."""
    from src.core.auth.audit import append_audit

    append_audit(action, actor=actor or "system", details=details)


def _safe_source(source: str) -> Path:
    """Resolve source; di luar root marketplace → DENY (anti path traversal)."""
    if not source or Path(source).is_absolute() or ".." in Path(source).parts:
        raise MarketplaceError(400, "PATH_ESCAPE", f"source tidak valid: {source!r}")
    resolved = (_ROOT / source).resolve()
    try:
        resolved.relative_to(_ROOT.resolve())
    except ValueError as e:
        raise MarketplaceError(400, "PATH_ESCAPE", f"source di luar root: {source!r}") from e
    return resolved


def _validate_entry(name: str, entry: object) -> dict | None:
    """Validasi satu entry registry. None = invalid → di-drop (fail-closed)."""
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        logger.warning("Marketplace: nama entry tidak valid: %r", name)
        return None
    if not isinstance(entry, dict):
        return None
    version, source = entry.get("version"), entry.get("source")
    sha, agents = entry.get("sha256"), entry.get("agents")
    if not isinstance(version, str) or not version:
        return None
    if not isinstance(source, str):
        return None
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return None
    if not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents):
        return None
    if any(a not in TOOL_CAPABILITIES for a in agents):
        logger.warning("Marketplace: entry %s memakai agent tak dikenal", name)
        return None
    try:
        _safe_source(source)
    except MarketplaceError:
        logger.warning("Marketplace: source tak aman untuk %s: %r", name, source)
        return None
    return {
        "name": name,
        "version": version,
        "description": str(entry.get("description") or ""),
        "source": source,
        "sha256": sha,
        "agents": list(agents),
    }


def load_registry() -> dict[str, dict]:
    """Baca + validasi registry. File hilang/rusak → {}; entry invalid di-drop."""
    path = _registry_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Marketplace: registry gagal dibaca: %s", e)
        return {}
    tools = raw.get("tools") if isinstance(raw, dict) else None
    if not isinstance(tools, list):
        return {}
    out: dict[str, dict] = {}
    for item in tools:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            entry = _validate_entry(item["name"], item)
            if entry:
                out[entry["name"]] = entry
    return out


def list_marketplace() -> list[dict]:
    """Daftar tool registry + flag installed."""
    reg = load_registry()
    inst_dir = _install_dir()
    installed = {p.stem for p in inst_dir.glob("*.json")} if inst_dir.is_dir() else set()
    out = []
    for name, entry in sorted(reg.items()):
        item = dict(entry)
        item["installed"] = name in installed
        out.append(item)
    return out


def _collect_tools(module) -> dict:
    """Kumpulkan objek tool (punya .name + callable .func) dari module."""
    tools = {}
    for attr in dir(module):
        if attr.startswith("_"):
            continue
        obj = getattr(module, attr)
        if hasattr(obj, "name") and hasattr(obj, "func") and callable(getattr(obj, "func", None)):
            tools[getattr(obj, "name", attr)] = obj
    return tools


def _load_tools(path: Path, strict: bool = True) -> dict:
    """Import modul tool dari file. strict → raise; selain itu drop + warning."""
    spec = importlib.util.spec_from_file_location(f"ayesh_marketplace_{path.stem}", path)
    if spec is None or spec.loader is None:
        if strict:
            raise MarketplaceError(400, "MODULE_INVALID", f"gagal memuat {path.name}")
        logger.warning("Marketplace: spec gagal untuk %s", path)
        return {}
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        if strict:
            raise MarketplaceError(400, "MODULE_INVALID", f"{path.name}: {e}") from e
        logger.warning("Marketplace: modul %s gagal dimuat (dilewati): %s", path, e)
        return {}
    return _collect_tools(module)


def _restore_file(path: Path, prev: bytes | None) -> None:
    """Best-effort rollback satu file (error lain di-log, error asli terus melesat)."""
    try:
        if prev is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(prev)
    except OSError as e:
        logger.error("Marketplace: rollback file gagal %s: %s", path, e)


def install_tool(name: str, actor: str = "") -> dict:
    """Install tool dari registry. Gagal di langkah mana pun → DENY + rollback."""
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise MarketplaceError(400, "BAD_NAME", f"nama tool tidak valid: {name!r}")
    entry = load_registry().get(name)
    if entry is None:
        raise MarketplaceError(404, "NOT_FOUND", f"tool tidak ada di registry: {name}")
    src = _safe_source(entry["source"])
    if not src.is_file():
        raise MarketplaceError(404, "SOURCE_MISSING", f"source tidak ditemukan: {entry['source']}")
    if hashlib.sha256(src.read_bytes()).hexdigest() != entry["sha256"]:
        raise MarketplaceError(409, "HASH_MISMATCH", f"sha256 {name} tidak cocok dengan registry")
    tools = _load_tools(src, strict=True)
    if not tools:
        raise MarketplaceError(400, "NO_TOOLS", f"{name} tidak mendefinisikan tool")
    plugins = _get_plugins()
    for tool_name in tools:
        if not isinstance(tool_name, str) or not _NAME_RE.fullmatch(tool_name):
            raise MarketplaceError(400, "BAD_TOOL_NAME", f"nama tool internal tidak valid: {tool_name!r}")
        if tool_name in plugins:
            raise MarketplaceError(409, "DUPLICATE_TOOL", f"tool sudah terdaftar: {tool_name}")

    dest, manifest = _installed_py(name), _manifest_path(name)
    payload = src.read_bytes()
    manifest_bytes = json.dumps(
        {
            "name": name,
            "version": entry["version"],
            "tools": sorted(tools),
            "agents": entry["agents"],
            "sha256": entry["sha256"],
        },
        indent=2,
    ).encode()
    _install_dir().mkdir(parents=True, exist_ok=True)
    prev_py = dest.read_bytes() if dest.is_file() else None
    prev_manifest = manifest.read_bytes() if manifest.is_file() else None
    try:
        dest.write_bytes(payload)
        manifest.write_bytes(manifest_bytes)
        plugins.update(tools)
        for agent in entry["agents"]:
            TOOL_CAPABILITIES[agent] = set(TOOL_CAPABILITIES[agent]) | set(tools)
        _audit(
            "marketplace.install",
            actor,
            {"tool": name, "version": entry["version"], "sha256": entry["sha256"]},
        )
    except Exception as e:
        _restore_file(dest, prev_py)
        _restore_file(manifest, prev_manifest)
        for tool_name in tools:
            plugins.pop(tool_name, None)
        for agent in entry["agents"]:
            TOOL_CAPABILITIES[agent] = set(TOOL_CAPABILITIES[agent]) - set(tools)
        if isinstance(e, MarketplaceError):
            raise
        raise MarketplaceError(500, "INSTALL_FAILED", str(e)) from e
    logger.info("Marketplace: tool %s terpasang oleh %s", name, actor or "system")
    return {
        "name": name,
        "version": entry["version"],
        "tools": sorted(tools),
        "agents": entry["agents"],
        "installed": True,
    }


def uninstall_tool(name: str, actor: str = "") -> dict:
    """Hapus tool terpasang + cabut grant capabilities (audit; gagal → rollback)."""
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise MarketplaceError(400, "BAD_NAME", f"nama tool tidak valid: {name!r}")
    dest, manifest = _installed_py(name), _manifest_path(name)
    if not dest.is_file() or not manifest.is_file():
        raise MarketplaceError(404, "NOT_INSTALLED", f"tool belum terpasang: {name}")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise MarketplaceError(500, "MANIFEST_CORRUPT", str(e)) from e
    tool_names = [t for t in data.get("tools", []) if isinstance(t, str)]
    agents = [a for a in data.get("agents", []) if a in TOOL_CAPABILITIES]
    py_bytes, manifest_bytes = dest.read_bytes(), manifest.read_bytes()
    plugins = _get_plugins()
    removed_plugins = {t: plugins[t] for t in tool_names if t in plugins}
    try:
        dest.unlink()
        manifest.unlink()
        for tool_name in tool_names:
            plugins.pop(tool_name, None)
        for agent in agents:
            TOOL_CAPABILITIES[agent] = set(TOOL_CAPABILITIES[agent]) - set(tool_names)
        _audit("marketplace.uninstall", actor, {"tool": name, "tools": tool_names})
    except Exception as e:
        _restore_file(dest, py_bytes)
        _restore_file(manifest, manifest_bytes)
        plugins.update(removed_plugins)
        for agent in agents:
            TOOL_CAPABILITIES[agent] = set(TOOL_CAPABILITIES[agent]) | set(tool_names)
        if isinstance(e, MarketplaceError):
            raise
        raise MarketplaceError(500, "UNINSTALL_FAILED", str(e)) from e
    logger.info("Marketplace: tool %s dilepas oleh %s", name, actor or "system")
    return {"name": name, "uninstalled": True, "tools": tool_names}


def load_installed() -> dict:
    """Muat tool terpasang saat startup. Modul rusak → dilewati (tidak di-grant)."""
    out: dict = {}
    inst_dir = _install_dir()
    if not inst_dir.is_dir():
        return out
    for path in sorted(inst_dir.glob("*.py")):
        if path.stem.startswith("__"):
            continue
        out.update(_load_tools(path, strict=False))
    return out
