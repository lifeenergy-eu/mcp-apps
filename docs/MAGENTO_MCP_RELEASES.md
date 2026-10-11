# Magento MCPs — canonical release and recovery owner

Status: verified runtime identity, **READ rollout requires Brain Run Core correction**, 2026-10-11.

## Two independent runtimes (do not conflate)

| Runtime | Service | Supervisor | Loopback | Git source |
|---|---|---|---|---|
| Brain WRITE / Execute | `project-brain-controlled-execution-mcp` | PM2 (observed ID 32, **not** a stable deployment key) | 127.0.0.1:8793 | `lifeenergy-eu/mcp-apps` + separate `lifeenergy-eu/project-brain` execution source |
| Cloudways Magento READ | `project-brain-cloudways-mcp-magento.service` | **systemd --user**, not PM2 | 127.0.0.1:8792 | `lifeenergy-eu/mcp-apps` |
| Cloudways WordPress READ | separate WordPress target | independent target runtime | separately verified | `lifeenergy-eu/mcp-apps` |

A successful WRITE deployment does not activate READ, nor vice versa. Avoid hardcoded transient process IDs.

### Evidence from live Magento host

- READ listener: one PID owner, PID `2357313` at observation; parent `systemd`.
- READ systemd unit: `project-brain-cloudways-mcp-magento.service`; `ActiveState=active`, `UnitFileState=enabled`.
- Unit fragment: `/home/master/.config/systemd/user/project-brain-cloudways-mcp-magento.service`.
- READ source root at observation:
  `/home/master/.project-brain/cloudways-mcp/magento/releases/lifeenergy-eu__mcp-apps/c42c2dda55808ad7b05b195907418df952fefff6`.
- Unit ExecStart and WorkingDirectory do **not** directly pin that SHA, but **runtime environment does**. Release activation must handle that environment binding without revealing or replacing OAuth secrets.
- No systemd drop-ins at observation.
- Latest new READ functionality source tested for later rollout:
  `38d02dd8c9cc03cd45ef1641858825a03f4c18b7` (bounded Cloudways application logs; code commit, **not** a deployed release).
- WRITE operator bootstrap evidence:
  Project Brain `cbfb2ceb5aac0fc920940d9935952779081aedf0`, MCP Apps `741936da7d72f2f503c6f94851aca074e91ffde2`; original operator output reported HMAC V2, conformance, PM2, OAuth and 8792 preservation PASS; authenticated `brain_execute` E2E remained pending.

## Deployment authority and exact SHA separation

Brain owns source/target resolution, authorization, the **existing registered Run Core**, source HMAC V2 attestation, validation, execution, rollback, and durable receipts. ChatGPT's public deploy request is only `brain_execute(repository, commit_sha)`. A GitHub commit, a socket listener and a queued run are not verified deployment.

Pin four identities separately:
1. Brain `main` HEAD.
2. Authorized Brain Run Core execution-source SHA.
3. MCP Apps **target commit SHA** (possibly one release used by multiple services).
4. Actual deployed **per-service** SHA from live runtime.

Every release is a **complete verified repository commit**, never three copied Python files, an overlay, on-host hotfix, or a modified prior release tree. Run source tests with `PYTHONDONTWRITEBYTECODE=1` and outside the immutable manifested source when possible; source manifests must reject unexpected files.

### WRITE release

- Supervisor PM2, fixed service name `project-brain-controlled-execution-mcp`.
- Exact source tree for `mcp-apps`; Brain helper is a **second independent exact-SHA** source tree.
- Verify HMAC V2, manifest, source regression, relay activation conformance, PM2 saved entry, loopback 8792 preservation, OAuth protection, authenticated `tools/list` and real `brain_execute` end-to-end result.
- Existing operator bootstrap program was used for a recovery/cutover. **Do not treat it as permanent independent deployment authority.** Its offline provenance is retained separately by the operator.
- Routine production deploy: registered Brain Run Core via public `brain_execute`.

### READ release (Magento)

**Blocker:** existing Brain action `read_mcp_exact_sha_rollout_v1` in `control-plane/server/mcp_read_rollout.py` assumes unique READ **PM2** entry and copies three files into an old source root. Both assumptions contradict the observed **systemd** lifecycle and the complete-source rule. Do not run this old action to activate READ.

