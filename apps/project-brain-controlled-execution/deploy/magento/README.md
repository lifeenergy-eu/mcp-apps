# Magento — Project Brain Controlled Execution MCP SHA deployment

This is the retained operator script for the existing **Cloudways Magento** instance of `apps/project-brain-controlled-execution`. It is not a second deploy orchestrator or a new PM2 service.

## Verified baseline

- PM2 service: `project-brain-controlled-execution-mcp` (run as `master`).
- PM2 executable is resolved from the current PATH and existing NVM installations, including `/home/master/.nvm/versions/node/v22.22.2/bin/pm2`.
- Execute MCP: `127.0.0.1:8793`; separate Read MCP: `127.0.0.1:8792`.
- Existing OAuth process environment and PM2 process binding are preserved.
- The **operator reported** `PASS_PM2_ACTIVATED` for MCP Apps SHA `797c99330e1cbb505fb04fc4889bcd1fec018093` with Brain helper SHA `0f672966f862c6f08e9c208c0c7ff1aaef27ef66`, using a **two-file Git-blob-verified overlay**, not full exact-SHA repository materialization.

## Run on Magento

```bash
bash deploy_mcp_apps_magento_sha.sh <MCP_APPS_SHA> [BRAIN_SHA]
```

For the already verified overlay combination:

```bash
bash deploy_mcp_apps_magento_sha.sh 797c99330e1cbb505fb04fc4889bcd1fec018093 0f672966f862c6f08e9c208c0c7ff1aaef27ef66
```

The second argument defaults to the baseline Brain helper SHA above. **Specify the Brain SHA explicitly when updating both components.** The script does not clone GitHub, ask for user credentials, create deploy keys or install a separate PM2 service.

## Exact-SHA source requirement

A *new* SHA must already be locally materialized in an approved on-host exact-SHA release directory, with the canonical `.pb-source-manifest.json` matching the repository and SHA. The previously verified two-file overlays are accepted **only** for their pinned SHAs and pinned Git blob hashes. If no verified local source exists, the script exits before changing PM2 with `SHA_SOURCE_NOT_LOCALLY_VERIFIED`. Do not infer this tool fetches missing SHAs.

Canonical source ingress owner: `lifeenergy-eu/project-brain:control-plane/source/exact_sha_ingress.py`. Source staging and HMAC V2 source attestation are separate governed prerequisites. The script is an **operator-side PM2 activation step**, not evidence of a complete central Run Core release receipt.

## Safety and result interpretation

1. Preflight verifies one online named PM2 process, correct local ports, OAuth 401/403, readable existing Python/server/helper and bound environment.
2. Checks local source provenance, syntax and Brain deploy compiler before any PM2 mutation.
3. Rebinds only the named Execute MCP process, preserving the existing environment and checking the distinct Read MCP port.
4. Persists PM2 after successful acceptance. If switching fails, attempts to restore the previous PM2 process using existing source files. No extra backup copy is created.
5. `PASS_PM2_ACTIVATED` confirms the local PM2/OAuth/port cutover only. It does **not** prove full source release, authenticated end-to-end `brain_execute` deploy, actual target release, or Brain reconciliation. Those require separate acceptance.

This script is specific to the existing Magento instance and its on-host directory convention. Do not apply it to P620 or WordPress.

Canonical policy: `lifeenergy-eu/project-brain:control-plane/PROJECT_EXECUTION_POLICY.json#execution.commit_and_deploy.final_operating_model_v1`.
