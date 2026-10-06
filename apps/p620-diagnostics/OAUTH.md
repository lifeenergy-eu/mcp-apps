# OAuth 2.1 resource-server configuration

Private Infrastructure Access uses the MCP server as an **OAuth resource server only**. It does not implement login, consent, client registration, or token issuance.

Use an established OAuth/OpenID Connect provider that can satisfy the MCP authorization requirements.

## Runtime modes

### Bootstrap

`MCP_AUTH_MODE=bootstrap_bearer`

Keeps the existing host-local static bearer secret. This is the default until an OAuth provider is configured and accepted.

### OAuth

`MCP_AUTH_MODE=oauth`

Required environment:

- `MCP_OAUTH_ISSUER_URL` — exact authorization-server issuer.
- `MCP_OAUTH_RESOURCE_URL` — canonical HTTPS MCP resource identifier, including the MCP path when that is the registered resource.
- `MCP_OAUTH_JWKS_URL` — provider JWKS endpoint.
- `MCP_OAUTH_SCOPES` — comma-separated scopes; default source convention is `infra.read`.
- `MCP_OAUTH_ALGORITHMS` — optional comma-separated JWT algorithms; default `RS256`.

The server validates JWT signature, issuer, audience/resource, expiration and required scopes. Invalid credentials fail closed.

## MCP / ChatGPT discovery

When OAuth mode is enabled, MCP Python SDK authentication generates RFC 9728 Protected Resource Metadata for the configured resource and returns a `WWW-Authenticate` challenge on unauthenticated MCP requests.

All tools advertise OAuth security metadata, including the back-compat `_meta.securitySchemes` mirror used by clients that still read it there.

The external authorization server must publish standards-compliant OAuth/OIDC discovery, support authorization code + PKCE S256 and a ChatGPT-compatible client registration model such as CIMD or DCR.

## Security boundary

OAuth changes **who may call the MCP tools**. It does not expand what those tools may do.

- read-only helper remains the only host backend;
- no arbitrary shell;
- no mutation tool;
- no token or secret is returned by any tool;
- Cloudways remains outside the MCP product data path.
