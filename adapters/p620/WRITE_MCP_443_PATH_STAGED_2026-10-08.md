# P620 OAuth WRITE MCP – shared HTTPS 443 path

- User explicitly requires port 443 with a different endpoint URL from the existing P620 DEBUG MCP.
- Existing DEBUG: `https://p620.taila88a6c.ts.net/mcp` -> `127.0.0.1:8792`, unchanged.
- Staged WRITE: `https://p620.taila88a6c.ts.net/pb-control-mcp/mcp` -> `127.0.0.1:8793`, private OAuth `control.execute`.
- Separate protected-resource metadata `/.well-known/oauth-protected-resource/pb-control-mcp/mcp` and auth-server metadata `/.well-known/oauth-authorization-server/pb-control-mcp` are explicitly routed to the WRITE backend for OAuth discovery.
- P620 operator wrapper owner: `lifeenergy-eu/p620-ai-runtime`, entrypoint `activate_p620_write_funnel_443.sh`, Windows Tailscale configuration `activate_p620_write_funnel_443.ps1`.
- Existing console at HTTPS 8443 remains tailnet-only. No new HTTPS listener, no direct shell/SQL/mutation authority.
- WRITE backend remains NOT_CONNECTED_FAIL_CLOSED; public transport must not be marked live before successful OAuth, public endpoint, and DEBUG non-regression checks.
