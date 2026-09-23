"""Tool versioning: dukung referensi `nama@vN` untuk kompatibilitas alat.

Satu tool logis boleh punya beberapa versi implementasi. Referensi tanpa suffix
(mis. ``cari_web``) selalu resolve ke versi default (nomor tertinggi terdaftar);
referensi eksplisit ``cari_web@v1`` resolve ke versi 1 bila ada — kalau tidak,
fallback ke default. Dengan begitu caller/konfigurasi lama tidak pernah pecah
saat versi baru di-deploy, dan versi lama tetap bisa dipanggil selama didaftarkan.

Registrasi dilakukan otomatis saat ``src.plugins.core_tools`` diimport (semua
tool memakai ``version=1`` kecuali dideklarasi lebih tinggi). Modul ini tidak
mengimpor proyek lain — aman dipakai dari mana pun tanpa siklus.
"""

import re
import threading

_VERSION_RE = re.compile(r"^(.+?)@v(\d+)$")


def _split(name: str) -> tuple[str, int | None]:
    """Pecah nama menjadi (base, version). Tanpa suffix @vN → version None."""
    name = (name or "").strip()
    m = _VERSION_RE.match(name)
    if m:
        return m.group(1), int(m.group(2))
    return name, None


class _Registry:
    """Thread-safe registry nama tool → {version: objek tool} + default per basis."""

    def __init__(self) -> None:
        self._versions: dict[str, dict[int, object]] = {}
        self._defaults: dict[str, int] = {}
        self._lock = threading.Lock()

    def register(self, name: str, tool: object, version: int = 1) -> None:
        base, _ = _split(name)
        version = int(version)
        if version < 1:
            version = 1
        with self._lock:
            self._versions.setdefault(base, {})[version] = tool
            if version >= self._defaults.get(base, 0):
                self._defaults[base] = version

    def default_version(self, name: str) -> int:
        base, _ = _split(name)
        return self._defaults.get(base, 1)

    def list_versions(self, name: str) -> list[int]:
        base, _ = _split(name)
        return sorted(self._versions.get(base, {}).keys())

    def lookup(self, name: str) -> object | None:
        """Resolve nama/alias → tool. Versi tak dikenal jatuh ke default."""
        base, version = _split(name)
        with self._lock:
            versions = self._versions.get(base, {})
        if not versions:
            return None
        if version is not None and version in versions:
            return versions[version]
        return versions.get(self._defaults.get(base, max(versions)))

    def normalize(self, name: str) -> str:
        base, _ = _split(name)
        return base


_registry = _Registry()


def register(name: str, tool: object, version: int = 1) -> None:
    """Daftarkan tool di bawah nama basis (suffix @vN dibersihkan)."""
    _registry.register(name, tool, version)


def lookup(name: str) -> object | None:
    """Resolve referensi (dengan/tanpa @vN) ke tool. None bila tak dikenal."""
    return _registry.lookup(name)


def supports(name: str) -> bool:
    """Adakah tool terdaftar untuk nama (basis) ini?"""
    return _registry.lookup(name) is not None


def normalize(name: str) -> str:
    """Nama basis kanonik tanpa suffix @vN (untuk log/karantina/agregasi)."""
    return _registry.normalize(name)


def default_version(name: str) -> int:
    """Versi default saat ini untuk nama basis (1 bila belum terdaftar)."""
    return _registry.default_version(name)


def list_versions(name: str) -> list[int]:
    """Versi yang terdaftar untuk nama basis, terurut naik."""
    return _registry.list_versions(name)


def resolve_tool_references(names) -> list[str]:
    """Normalisasi daftar nama tool (boleh dari DB berisi @vN) → nama basis unik."""
    seen: dict[str, None] = {}
    for n in names:
        seen.setdefault(normalize(n), None)
    return sorted(seen)


def tools_from_names(names) -> list:
    """Map nama (boleh @vN) → objek tool versi kanonik. Tool tak dikenal di-skip."""
    out = []
    for n in names:
        tool = lookup(n)
        if tool is not None:
            out.append(tool)
    return out
