# MCP Apps

Public source repository for reusable Model Context Protocol applications developed by LifeEnergy EU.

## Repository model

- `apps/` contains product-facing MCP applications.
- Product source is host-neutral. Host-specific deployment, credentials, private hostnames, firewall rules, Tailscale configuration and runtime secrets do **not** belong here.
- Each app must expose explicit typed tools and fail closed by default.
- Arbitrary shell execution is forbidden unless a future app explicitly defines and secures such a capability.
- Remote MCP clients connect directly to the selected host endpoint. A host adapter may expose that endpoint by HTTPS/tunnel without introducing a separate application proxy.

## Apps

### Private Infrastructure Access

Current source path: `apps/p620-diagnostics` (compatibility path during the bootstrap release series).

Reusable authenticated, read-only infrastructure diagnostics MCP server. The product delegates host reads to a fixed external helper supplied by the host adapter; it does not implement filesystem, shell or mutation privileges itself.

First host adapter: `lifeenergy-eu/p620-ai-runtime`.

Current P620 product data path:

`ChatGPT / MCP client -> remote HTTPS /mcp -> P620`

Cloudways is **not** part of this MCP product data path. Project Brain control/deploy and AI-runtime traffic use separate governed infrastructure.

The bootstrap runtime currently uses a static bearer secret. Public/plugin distribution is planned to use OAuth-compatible authentication without changing the read-only host diagnostic tool contract.
