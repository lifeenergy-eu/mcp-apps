# P620 OAuth WRITE MCP – shared HTTPS 443 path (public transport PASS)

- User explicitly requires port 443 with a different endpoint URL from the existing P620 DEBUG MCP.
- Existing DEBUG: `https://p620.taila88a6c.ts.net/mcp` -> `127.0.0.1:8792`, unchanged.
- Staged WRITE: `https://p620.taila88a6c.ts.net/pb-control-mcp/mcp` -> `127.0.0.1:8793`, private OAuth `control.execute`.
- Separate protected-resource metadata `/.well-known/oauth-protected-resource/pb-control-mcp/mcp` and auth-server metadata `/.well-known/oauth-authorization-server/pb-control-mcp` are explicitly routed to the WRITE backend for OAuth discovery.
- P620 operator wrapper owner: `lifeenergy-eu/p620-ai-runtime`, entrypoint `activate_p620_write_funnel_443.sh`, Windows Tailscale configuration `activate_p620_write_funnel_443.ps1`.
- Existing console at HTTPS 8443 remains tailnet-only. No new HTTPS listener, no direct shell/SQL/mutation authority.
- WRITE backend remains NOT_CONNECTED_FAIL_CLOSED; operator accepted public transport and OAuth discovery PASS on 2026-10-08; backend remains NOT_CONNECTED_FAIL_CLOSED.

## 2026-10-08 live acceptance

- Operator receipt: `P620_WRITE_PUBLIC_MCP=PASS_443`, `WRITE_OAUTH_DISCOVERY=PASS`, `P620_DEBUG_443=PASS_UNCHANGED`, `P620_WRITE_PLUGIN_TRANSPORT=PASS`.
- Exact ChatGPT custom MCP server URL: `https://p620.taila88a6c.ts.net/pb-control-mcp/mcp` (private OAuth `control.execute`).
- Independent P620 read-only diagnostics: `project-brain-p620-controlled-execution-mcp.service` active/enabled PID `1250468` and `127.0.0.1:8793` listening. `project-brain-p620-mcp.service` active/enabled PID `1206702` and `127.0.0.1:8792` listening. Write-only OAuth override references the public issuer and resource URL.
- Separate `https://p620.taila88a6c.ts.net/mcp` DEBUG endpoint remains unchanged. Do not imply full mutation acceptance; canonical write backend is `NOT_CONNECTED`.
- Brain evidence: `evidence/reconciliation/p620-write-mcp-public-443-oauth-acceptance-20261008.json`.
