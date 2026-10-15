# Cloudways Magento Server MCP

Standalone direct Server MCP, based on the active P620 and Netcup WordPress 19-tool FastMCP interface. Runs strictly as Cloudways SSH user, **never sudo/root**. Separate from Magento READ and Project Brain controlled-execution MCPs.

## Source
- `server.py`: OAuth 2.1 private FastMCP entrypoint with 19 tools, `control.execute` scope
- `user_helper.py`: bounded subprocess/file operations, no elevation
- Imports trusted existing `packages/mcp_auth` via `MAGENTO_MCP_AUTH_PACKAGES`
- Local bind 127.0.0.1:18794, MCP endpoint `/mcp`. Must be fronted by separately authorized HTTPS/OAuth ingress, not exposed directly publicly.
- Deployment must use approved source/release and target security policy. Do not replace port 8792 READ or 8793 controlled-execution until acceptance.

## Configuration
`MCP_PUBLIC_HOST`, `MAGENTO_MCP_AUTH_PACKAGES`, `MCP_BIND_PORT=18794`, plus existing private OAuth runtime environment as required by `mcp_auth`. Never commit secrets.

## Limitations
- Same 19 named tools as the two working direct MCPs, but filesystem/process access limited by Cloudways account permissions. No root helper, no sudo.
- Raw command tool runs with Cloudways SSH account privileges; enforce transport authorization and production change controls.
- Install as a separate systemd --user service, with independent OAuth resource identity and HTTPS proxy routing. Exact public domain/routing must be confirmed before enabling.

## Acceptance
Syntax compile; OAuth unauthorized 401; valid auth scope `control.execute`; connector_health correct identity; read diagnostics; sandboxed file create/read/hash/mode/remove; failed privilege escalation; safe timeout; no modification of two existing systemd units; exact running source SHA.

## Release control
Standalone Cloudways Magento Direct MCP activation requires independent HMAC V2 source attestation, explicitly registered Run Core authority, preserved 8792/8793 services, and exact-SHA production verification. SSH access alone does not confer release authorization.
