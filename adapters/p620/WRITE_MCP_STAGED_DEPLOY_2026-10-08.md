# P620 WRITE MCP — source staged; runtime not yet verified

- Exact MCP product: `lifeenergy-eu/mcp-apps@fc254e6f9bf1d9737e4961d5c76808e9ff7e5887` (`apps/project-brain-controlled-execution`).
- Target-owned deployment wrapper: `lifeenergy-eu/p620-ai-runtime@f87385d7f56cc2637a261d3db0f5648ffa06ffea`, `deploy_p620_controlled_mcp.sh`.
- Fixed P620 host adapter: `p620_control_mcp_helper.py` — all writes fail closed and connector health declares backend NOT_CONNECTED.
- Independent unit: `project-brain-p620-controlled-execution-mcp.service`; loopback `127.0.0.1:8793`; isolated OAuth storage.
- Existing P620 `project-brain-p620-mcp.service` remains unchanged: DEBUG OAuth `infra.read` on `127.0.0.1:8792`.
- No public WRITE ingress is deployed; P620 direct inbound mutation is prohibited under current Brain policy.
- User WSL execution and end-to-end orchestrator acceptance are pending. Do not mark LIVE until runtime confirmed.
- Brain evidence: `evidence/reconciliation/p620-controlled-execution-mcp-staged-deploy-20261008.json`.
