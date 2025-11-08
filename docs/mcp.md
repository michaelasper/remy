# GitHub MCP Server Integration

Remy’s workspace now ships ready-to-use configuration for the GitHub MCP Server—both the hosted OAuth option and the local Docker variant. These configs let Copilot/Claude/Cursor (or any MCP host) talk to GitHub for repo operations, issues, PRs, etc.

## Remote (OAuth) configuration

- Config file: `.vscode/mcp.remote.json`
- Contents:

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/"
    }
  }
}
```

### Usage
1. Ensure your IDE/host supports remote MCP servers (VS Code ≥1.101, Claude Desktop, Windsurf, Cursor, etc.).
2. Point the host at `.vscode/mcp.remote.json` (VS Code does this automatically; others usually allow importing a config file).
3. When prompted, complete the GitHub OAuth flow. The host handles tokens/refresh.

## Local (Docker + PAT) configuration

- Config file: `.vscode/mcp.local.json`
- Expects Docker running locally plus a GitHub PAT with at least `repo`, `read:org`, and `read:packages` scopes.

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "github_token",
      "description": "GitHub Personal Access Token (PAT) with repo/read:org scopes",
      "password": true
    }
  ],
  "servers": {
    "github": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${input:github_token}"
      }
    }
  }
}
```

### Usage
1. Create a PAT at https://github.com/settings/tokens (classic fine) with the minimum scopes you need.
2. Keep the token in an env var (e.g., `export GITHUB_PAT=...`) or password manager—never commit it.
3. Import `.vscode/mcp.local.json` into your host. When prompted for `github_token`, paste your PAT (or reference the env var if your host supports `${env:VAR}` syntax).
4. The host will launch `ghcr.io/github/github-mcp-server` on demand via Docker and stream MCP traffic over stdio.

## Tips
- Need GitHub Enterprise / ghe.com? Set `GITHUB_HOST` in the config per the upstream README.
- Add additional `inputs` entries if you want multiple PATs or enterprise hosts; the config files are editable.
- VS Code prioritizes `.vscode/mcp.json`; symlink or copy whichever config you want into that filename when switching modes.
