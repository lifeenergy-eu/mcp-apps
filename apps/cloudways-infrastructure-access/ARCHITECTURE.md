# Cloudways Infrastructure Access

One reusable MCP application serves two fixed Cloudways target profiles.

Data path:

`ChatGPT / MCP client -> HTTPS 443 -> Cloudways ingress -> loopback MCP runtime -> fixed helper -> allowlisted host reads`

The MCP runtime never receives generic command authority. The helper is invoked directly as the existing Cloudways execution user; sudo is not used.

Runtime-owned configuration supplies the exact target identity and allowlists:
- `MCP_TARGET_ID`
- `MCP_PROFILE_ID`
- `MCP_ALLOWED_ROOTS_JSON`
- `MCP_ALLOWED_GIT_ROOTS_JSON`
- `MCP_ALLOWED_SERVICES_JSON`
- `MCP_ALLOWED_SQLITE_PATHS_JSON`

These values are deployment/runtime configuration, not caller arguments. The caller cannot add roots, services or databases.

The public source intentionally contains no credentials, private keys, tokens, passwords, Cloudways master credentials or OAuth secrets.

Activation is separate from source readiness. A target is not canonical until its HTTPS 443 ingress, lifecycle and full OAuth/MCP acceptance suite pass.
