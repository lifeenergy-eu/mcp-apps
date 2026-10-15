# Direct Server Administration MCP — Netcup → P620 reference and future host-copy runbook

Status: **operational observations / installation reference**, 2026-10-15. This document records what was actually done and verified; it is not authorization to bypass the Project Brain controlled-execution model or a claim that a third host has been installed.

## Purpose and boundary

A **direct server administration MCP** is a separate product from (1) Private Infrastructure Access **read-only** MCP and (2) Project Brain **Controlled Execution**. The direct admin product exposes bounded `run_command`, `write_file`, `create_directory`, `remove_path`, `change_permissions` and diagnostic tools to a specifically authorized operator. It must not be presented as a Brain deployment gateway. Respect the canonical Project Brain authority/activation contracts and do not replace an existing read-only or controlled-execution endpoint with an admin endpoint.

**Working reference: Netcup WordPress MCP**, on the actual Netcup host:
- server: `/opt/netcup-migration-mcp/server.py`
- helper: `/opt/netcup-migration-mcp/root_helper.py`
- executor: `/opt/netcup-migration-mcp/admin_executor.py`
- systemd: `netcup-migration-mcp.service` with `90-permanent.conf` override; `RuntimeMaxSec=infinity`, `Restart=always`, `RestartSec=3`.
- OAuth package observed at `/opt/project-brain/mcp-apps/releases/c6506b90193a2685d9b5dd98607a34c6b3490b82/packages/mcp_auth/private_oauth.py`; the active package path comes from host environment and **must be resolved there rather than assumed**.
- OAuth scope on the reference: `control.execute`; direct tools call the pinned sudo root helper. FastMCP streamable HTTP, localhost bind, DNS-rebinding host/origin rules, OAuth provider with SQLite token persistence.

**P620 WSL Ubuntu instance**, verified after parity change:
- server: `/opt/p620-server-mcp/app/server.py`
- helper: `/opt/p620-server-mcp/root_helper.py`
- executor: `/opt/p620-server-mcp/admin_executor.py`
- virtualenv: `/srv/project-brain/mcp-apps/venv`; Python/MCP SDK reported MCP `1.26.0`.
- service: `project-brain-p620-mcp.service` on `127.0.0.1:8792`
- public MCP resource: `https://p620.taila88a6c.ts.net/mcp`; issuer `https://p620.taila88a6c.ts.net`.
- OAuth DB: `/srv/project-brain/mcp-oauth/oauth.sqlite3` (**never commit, duplicate or print secrets/tokens**).
- systemd parity override: `/etc/systemd/system/project-brain-p620-mcp.service.d/99-netcup-parity.conf`; scope and required scope `control.execute`; permanent restart policy. Source override `90-p620-server-mcp.conf` points to the P620 app.
- `connector_health.target_id=SERVER-P620-WSL`; display name `P620 Server MCP`.
- reported host: `DESKTOP-133GO83`, Ubuntu 26.04.1 LTS on WSL2.

## Root cause and lesson learned

The initial P620 installation mixed the legacy `infra.read` scopes and existing OAuth client tokens with a direct-admin app asserting `control.execute`. Token issuance and OAuth redirect could return success, but `POST /mcp` returned 403/401 and prompted reconnects. Ad-hoc changes then created a dual-scope model and per-tool `require_control_scope()` guard that differed from the successful Netcup reference. The P620 app also mistakenly returned the Netcup `target_id`. **Do not repeat this debugging-by-mutation.**

Final P620 parity aligned the app with the Netcup **single `control.execute` scope**, eliminated the experimental dual-scope/per-tool variant, and corrected P620-specific identity. The confirmed runtime acceptance from ChatGPT after that change:
- `connector_health` **PASS**, correct `SERVER-P620-WSL`;
- `system_info` **PASS** and WSL Ubuntu identified;
- `run_command(argv=['/usr/bin/true'])` **PASS**, exit code 0;
- `write_file`, `remove_path`, `change_permissions` were **not** separately exercised in the final acceptance; do not state otherwise.

During troubleshooting, existing OAuth records for a specific ChatGPT client were manually modified; that was an ad-hoc recovery, **not a standard procedure**. Do not copy token tables, reuse client secrets, hardcode historic client IDs, or silently elevate read-only tokens on future hosts.

## Standard process for future hosts (e.g. Netcup Magento)

1. **Read the actual working Netcup host implementation** and the GitHub canonical source first. Inspect live `server.py`, `root_helper.py`, `admin_executor.py`, effective systemd + overrides, resolved OAuth package, runtime Python/MCP versions and reverse proxy/TLS route. Avoid guessing paths such as `/opt/.../app/server.py`.
2. **Select a fixed known-good source revision** and install a copy of the direct-admin app for the new host; keep the same tool contracts, safety constraints, auth flow, helper protocol, limits, and service restart policy. Prefer a parameterized installer/template rather than hand-editing OAuth code.
3. Change **only host-specific values**: unique MCP `target_id`, display name, hostname/issuer/resource URL, reverse-proxy route, localhost listen port, app/helper/executor paths, virtualenv, systemd unit/user/group/sudo rule, OAuth DB and secret file paths, OS/platform assumptions, and allowed hosts/origins. Confirm service account and sudo boundary on the destination. **No shared credentials or token DB between hosts.**
4. Configure one intentionally selected admin scope (`control.execute`, matching Netcup). The OAuth authorization server must validate issuer, resource audience, scope and approved client/redirect; only authorized clients should receive admin scope. Do not downgrade a read-only MCP endpoint or confuse metadata annotations with authorization.
5. Preflight **before** restart: Python compile/import, assertions, expected effective systemd environment, proxy headers and external HTTPS/OAuth discovery. Perform one controlled restart after passing checks. Do not mutate a live OAuth schema or create overlapping service overrides blindly.
6. Acceptance gate: `connector_health` (unique identity), `system_info`, a non-mutating `run_command` (e.g. `/usr/bin/true`), and where authorized, a **temporary dedicated test directory** write/read/remove round trip. Confirm proper refusals for no token, invalid audience/scope, and attempts outside policy. Record actual results rather than inferred capability.
7. Keep a concise receipt: host identity, source SHA, service name, scope, resource URI, exact tool tests and return codes, date, expected restrictions. Reuse the same runbook for each additional host.

## Common failure diagnosis

- `GET /authorize` 302 and `POST /token` 200 **do not prove** MCP authorization works.
- `POST /mcp` 403 suggests permission/scope mismatch; 401 suggests missing, expired or invalid token/audience. Inspect the effective service environment and OAuth required scope before any code change.
- Distinguish a server-originated `CONTROL_EXECUTE_SCOPE_REQUIRED` from a platform-level tool safety block; they have different causes and no guaranteed one-line workaround.
- `active` systemd status proves process availability, **not** working root execution. Test tool result and return code.
- Update P620 identity from the originally copied `SERVER-NETCUP-WORDPRESS` to `SERVER-P620-WSL`.

## Non-goals / authority

This is documentation for the separately authorized direct-admin connector, **not permission to execute arbitrary Brain deployments**. Consult `lifeenergy-eu/project-brain` canonical policy and the registered action/run capability contracts for Brain deployments. Do not commit live OAuth DBs, passwords, bearer tokens, root secret files or private host-specific environment files to public `mcp-apps`.
