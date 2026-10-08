# P620 DEBUG MCP verified baseline for separate WRITE MCP

Current verified via the **connected P620 private MCP** on 2026-10-08 (no host mutation):

| Dimension | Existing DEBUG (must remain unchanged) |
| --- | --- |
| Remote ingress | `https://p620.taila88a6c.ts.net/mcp` (direct client-to-P620; no Cloudways hop) |
| Transport | HTTPS streamable HTTP on Tailscale Funnel port 443 |
| Backend | `127.0.0.1:8792`, `project-brain-p620-mcp.service` enabled / active |
| Application | `apps/p620-diagnostics` from `lifeenergy-eu/mcp-apps` |
| Exact deployed app SHA | `d4d6f31247924951d734e77de878c8da22aa956b` |
| Wrapper repository | `lifeenergy-eu/p620-ai-runtime` |
| Exact running wrapper HEAD | `011c85851c2c7e39a329c9c1b646ae89f95a85ed` (live MCP `git_read`) |
| Wrapper source manifest | `/srv/project-brain/source/p620-ai-runtime/MCP_APP_SOURCE.json`; source SHA matches live deployment |
| Runtime app | `/srv/project-brain/mcp-apps/releases/d4d6f31247924951d734e77de878c8da22aa956b/p620-diagnostics/server.py` (live file stat PASS) |
| Interpreter | `/srv/project-brain/mcp-apps/venv/bin/python` |
| Authentication | Private OAuth 2.1, authorization-code + PKCE S256, DCR; `infra.read` |
| Host adapter | Fixed `/usr/local/libexec/p620-debug-read`, invoked via `sudo -n` under bounded sudoers policy |
| Tools | 14 typed, read-only tools; no mutation/deploy/SQL write/shell |
| Diagnostics | `connector_health=PASS`, connector version `0.6.0` |
| Service process | `project-brain-p620-mcp.service` running with `10-source.conf` drop-in |
| OAuth ownership | P620 runtime secrets under `/srv/project-brain/secrets/`, database under `/srv/project-brain/mcp-oauth/`; never copy/reuse in WRITE |

## Mirror plan and hard boundaries

1. Reuse the *same product architecture*: exact-SHA materialized `mcp-apps` source, host wrapper in `p620-ai-runtime`, isolated systemd unit + OAuth DB/password + service account confinement, host-fixed adapter, explicit conformance.
2. **Keep DEBUG `8792` and existing public `/mcp` untouched.** WRITE needs separate service and auth state. Source currently available: `apps/project-brain-controlled-execution` in `mcp-apps`.
3. Current canonical Project Brain explicitly forbids direct **inbound P620 control/mutation**; its governed deploy/control path uses existing **outbound** data plane and shared Run Core. Do not expose a P620 WRITE mutation endpoint through Funnel, create a local mutating helper or grant sudo/root simply by cloning DEBUG.
4. Current source has no approved P620 WRITE host adapter or activation acceptance. First execute read-only preflight of the actual live DEBUG systemd, Tailscale ingress, source pin and exact runner/target policy. Bind the P620 WRITE ingress *only* after canonical route/authorization/transport validation; retain `FAIL_CLOSED` prior to that.
5. No Magento server changes, no GitHub PAT on target, no change to DEBUG or production application as part of this evidence step.

## Current result

**DEBUG accepted; P620 WRITE implementation/activation NOT YET VERIFIED.** Read/negative acceptance is not WRITE execution acceptance.
