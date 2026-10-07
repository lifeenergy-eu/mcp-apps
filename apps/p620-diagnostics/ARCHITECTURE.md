# Private Infrastructure Access architecture

The product is split into reusable MCP packages plus a host-specific adapter boundary.

1. `packages/mcp_auth/` — private OAuth 2.1 authorization/resource server, DCR, PKCE S256, refresh tokens and hashed runtime token storage.
2. `packages/infrastructure_read_policy/` — fixed-helper client and common 14-tool read-only MCP surface.
3. `apps/p620-diagnostics/` — P620 compatibility application and host defaults.
4. `lifeenergy-eu/p620-ai-runtime` — P620-only helper, sudoers, service, Tailscale ingress and runtime secrets.

P620 product data path remains:

`ChatGPT / MCP client -> HTTPS /mcp -> P620 MCP service -> fixed P620 read helper`

Cloudways is not in the P620 product data path.

The P620 compatibility adapter keeps `sudo -n <fixed-helper>` because that is the existing P620 host boundary. Cloudways uses a different no-sudo adapter and does not weaken or replace this P620 rule.

No generic shell, mutation or deploy tool is exposed by the MCP application.
