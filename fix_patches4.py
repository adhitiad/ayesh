import re

with open(
    "tests/security/test_security_regression.py", "r", encoding="utf-8", errors="ignore"
) as f:
    content = f.read()

# Fix the remaining core.approval.ensure_approved
content = content.replace(
    '"core.approval.ensure_approved"', '"src.core.approval.ensure_approved"'
)

with open("tests/security/test_security_regression.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
