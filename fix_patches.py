import re

with open(
    "tests/test_prompt_structure.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

content = content.replace(
    'patch("core.auth.set_current_user")', 'patch("src.core.auth.set_current_user")'
)
content = content.replace(
    'patch("core.auth.set_current_user_role")',
    'patch("src.core.auth.set_current_user_role")',
)
content = content.replace(
    'patch("core.auth.get_current_user_role", return_value="owner")',
    'patch("src.core.auth.get_current_user_role", return_value="owner")',
)

with open("tests/test_prompt_structure.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
