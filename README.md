# MCP Apps

Public source repository for reusable Model Context Protocol applications developed by LifeEnergy EU.

## Repository model

- `apps/` contains product-facing MCP applications.
- `packages/mcp_auth/` owns reusable private OAuth 2.1 + DCR logic.
- `packages/infrastructure_read_policy/` owns the fixed-helper client, the common 14-tool surface and Cloudways fail-closed host read policy.
- `adapters/` contains target-profile contracts; runtime-specific allowlists and all secrets remain outside the public repository.
- Product source is host-neutral; credentials, private keys, passwords, tokens and deployment secrets stay outside this repository.
- Tools are explicit, typed and fail closed.
- Arbitrary shell execution and mutation/deploy tools are forbidden.

## Private Infrastructure Access

### P620 compatibility application
`apps/p620-diagnostics`

P620 keeps its existing direct HTTPS product data path and fixed sudo-mediated host helper. The application now imports the shared OAuth and MCP read-tool packages; P620 host-specific helper/sudoers/service ownership stays in `lifeenergy-eu/p620-ai-runtime`.

### Cloudways application
`apps/cloudways-infrastructure-access`

One reusable Cloudways application supports:
- `CLOUDWAYS_MAGENTO_INFRA_READ_V1`
- `CLOUDWAYS_WORDPRESS_INFRA_READ_V1`

Cloudways executes its fixed helper directly as the existing Cloudways user with no sudo. Exact roots, Git roots, service names and SQLite files are runtime-owned allowlists supplied by the canonical target adapter. Public activation requires target-specific HTTPS 443 and OAuth/MCP acceptance.
