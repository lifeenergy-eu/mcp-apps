# P620 WRITE MCP — local WSL runtime verified; outbound execution backend not connected

- Exact MCP product: `lifeenergy-eu/mcp-apps@fc254e6f9bf1d9737e4961d5c76808e9ff7e5887` (`apps/project-brain-controlled-execution`).
- Target-owned deployment wrapper: `lifeenergy-eu/p620-ai-runtime@06cedde383fb89fb17fa731f0edaf61db9575775`, `deploy_p620_controlled_mcp.sh`.
- Fixed P620 host adapter: `p620_control_mcp_helper.py` — all writes fail closed and connector health declares backend NOT_CONNECTED.
- Independent unit: `project-brain-p620-controlled-execution-mcp.service`; loopback `127.0.0.1:8793`; isolated OAuth storage.
- Existing P620 `project-brain-p620-mcp.service` remains unchanged: DEBUG OAuth `infra.read` on `127.0.0.1:8792`.
- No public WRITE ingress is deployed; P620 direct inbound mutation is prohibited under current Brain policy.
- **2026-10-08 operator WSL execution:** local install and service acceptance PASS. Independent live P620 DEBUG MCP `service_status`, `socket_list`, `file_stat`, `file_read` and `hash_file` confirm running P620 WRITE service, pinned app source path, separate default-deny helper and DEBUG service healthy. Local unauthorized initialize HTTP 401 observed in operator receipt. Orchestrator-backed registered write remains **NOT_CONNECTED** and was not tested.
- Brain evidence: `evidence/reconciliation/p620-controlled-execution-mcp-staged-deploy-20261008.json`.

- First WSL attempt was blocked by root-owned shared `/srv/project-brain/mcp-apps/releases` (mode 0755); updated wrapper creates only new dedicated WRITE-owned directories with `sudo install -d`, without recursive ownership or DEBUG changes. New runtime execution still pending operator retry.

## Independent post-deploy evidence (2026-10-08)

- WRITE service `project-brain-p620-controlled-execution-mcp.service`: **ACTIVE_RUNNING**, enabled; PID `1244235` at readback.
- WRITE transport: `127.0.0.1:8793` listening. DEBUG transport: `127.0.0.1:8792` listening and healthy.
- WRITE OAuth scope: `control.execute`, separate SQLite and password paths; loopback-only. No public P620 WRITE ingress configured.
- WRITE helper SHA-256: `b3b0536cd5a43e0f4c452142e46f1bceca4720274b1ba4799dd739350c479174`, `uid=1000`, mode `0700`. Contract verified: `P620` target, `NOT_CONNECTED`, `FAIL_CLOSED`, no inbound mutation.
- Deployed product source path: `/srv/project-brain/mcp-apps/releases/fc254e6f9bf1d9737e4961d5c76808e9ff7e5887/apps/project-brain-controlled-execution/server.py`.
- Initial `RTNETLINK` and transient `curl (7)` warnings were nonblocking; final operator acceptance confirmed unauthorized HTTP `401`, and direct read-only MCP verifies running listener.
- Brain receipt: `evidence/reconciliation/p620-controlled-execution-mcp-staged-deploy-20261008.json`.
- **Remaining gate:** existing canonical outbound Run Core adapter binding and a registered end-to-end write execution receipt. Do not claim full WRITE completion.
