# ChatGPT / plugin readiness

## Product path

`ChatGPT plugin -> HTTPS /mcp -> host MCP service -> fixed read-only host helper`

For P620, Cloudways is not in this product path.

## Current source stage

Version 0.4 adds a provider-neutral OAuth 2.1 **resource-server** mode while preserving the verified bootstrap bearer mode until runtime OAuth is configured.

The server:
- exposes Streamable HTTP on `/mcp`;
- uses SDK-native protected-resource discovery in OAuth mode;
- verifies JWT signature, issuer, audience/resource, expiry and scopes;
- advertises per-tool OAuth security metadata;
- remains read-only with no arbitrary shell or mutation tools.

See `OAUTH.md` for runtime configuration.

## ChatGPT connection

A supported ChatGPT surface can create a plugin from the remote MCP URL, select OAuth authentication, scan the tools and complete user authorization.

The authorization server is external to this repository. Use an established identity provider rather than implementing login/token issuance inside this MCP app.

## Compatibility

The source directory remains `apps/p620-diagnostics` during bootstrap compatibility because the P620 wrapper pins that path. Product identity remains **Private Infrastructure Access**.
