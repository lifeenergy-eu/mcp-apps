# MCP Apps

Public source repository for reusable Model Context Protocol applications developed by LifeEnergy EU.

## Repository model

- `apps/` contains product-facing MCP applications.
- `packages/mcp_auth/` owns reusable private OAuth 2.1 + DCR logic.
- `packages/infrastructure_read_policy/` owns the fixed-helper client, the common 14-tool surface and Cloudways fail-closed host read policy.
- `adapters/` contains target-profile contracts; runtime-specific allowlists and all secrets remain outside the public repository.
- Product source is host-neutral; credentials, private keys, passwords, tokens and deployment secrets stay outside this repository.
- Tools are explicit, typed and fail closed.
- Private Infrastructure Access applications are strictly read-only and expose no mutation or deploy tools.
- Project Brain Controlled Execution is a separate authenticated transport surface. It carries no execution authority and may invoke only registered Project Brain capabilities through the canonical control plane.

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

## Project Brain Controlled Execution

`apps/project-brain-controlled-execution`

This is a separate OAuth-protected MCP transport for typed controlled execution requests. The transport delegates only to the fixed Project Brain helper; capability resolution, target binding, Run Core orchestration, deterministic execution and verification remain owned by `lifeenergy-eu/project-brain`.

Source presence in this repository does not imply runtime activation. Deployment and live acceptance are controlled exclusively by the current Project Brain canonical state and activation gate.
