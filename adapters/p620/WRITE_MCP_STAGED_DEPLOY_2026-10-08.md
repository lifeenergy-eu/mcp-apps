# P620 WRITE MCP — source staged; runtime not yet verified

- Exact MCP product: `lifeenergy-eu/mcp-apps@fc254e6f9bf1d9737e4961d5c76808e9ff7e5887` (`apps/project-brain-controlled-execution`).
- Target-owned deployment wrapper: `lifeenergy-eu/p620-ai-runtime@06cedde383fb89fb17fa731f0edaf61db9575775`, `deploy_p620_controlled_mcp.sh`.
- Fixed P620 host adapter: `p620_control_mcp_helper.py` — all writes fail closed and connector health declares backend NOT_CONNECTED.
- Independent unit: `project-brain-p620-controlled-execution-mcp.service`; loopback `127.0.0.1:8793`; isolated OAuth storage.
- Existing P620 `project-brain-p620-mcp.service` remains unchanged: DEBUG OAuth `infra.read` on `127.0.0.1:8792`.
- No public WRITE ingress is deployed; P620 direct inbound mutation is prohibited under current Brain policy.
- User WSL execution and end-to-end orchestrator acceptance are pending. Do not mark LIVE until runtime confirmed.
- Brain evidence: `evidence/reconciliation/p620-controlled-execution-mcp-staged-deploy-20261008.json`.

- First WSL attempt was blocked by root-owned shared `/srv/project-brain/mcp-apps/releases` (mode 0755); updated wrapper creates only new dedicated WRITE-owned directories with `sudo install -d`, without recursive ownership or DEBUG changes. New runtime execution still pending operator retry.
