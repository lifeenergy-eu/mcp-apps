# Private Infrastructure Access architecture

The application is intentionally split into two layers.

1. **Product MCP layer (this repository)** — remote MCP protocol surface, typed read-only tools, authentication boundary and generic helper invocation.
2. **Host adapter layer** — supplied by the deployment target. On the first P620 deployment this is owned by `lifeenergy-eu/p620-ai-runtime`.

## Product data path

The MCP client communicates directly with the host endpoint:

`ChatGPT / MCP client -> HTTPS streamable HTTP /mcp -> host MCP service -> fixed host read helper`

For the P620 deployment, Cloudways is not a proxy, queue, gateway or dependency in this product data path.

The existing Project Brain Cloudways-backed AI runtime data plane remains a **separate control/compute channel**. It continues to own governed Project Brain debug/deploy/AI jobs and does not gain authority over the direct MCP product surface.

## Security boundary

The product layer never receives generic shell authority. Every diagnostic operation maps to one named action implemented by the host helper. The P620 helper owns path allowlists, secret-path denial, output redaction, query limits and fixed command construction.

Runtime secrets, concrete hostnames, Funnel/tunnel configuration, sudoers and systemd units remain outside this public repository.

The bootstrap P620 release uses a static bearer token. A reusable ChatGPT/plugin release must move to OAuth-compatible authorization while preserving the same read-only tool boundary.
