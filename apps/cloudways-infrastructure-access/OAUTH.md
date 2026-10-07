# Cloudways private OAuth

The application uses the shared `packages/mcp_auth` implementation.

Required runtime configuration:
- `MCP_AUTH_MODE=oauth_private`
- `MCP_OAUTH_ISSUER_URL=https://<approved-host>`
- `MCP_OAUTH_RESOURCE_URL=https://<approved-host>/mcp`
- `MCP_OAUTH_DB_PATH=<private writable runtime path>/oauth.sqlite3`
- `MCP_OAUTH_PASSWORD_FILE=<private runtime secret path>`
- `MCP_OAUTH_SCOPES=infra.read`

Optional predefined private client values remain runtime-only:
- `MCP_OAUTH_STATIC_CLIENT_ID_FILE`
- `MCP_OAUTH_STATIC_CLIENT_SECRET_FILE`
- `MCP_OAUTH_STATIC_REDIRECT_URI`

DCR permits HTTPS callback URIs on ChatGPT/OpenAI domains only. Authorization code + PKCE S256, refresh tokens, RFC 9728 protected-resource metadata and SHA-256 token-hash storage are preserved from the P620 implementation.

OAuth authenticates the caller; it does not expand read authority.
