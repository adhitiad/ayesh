import json
data = {
  "mcpServers": {
    "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"}},
    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "E:/"], "env": {}},
    "memory": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"], "env": {}},
    "sequential-thinking": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
    "time": {"command": "uvx", "args": ["mcp-server-time"], "env": {}},
    "context7": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.context7.com/mcp"], "env": {"CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"}},
    "better-auth": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.better-auth.com/mcp"], "env": {}},
    "agent-platform-mcp": {"command": "npx", "args": ["-y", "mcp-remote", "https://aiplatform.googleapis.com/mcp/generate"], "env": {}},
    "google-maps-platform-code-assist": {"command": "npx", "args": ["-y", "@googlemaps/code-assist-mcp@0.2.0"], "env": {}},
    "exa": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"], "env": {"EXA_API_KEY": "${EXA_API_KEY}"}},
    "tavily": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.tavily.com/mcp/?tavilyApiKey=${TAVILY_API_KEY}"], "env": {}},
    "firecrawl": {"command": "npx", "args": ["-y", "mcp-remote", "https://mcp.firecrawl.dev/v2/mcp"], "env": {"FIRECRAWL_API_KEY": "fc-551b462a09e34f548f40a1efe0ab580b"}}
  }
}
with open('E:\\code\\fr\\mcp_core\\mcp.json','w',encoding='utf-8') as f:
    json.dump(data,f,indent=2)