Required canonical correction before an authorized READ deploy:
1. Update the registered Brain READ release runner to verify the exact systemd user service and uniquely tie the 8792 listener PID to that unit; preserve the 8793 WRITE runtime.
2. Discover and validate which unit/runtime **environment source-root variables** pin the prior READ SHA. Never print secrets; no arbitrary unit selection or caller-supplied paths.
3. Materialize the **entire** `mcp-apps` source from GitHub at the requested exact SHA with canonical HMAC V2 and complete-source manifest. Keep mutable OAuth state/env external.
4. Verify source tests, unit/environment safety and prior verified release; stage an immutable new release and atomically activate using the **existing registered Brain Run Core**, not a second scheduler or an unregistered operator Bash deployment.
5. Verify new process uniquely owns 8792 under systemd, exact loaded source and `tools/list` plus a bounded log READ, and negative OAuth/path/sensitive-file denials; rollback the preserved unit environment and old release if any gate fails.
6. Preserve all production data, OAuth DB/password, existing unit enablement, unrelated READ targets and WRITE service.
7. Complete durable Run Core result and per-service deployed-SHA reconciliation.

`deploy/magento-read-preflight.sh` provides non-mutating unit/source/port checks with SHA parameters. It intentionally does **not** bypass this registration gate.

### READ WordPress

Separate target; do not assume the Magento systemd unit, credentials, source root, or health state applies. Current connected WordPress READ plugin returned internal tool errors in the Oct 11 session. Separate runtime identity and governed release needed.

## Source attestation and current documentation commits

**Important:** The documentation and operator-preflight commits written on 2026-10-11 were ordinary GitHub documentation commits, **not** HMAC V2-attested deployment commits. Do **not** deploy the documentation HEAD as an application release. The earlier READ feature commit `38d02dd8c9cc03cd45ef1641858825a03f4c18b7` was created with canonical HMAC V2 commit trailers and remains the intended immutable **READ source candidate**, pending registered systemd deployment. For a future release including this documentation, use the registered HMAC V2 atomic source mutation process and independently verify the new commit's attestation.

Available scripts, all SHA-parameterized:

- `deploy/magento-write-operator-bootstrap.sh MCP_APPS_SHA40 BRAIN_SHA40`: preserved full operator bootstrap source, recovery **only**, not a replacement for Run Core.
- `deploy/magento-write-bootstrap.sh MCP_APPS_SHA40 BRAIN_SHA40`: wrapper for an **already locally present** bootstrap, no new runner.
- `deploy/magento-write-preflight.sh MCP_APPS_SHA40 BRAIN_SHA40`: READ-ONLY diagnostics.
- `deploy/magento-read-preflight.sh TARGET_MCP_APPS_SHA40`: READ-ONLY systemd exact PID, port 8792, SHA and environment-key diagnostics. **Not deployment.**

These scripts are deliberately separate; WRITE scripts must never restart the READ unit, and READ preflight must never alter the WRITE PM2 service.

## No-deploy diagnostics

```bash
bash deploy/magento-read-preflight.sh 38d02dd8c9cc03cd45ef1641858825a03f4c18b7
```

For WRITE use `deploy/magento-write-preflight.sh MCP_APPS_SHA40 BRAIN_SHA40`. These diagnose host identity and source availability; they do not mutate production. Executing deployment still requires Brain's registered execution boundary.

## Sources of authority (do not duplicate security policy here)

- `lifeenergy-eu/project-brain/PROJECT_INSTRUCTIONS.md` — ChatGPT bootstrap.
- `control-plane/EXECUTION_CAPABILITY_CONTRACTS.json` — permitted capabilities.
- `control-plane/EXECUTION_TREE.json` — governed execution topology.
- `control-plane/PROJECT_EXECUTION_POLICY.json` — security and deployment authority.
- `control-plane/CURRENT_STATE.json` — verified state only.
- `control-plane/server/mcp_read_rollout.py` — currently **PM2-only, partial** READ runner; must be replaced by registered systemd full-source runner before activation.
- `control-plane/contracts/infrastructure-debug-read-v1.json` — bounded READ security.
