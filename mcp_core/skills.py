"""Skill loader ala Claude Code: skill adalah file markdown ber-frontmatter yang bisa di-invoke via /nama-skill."""

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "ayesh" / "skills"


def _parse_skill_file(path: Path) -> dict | None:
    """Parse satu file skill. Return None bila bukan skill invokable (tanpa frontmatter name)."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    if "name" not in meta:
        return None
    meta["body"] = parts[2].strip()
    return meta


def list_skills() -> list[dict]:
    """Daftar semua skill invokable: [{name, description}]."""
    if not SKILLS_DIR.exists():
        return []
    skills = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        parsed = _parse_skill_file(path)
        if parsed:
            skills.append({"name": parsed["name"], "description": parsed.get("description", "")})
    return skills


def load_skill(name: str) -> dict | None:
    """Muat satu skill by name. Return {name, description, body} atau None."""
    name = name.strip().lower()
    for path in SKILLS_DIR.glob("*.md") if SKILLS_DIR.exists() else []:
        parsed = _parse_skill_file(path)
        if parsed and parsed["name"].lower() == name:
            return parsed
    return None


def get_skills_block() -> str:
    """Blok '# Skills' untuk system prompt: skill user-invocable + trigger."""
    skills = list_skills()
    if not skills:
        return ""
    lines = ["## Skills (user-invocable)"]
    for s in skills:
        lines.append(f"- /{s['name']}: {s['description']}")
    lines.append("Jika user mengetik /<nama-skill>, ikuti instruksi skill tersebut. Hanya skill terdaftar di atas yang boleh dipakai — jangan mengarang skill lain.")
    return "\n".join(lines)
