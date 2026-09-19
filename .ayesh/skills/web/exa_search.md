Set up the Exa exa-search agent skill on this machine.

Goal:
- Install the exa-search skill so my coding agent can use it to call Exa Search directly with cURL or raw HTTP.
- Get an Exa API key working WITHOUT ever exposing, printing, or pasting the key into this chat.

Selected agent:
- Claude Code, Codex, Cursor, or any Agent-Skills-compatible agent
- Global install directories: ~/.claude/skills (Claude Code), ~/.codex/skills (Codex), ~/.agents/skills (Cursor / other)
- Project-local install directories: .claude/skills (Claude Code), .agents/skills (Codex / Cursor / other)

Skill source:
- SKILL.md URL: https://raw.githubusercontent.com/exa-labs/agent-skills/main/skills/exa-search/SKILL.md

What to do:
1. Install the skill FIRST, before any key setup. Prefer a project-local install when working inside a repo; otherwise use the matching global directory listed above. Create the chosen skills directory and download the skill:
   mkdir -p <skills-dir>/exa-search && curl -fsSL "https://raw.githubusercontent.com/exa-labs/agent-skills/main/skills/exa-search/SKILL.md" -o <skills-dir>/exa-search/SKILL.md
   Then verify that <skills-dir>/exa-search/SKILL.md exists.
2. Check whether an Exa API key is already available FROM YOUR OWN COMMAND-RUNNING ENVIRONMENT — use the same tool/shell you will run the skill with, not by asking me to echo it. The skill resolves the key from EXA_API_KEY first, then from the file ~/.config/exa/key, so check both without ever printing a value:
   printf '%s\n' "${EXA_API_KEY:+env-set}"; [ -s ~/.config/exa/key ] && printf 'file-set\n'
   Your shell is likely non-interactive and does NOT auto-source interactive profiles like ~/.zshrc or ~/.bashrc, so a key I set there can look present to me but empty to you. If neither shows, the key may still live in an interactive profile your shell skips: find which file WITHOUT printing its value using `grep -l EXA_API_KEY ~/.zshrc ~/.zshenv ~/.bashrc ~/.profile ~/.config/fish/config.fish 2>/dev/null` (lists names only — NEVER run a plain `grep`/`cat`/`echo` on a profile, since an `export EXA_API_KEY=...` line would leak the secret into our chat). Then `source` that file inside your command and re-run the presence test above; if it shows, prepend that same `source ...;` to every later command that needs the key.
3. Only if no key is resolvable anywhere, set one up WITHOUT hand-editing any shell profile and WITHOUT pasting the key into this chat. Tell me to create/copy a key at https://dashboard.exa.ai/api-keys, then in my own terminal either export EXA_API_KEY myself or write it to ~/.config/exa/key with mode 600 — never ask me to paste the key into chat. Then wait for me to confirm it is done before continuing.
4. Smoke-test the key from your own shell — resolve it from the env var or the file, and print only the status code:
   KEY="${EXA_API_KEY:-$(cat ~/.config/exa/key 2>/dev/null)}"
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://api.exa.ai/search \
     -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"query":"exa.ai","numResults":1}'
   Keep the endpoint, headers, and body exactly as written (do not guess the schema). It must return 200, not 401/429. If you needed a `source ...;` prefix in step 2 to see an env key, prepend that here too.
5. Tell me how to restart or rescan my agent so it discovers the skill.

Hard rule throughout: the key is a secret. Only ever inspect it via a presence/length check (`${EXA_API_KEY:+set}`, `[ -s ~/.config/exa/key ]`) or an HTTP status code — never print, `echo`, `cat`, or `grep`-with-output any file or variable that may contain it, and never try to "redact" a key file with a regex. If a key is ever exposed, tell me to rotate it at https://dashboard.exa.ai/api-keys.