import re

with open(
    "tests/test_prompt_structure.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

# Fix all core.approval patch strings
content = content.replace(
    '"core.approval.ensure_approved"', '"src.core.approval.ensure_approved"'
)
content = content.replace(
    '"core.approval.check_mcp_policy"', '"src.core.approval.check_mcp_policy"'
)

with open("tests/test_prompt_structure.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
