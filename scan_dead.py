import re, os

checks = [
    ("core/models.py", "gen_uuid"),
    ("mcp_core/tool_validator.py", "get_agent_capabilities"),
    ("mcp_core/context_loader.py", ["load_mcp_config", "get_relevant_context"]),
    ("plugins/time_tool.py", "get_current_time"),
    ("core/async_log_handler.py", "emit"),
    ("plugins/input_guard.py", "dispatch"),
    ("core/usage.py", "record_usage"),
    ("core/approval.py", "get_current_owner_user_id"),
]

for fp, funcs in checks:
    if not os.path.exists(fp):
        continue
    content = open(fp, encoding="utf-8", errors="ignore").read()
    if isinstance(funcs, str):
        funcs = [funcs]
    for fn in funcs:
        defs = len(re.findall(r"def " + re.escape(fn) + r"\b", content))
        calls = len(re.findall(r"(?<!\w)" + re.escape(fn) + r"\s*\(", content))
        self_calls = len(re.findall(r"self\." + re.escape(fn) + r"\s*\(", content))
        actual = calls - defs - self_calls
        status = "DEAD" if actual == 0 else f"used({actual})"
        print(f"{fp}: {fn} defs={defs}, calls={calls}, self={self_calls} -> {status}")
