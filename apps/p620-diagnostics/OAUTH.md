# Private ChatGPT web OAuth

Version 0.5 keeps the product path direct:

`ChatGPT web -> HTTPS /mcp -> host`

For the P620 host, the public endpoint is exposed only through Tailscale Funnel. Cloudways is not in MCP product traffic.

## Authentication

The MCP process acts as both:
- OAuth 2.1 authorization server for this private single-user deployment; and
- MCP OAuth protected resource server.

It uses authorization-code flow with PKCE S256, DCR, refresh tokens and RFC 9728 protected-resource metadata.

DCR is restricted to HTTPS redirect URIs on ChatGPT/OpenAI domains. Authorization requires the host-local operator password. Access and refresh tokens are random opaque credentials; only SHA-256 token hashes are stored in the runtime SQLite database.

## Runtime-only state

No secret belongs in this repository.

P620 host adapter supplies:
- `MCP_AUTH_MODE=oauth_private`
- `MCP_OAUTH_ISSUER_URL=https://p620.taila88a6c.ts.net:8443`
- `MCP_OAUTH_RESOURCE_URL=https://p620.taila88a6c.ts.net:8443/mcp`
- `MCP_OAUTH_DB_PATH=/srv/project-brain/mcp-oauth/oauth.sqlite3`
- `MCP_OAUTH_PASSWORD_FILE=/srv/project-brain/secrets/p620-mcp-oauth-password`
- `MCP_OAUTH_SCOPES=infra.read`

The operator password is generated/owned by the host adapter and must never be committed or copied into Project Brain.

## Security boundary

OAuth controls who may call tools. It does not expand tool authority. The application remains read-only, delegates host reads to the fixed helper, exposes no arbitrary shell, and contains no mutation tools.
