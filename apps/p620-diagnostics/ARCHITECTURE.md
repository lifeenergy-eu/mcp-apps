# P620 Diagnostics architecture

The application is intentionally split into two layers.

1. **Product MCP layer (this repository)** — protocol surface, typed tools, bearer gate and generic helper invocation.
2. **Host adapter layer** — supplied by the deployment target. On the P620 this is owned by `lifeenergy-eu/p620-ai-runtime`.

The product layer never receives generic shell authority. Every diagnostic operation maps to one named action implemented by the host helper. The P620 helper additionally owns path allowlists, secret-path denial, output redaction, query limits and fixed command construction.

Runtime secrets, concrete hostnames, Funnel configuration, sudoers and systemd units remain outside this public repository.

A future public/multi-tenant release should replace the bootstrap static bearer token with OAuth 2.1 / MCP-compatible authorization without changing the host diagnostic tool contract.
