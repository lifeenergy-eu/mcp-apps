# Netcup Magento Direct Server MCP — first-host bootstrap

**Status:** source for operator-initiated bare-metal bootstrap only. NOT an active connector, NOT a Run Core deploy, NOT an authorization to skip production change governance.

## Identity
- Target: `SERVER-NETCUP-MAGENTO`
- Reference: direct Netcup WordPress `/opt/netcup-migration-mcp/{server.py,root_helper.py,admin_executor.py}` (read-only observed 2026-10-18)
- Source: `lifeenergy-eu/mcp-apps` exact SHA supplied to installer
- Host class: separately provisioned Netcup RS 2000 G12.5, Vienna, Ubuntu 24.04 LTS amd64
- Service: `netcup-magento-mcp.service`
- Application: `/opt/netcup-magento-mcp`
- Account: `projectbrain-mcp-magento`
- Auth: OAuth 2.1/private, `control.execute`, fresh per-server SQLite store and password
- Bind: `127.0.0.1:18793` only
- Intended independent HTTPS: `https://magento-mcp.larimarcode.com/mcp` (ingress NOT installed by this script)
- Auth config: `/etc/project-brain/mcp/netcup-magento.env`; password file in same directory
- Distinct helper: `/usr/bin/python3 -I /opt/netcup-magento-mcp/root_helper.py`, invoked via pinned sudoers rule only by dedicated service user

## Bootstrap
Log into **new Magento Netcup** host over SSH. Do not run on the WordPress host.

```bash
SHA=<exact_commit_sha_from_GitHub>
curl -fsSL "https://raw.githubusercontent.com/lifeenergy-eu/mcp-apps/$SHA/apps/netcup-magento-server-mcp/install.sh" -o /tmp/netcup-magento-mcp-install.sh
sudo bash /tmp/netcup-magento-mcp-install.sh "$SHA"
```

The script independently clones the canonical repository and refuses if the checked-out source SHA differs; it never uses unpinned `main`. There are no transferred WordPress user records or OAuth tokens. No public port is opened by the installer, no SSH/firewall/Tailscale setting is changed.

## Required after local install
1. Verify `systemctl is-active netcup-magento-mcp.service` and `curl` against loopback returns unauthenticated 401. Confirm local helper invocation uid 0 through the smoke check.
2. Provision an independent authenticated HTTPS ingress (scoped Cloudflare Tunnel + DNS, no port 18793 externally).
3. Verify remote metadata, unauthenticated 401, DNS-rebinding defenses and trusted OAuth login/DCR.
4. Add separate ChatGPT plugin pointing to `https://magento-mcp.larimarcode.com/mcp`, sign in using the password kept on **the new server**. Never paste password into chat.
5. Confirm 19 tools/target `SERVER-NETCUP-MAGENTO`, run root read, safe temporary write/read/remove, 401 on invalid audience/scope.
6. Enable Tailscale and test independent login BEFORE tightening public SSH/firewall.
7. Record new server identity, source SHA, live identity/scope, verified tool results and security boundary through official GitHub Direct in the canonical Brain owner. No Magento application release or production cutover is implied.

## Safety
This is a high-trust `control.execute` direct host admin interface. Do not expose it on an unprotected public origin. The current implementation includes arbitrary direct root commands by design, therefore strong OAuth password and private/managed ingress are required. Root source and helper files must remain root-owned and not writable by the service user. Never clone WordPress OAuth SQLite DB, secret files, SSH keys, certificates or external endpoints.
