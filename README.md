# MCP Apps

Public source repository for reusable Model Context Protocol applications developed by LifeEnergy EU.

## Repository model

- `apps/` contains product-facing MCP applications.
- Product source is host-neutral; host credentials, private hostnames, firewall policy and runtime secrets stay outside this repository.
- Tools are explicit, typed and fail closed.
- Arbitrary shell execution is forbidden unless a future product introduces a separately governed capability.
- Remote MCP clients connect directly to the selected host endpoint.

## Private Infrastructure Access

Current compatibility source path: `apps/p620-diagnostics`.

Authenticated read-only infrastructure diagnostics. Host reads are delegated to a fixed external helper supplied by the host adapter.

First host adapter: `lifeenergy-eu/p620-ai-runtime`.

Product data path:

`ChatGPT / MCP client -> remote HTTPS /mcp -> host`

Cloudways is not part of this MCP product data path.

Version 0.4 provides two auth modes:
- bootstrap static bearer (default until migration);
- OAuth 2.1 resource-server mode backed by an external standards-compliant identity provider.

OAuth changes access control only; it does not weaken the read-only host boundary.
