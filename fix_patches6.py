import re

with open(
    "tests/test_prompt_structure.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

content = content.replace('"core.auth.verify_key"', '"src.core.auth.verify_key"')

with open("tests/test_prompt_structure.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
