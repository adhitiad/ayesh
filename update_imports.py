import os, re

# Mapping of old imports to new imports
import_map = {
    r"from\s+core\.": "from src.core.",
    r"import\s+core\.": "import src.core.",
    r"from\s+plugins\.": "from src.plugins.",
    r"import\s+plugins\.": "import src.plugins.",
    r"from\s+mcp_core\.": "from src.mcp_core.",
    r"import\s+mcp_core\.": "import src.mcp_core.",
    r"from\s+integrations\.": "from src.integrations.",
    r"import\s+integrations\.": "import src.integrations.",
    r"from\s+memory\.": "from src.memory.",
    r"import\s+memory\.": "import src.memory.",
    r"from\s+agents\.": "from src.agents.",
    r"import\s+agents\.": "import src.agents.",
    r"from\s+config\.": "from src.config.",
    r"import\s+config\.": "import src.config.",
}

# Also handle relative imports that might reference parent modules
# But we only update absolute imports from our modules

root_dir = r"E:\code\fr"
exclude_dirs = {
    "venv",
    "__pycache__",
    ".git",
    "build",
    "dist",
    ".venv",
    "env",
    "tests",
    ".kilo",
}

all_files = []
for root, dirs, files in os.walk(root_dir):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for f in files:
        if f.endswith(".py"):
            all_files.append(os.path.join(root, f))

changes = 0
for fpath in all_files:
    try:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        original = content
        for pattern, replacement in import_map.items():
            content = re.sub(pattern, replacement, content)
        if content != original:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            changes += 1
            print(f"Updated: {fpath}")
    except Exception as e:
        print(f"Error {fpath}: {e}")

print(f"\nTotal files updated: {changes}")
