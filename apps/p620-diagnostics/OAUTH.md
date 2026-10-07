# Private ChatGPT web OAuth

The P620 compatibility application imports the shared `packages/mcp_auth` implementation.

Runtime configuration remains host-owned:
- `MCP_AUTH_MODE=oauth_private`
- `MCP_OAUTH_ISSUER_URL=<P620 public OAuth issuer>`
- `MCP_OAUTH_RESOURCE_URL=<P620 public /mcp resource>`
- `MCP_OAUTH_DB_PATH=/srv/project-brain/mcp-oauth/oauth.sqlite3`
- `MCP_OAUTH_PASSWORD_FILE=/srv/project-brain/secrets/p620-mcp-oauth-password`
- `MCP_OAUTH_SCOPES=infra.read`

P620 compatibility defaults for OAuth database/password/client files are set by `apps/p620-diagnostics/auth.py`. Secret values are never stored in this repository.

The shared implementation preserves authorization code + PKCE S256, DCR restricted to ChatGPT/OpenAI HTTPS callbacks, refresh tokens, RFC 9728 protected-resource metadata, SHA-256 token-hash storage and the optional predefined private client using `client_secret_post`.

OAuth authenticates the caller only. P620 host reads still pass through the fixed P620 helper and its separate sudoers policy.
