# ChatGPT / plugin readiness

Product path:

`ChatGPT web -> HTTPS /mcp -> P620 MCP service -> fixed read-only P620 helper`

Version 0.6 imports reusable OAuth and read-tool packages from the repository-level `packages/` tree while preserving the P620 host adapter boundary.

The MCP surface:
- exposes Streamable HTTP on `/mcp`;
- supports private OAuth 2.1 authorization code + PKCE S256;
- supports Dynamic Client Registration and refresh tokens;
- advertises the `infra.read` scope;
- exposes exactly the common 14 read-only infrastructure tools;
- exposes no arbitrary shell, mutation or deploy tools.

The P620 deployment wrapper must materialize both `apps/p620-diagnostics` and the required shared packages from the same exact `mcp-apps` SHA.
