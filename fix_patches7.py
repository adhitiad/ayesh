import re

with open(
    "tests/test_prompt_structure.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

# Fix the monologue patch - change "core.monologue" to "src.core.monologue"
content = content.replace(
    'patch.dict(sys.modules, {"core.monologue": stub})',
    'patch.dict(sys.modules, {"src.core.monologue": stub})',
)

with open("tests/test_prompt_structure.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
