# MCP Apps

Public source repository for reusable Model Context Protocol applications developed by LifeEnergy EU.

## Repository model

- `apps/` contains product-facing MCP applications.
- Host-specific deployment, credentials, private hostnames, firewall rules, Tailscale configuration and runtime secrets do **not** belong here.
- Each app must expose explicit typed tools and fail closed by default.
- Arbitrary shell execution is forbidden unless a future app explicitly defines and secures such a capability.

## Apps

### P620 Diagnostics

`apps/p620-diagnostics`

Authenticated, read-only infrastructure diagnostics MCP server. The app delegates host reads to a fixed external helper executable supplied by the host adapter. It does not implement filesystem/shell privileges itself.

Current host adapter: `lifeenergy-eu/p620-ai-runtime`.
