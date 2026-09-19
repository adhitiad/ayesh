import re

with open(
    "tests/security/test_security_regression.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

content = content.replace(
    'patch("core.approval.check_mcp_policy"',
    'patch("src.core.approval.check_mcp_policy"',
)

with open("tests/security/test_security_regression.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
