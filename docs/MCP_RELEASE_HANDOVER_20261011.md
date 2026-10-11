# Magento READ + WRITE MCP — execution handover (2026-10-11)

**Do not use historical memory as execution authority.** Start from current `lifeenergy-eu/project-brain/main` and its canonical bootstrap chain, and recheck live host identities.

## Confirmed completed

- WRITE Brain MCP: user executed full exact-source operator bootstrap with
  - Brain execution source: `cbfb2ceb5aac0fc920940d9935952779081aedf0`
  - WRITE MCP Apps source: `741936da7d72f2f503c6f94851aca074e91ffde2`
  - PM2 service: `project-brain-controlled-execution-mcp`, online, observed ID 32.
  - Reported full release, relay activation conformance, HMAC V2, OAuth protected, PM2 saved, READ port 8792 preserved.
  - **Authenticated ChatGPT tools/list and positive brain_execute E2E still NOT verified**; current ChatGPT tool adapter exposed stale `{task,wait_seconds}` schema while runtime expects `{repository,commit_sha}`.
- Magento READ MCP connector health: **PASS**, loopback `127.0.0.1:8792` listening.
  - Observed unique owner PID `2357313`, parent `systemd` PID `2357296`.
  - systemd user service `project-brain-cloudways-mcp-magento.service`, active and enabled, `MainPID=2357313`.
  - unit fragment `/home/master/.config/systemd/user/project-brain-cloudways-mcp-magento.service`; no drop-ins.
  - READ active source:
    `/home/master/.project-brain/cloudways-mcp/magento/releases/lifeenergy-eu__mcp-apps/c42c2dda55808ad7b05b195907418df952fefff6`.
  - **EXECSTART_PINS_OLD_SHA=False, WORKDIR_PINS_OLD_SHA=False, RUNTIME_ENV_PINS_OLD_SHA=True** (operator read-only diagnostic).
  - READ new feature source commit `38d02dd8c9cc03cd45ef1641858825a03f4c18b7` (bounded Cloudways access logs), **NOT DEPLOYED**.
- WordPress READ connector returned internal error in this ChatGPT session; separate host and release required.

## Exact blocker

Existing registered Brain READ action `read_mcp_exact_sha_rollout_v1`:
- `control-plane/server/mcp_read_rollout.py` insists on a PM2 READ entry; host is systemd.
- It atomically copies just **three Python files** to old runtime (partial overlay) rather than activating an attested complete immutable repository release.
- Prior attempts returned `MCP_ROLLOUT_PM2_IDENTITY_UNVERIFIED` with no confirmed READ production mutation.

Therefore **do not invoke the existing READ rollout**, guess a PM2 ID, or execute an unregistered SSH code-replacement script. It violates the complete-source, no-overlays, Run-Core-only contract. Both services must remain separate.

## Sources saved here

- [Main runbook](MAGENTO_MCP_RELEASES.md)
- [READ systemd preflight, SHA parameter](../deploy/magento-read-preflight.sh) (no mutation)
- [WRITE PM2 preflight, two SHA parameters](../deploy/magento-write-preflight.sh) (no mutation)
- [Full WRITE operator bootstrap source, two SHA parameters](../deploy/magento-write-operator-bootstrap.sh) (historical bootstrap/recovery; never routine bypass)
- [Existing local bootstrap wrapper](../deploy/magento-write-bootstrap.sh) (two SHA parameters)

**Read the SHA-attestation warning in the main runbook:** documentation commits are not canonical HMAC V2-attested deployment commits. Do not deploy latest docs HEAD; use signed target source pins, and only advance the source with the registered HMAC V2 mutation mechanism.

## Next executable work (no additional architecture invention)

1. Run immutable read-only systemd preflight with target `38d02dd8c9cc03cd45ef1641858825a03f4c18b7`. Capture only **names**, not values, of SHA-pinning runtime environment variables.
2. Update the registered **Brain** READ release executor to match the unique systemd service, existing private runtime environment binding, full exact-SHA source staging/HMAC V2, atomic release activation/rollback, and 8792 vs 8793 fault-domain separation. Update conformance tests and capability/owner metadata in canonical Brain. Do not add parallel runners.
3. Ensure the sole public `brain_execute(repository,commit_sha)` resolver can deploy the READ consumer of `mcp-apps` without accidentally mutating unrelated runtimes or choosing an unverified target; preserve existing WRITE binding.
4. Activate the updated Brain source through its existing registered lifecycle. Do not confuse source commit or staged manifests with runtime activation.
5. Deploy new READ target via Brain's registered Run Core; verify exact source, systemd unit and new MainPID, OAuth tools/list, bounded log read and negative security checks. Roll back on any failed gate.
6. Verify WRITE connector schema and independent real `brain_execute` E2E. Update Brain CURRENT_STATE only from production evidence.

## Operator one-liner: READ preflight, no upload

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/lifeenergy-eu/mcp-apps/101efcfcebba3f19af0c4365a89580760d8afa91/deploy/magento-read-preflight.sh) 38d02dd8c9cc03cd45ef1641858825a03f4c18b7
```

No SSH deployment script can truthfully claim to be canonical READ deployment while the registered Brain runner still targets PM2/partial updates. Treat `PREFLIGHT_ONLY_NOT_DEPLOYED` accordingly.
