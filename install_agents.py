"""Installer agent lintas OS.

Saat install (Mac / Linux / Windows), user diasumsikan punya folder `.agents`
di home directory (konvensi Cursor / agent lain):
  - Windows : %userprofile%\\.agents  (mis. C:\\Users\\Nama\\.agents)
  - Mac/Linux : ~/.agents

Script ini membaca definisi agent (*.md, format frontmatter ala Claude Code),
menampilkannya sebagai pilihan, lalu menerapkan yang dipilih ke proyek ini
sebagai skill invokable di ayesh/skills/ (dipakai via /nama-skill).

Pakai:
  python install_agents.py            # interaktif: pilih nomor
  python install_agents.py --list     # hanya tampilkan daftar
  python install_agents.py --all      # terapkan semua tanpa tanya
  python install_agents.py --pick 1,3 # terapkan nomor 1 dan 3
  python install_agents.py --dir PATH # override lokasi folder agents
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = PROJECT_ROOT / "ayesh" / "skills"


def agents_home(override: str | None = None) -> Path:
    """Folder .agents lintas OS. Path.home() = %userprofile% di Windows, ~ di Mac/Linux."""
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agents"


def parse_agent_file(path: Path) -> dict:
    """Parse satu file definisi agent. Toleran: tanpa frontmatter pun tetap dibaca."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"name": path.stem, "description": f"(gagal dibaca: {e})", "body": "", "source": str(path)}
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip().lower()] = value.strip()
            body = parts[2].strip()
    name = meta.get("name", path.stem)
    description = meta.get("description", "")
    if not description:
        for line in body.splitlines():
            line = line.strip().lstrip("# ").strip()
            if line:
                description = line[:150]
                break
    return {"name": name, "description": description, "body": body, "source": str(path)}


def scan_agents(home: Path, limit: int = 100) -> list[dict]:
    """Pindai *.md di folder agents (rekursif, dibatasi)."""
    if not home.exists():
        return []
    files = sorted(home.rglob("*.md"))[:limit]
    return [parse_agent_file(p) for p in files]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "skill"


def apply_agent(agent: dict) -> str:
    """Terapkan satu agent sebagai skill ayesh/skills/<slug>.md. Return status."""
    slug = slugify(agent["name"])
    target = SKILLS_DIR / f"{slug}.md"
    if target.exists():
        return f"SKIP (sudah ada): /{slug}"
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\n"
        f"name: {slug}\n"
        f"description: {agent['description']} (dari {agent['source']})\n"
        f"---\n\n"
        f"# Skill: {agent['name']}\n\n"
        f"{agent['body']}\n"
    )
    target.write_text(content, encoding="utf-8")
    return f"OK: /{slug} <- {agent['source']}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install agent dari ~/.agents ke ayesh/skills/")
    parser.add_argument("--list", action="store_true", help="Hanya tampilkan daftar agent")
    parser.add_argument("--all", action="store_true", help="Terapkan semua tanpa konfirmasi")
    parser.add_argument("--pick", default="", help="Nomor pilihan, mis. '1,3'")
    parser.add_argument("--dir", default=None, help="Override folder agents")
    args = parser.parse_args()

    home = agents_home(args.dir)
    print(f"Folder agents: {home}")
    if not home.exists():
        print(f"Folder tidak ditemukan. Buatkan folder tersebut lalu isi file *.md definisi agent, contoh:\n  {home / 'reviewer.md'}")
        return 1

    agents = scan_agents(home)
    if not agents:
        print("Tidak ada file *.md di folder agents.")
        return 1

    print(f"Ditemukan {len(agents)} agent:")
    for i, a in enumerate(agents, 1):
        print(f"  [{i}] {a['name']}: {a['description'][:100]}")

    if args.list:
        return 0

    if args.all:
        chosen = agents
    elif args.pick:
        try:
            idx = [int(x) - 1 for x in args.pick.split(",")]
        except ValueError:
            print("Format --pick salah. Contoh: --pick 1,3")
            return 1
        chosen = [agents[i] for i in idx if 0 <= i < len(agents)]
    else:
        raw = input("Pilih nomor (pisah koma, 'all', atau kosongkan untuk batal): ").strip().lower()
        if not raw:
            print("Dibatalkan.")
            return 0
        if raw == "all":
            chosen = agents
        else:
            try:
                idx = [int(x) - 1 for x in raw.split(",")]
            except ValueError:
                print("Input tidak valid.")
                return 1
            chosen = [agents[i] for i in idx if 0 <= i < len(agents)]

    if not chosen:
        print("Tidak ada yang dipilih.")
        return 0

    print("")
    for a in chosen:
        print(apply_agent(a))
    print("\nSelesai. Skill aktif via /nama-skill. Cek: GET /skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
