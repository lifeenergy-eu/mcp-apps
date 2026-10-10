#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent.parent / "packages", HERE / "packages"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

os.environ.setdefault("MCP_AUTH_MODE", "oauth_private")

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

VERSION = "0.1.1"
RO = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


HOST = _optional("MCP_BIND_HOST", "127.0.0.1")
PORT = int(_optional("MCP_BIND_PORT", "8793"))
PUBLIC_HOST = _required("MCP_PUBLIC_HOST")
HELPER = _required("PB_CONTROLLED_EXECUTION_HELPER")


class PluginFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        # The Brain MCP exposes exactly one ChatGPT-facing execution tool.
        # Legacy handlers remain defined only to respond to stale tool callers.
        tools = [tool for tool in tools if tool.name == "brain_execute"]
        if AUTH_MODE != "oauth_private":
            return tools
        schemes = [{"type": "oauth2", "scopes": OAUTH_SCOPES}]
        out = []
        for tool in tools:
            meta = dict(tool.meta or {})
            meta["securitySchemes"] = schemes
            out.append(tool.model_copy(update={"meta": meta, "securitySchemes": schemes}))
        return out


security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", f"https://{PUBLIC_HOST}", f"https://{PUBLIC_HOST}:*"],
)

mcp = PluginFastMCP(
    "project-brain-controlled-execution",
    instructions=(
        "Project Brain Controlled Execution. Typed operations only. Execution authority remains in "
        "Project Brain capability contracts, Run Core and existing deterministic executors. "
        "No arbitrary shell, caller-selected runner, target, filesystem root, raw SQL or raw HTTP."
    ),
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=security,
    auth=AUTH_SETTINGS,
    auth_server_provider=AUTH_PROVIDER,
)

if AUTH_MODE == "oauth_private":
    mcp.custom_route("/oauth/login", methods=["GET", "POST"], include_in_schema=False)(oauth_login_handler)


def helper_call(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = {"action": action, "payload": payload or {}}
    proc = subprocess.run(
        ["/usr/bin/python3", HELPER],
        input=json.dumps(request, separators=(",", ":")),
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_EMPTY_RESPONSE")
    try:
        body = json.loads(raw.splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_INVALID_RESPONSE") from exc
    if not isinstance(body, dict):
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_RESPONSE_NOT_OBJECT")
    return body


@mcp.tool(annotations=RO)
def connector_health() -> dict[str, Any]:
    """Return Controlled Execution MCP health and enforced execution posture."""
    body = helper_call("CONNECTOR_HEALTH")
    body["connector_version"] = VERSION
    body["authentication"] = "oauth2-private-single-user"
    body["oauth_scopes"] = OAUTH_SCOPES
    body["mcp_path"] = "/mcp"
    body["primary_execution_tool"] = "brain_execute"
    body["public_execution_tool_count"] = 1
    body["legacy_write_tools"] = "HANDOFF_REQUIRED_USE_BRAIN_EXECUTE"
    body["canonical_deploy_policy_ref"] = "control-plane/PROJECT_EXECUTION_POLICY.json#execution.commit_and_deploy.final_operating_model_v1.canonical_delivery_pipeline_v1"
    return body


def _legacy_handoff(action: str) -> dict[str, Any]:
    """A stale legacy tool call never executes; tell ChatGPT its next action."""
    return {
        "status": "HANDOFF_REQUIRED",
        "code": "USE_BRAIN_EXECUTE",
        "origin_surface": "PROJECT_BRAIN_MCP",
        "blocked_action": action,
        "next_surface": "PROJECT_BRAIN_MCP",
        "next_tool": "brain_execute",
        "required_next_action": "RESUBMIT_REGISTERED_TASK_INTENT",
        "message": "This compatibility tool no longer executes. Use brain_execute with a registered task intent and business inputs.",
        "retry_same_tool": False,
        "execution_performed": False,
        "secrets_emitted": False,
    }


@mcp.tool(annotations=WRITE)
def deploy_registered_source(
    system_id: str,
    source_sha: str,
    repository: str = "",
    paths: list[str] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Deploy one exact SHA through a registered system deployment contract."""
    return _legacy_handoff("DEPLOY_REGISTERED_SOURCE")

@mcp.tool(annotations=WRITE)
def run_registered_application_workflow(
    workflow_id: str,
    operation: dict[str, Any],
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named registered application workflow through Project Brain."""
    return _legacy_handoff("RUN_APPLICATION_WORKFLOW")

@mcp.tool(annotations=WRITE)
def run_registered_database_workflow(
    database_contract_id: str,
    payload: dict[str, Any] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named database contract. Unknown contracts and raw SQL/table selection fail closed."""
    return _legacy_handoff("RUN_DATABASE_WORKFLOW")

@mcp.tool(annotations=WRITE)
def run_registered_task(task: dict[str, Any], wait_seconds: int = 8) -> dict[str, Any]:
    """Send only a registered task intent to Project Brain; no runner, SHA, target or plan."""
    return _legacy_handoff("RUN_REGISTERED_TASK")

@mcp.tool(annotations=WRITE)
def brain_execute(task: dict[str, Any], wait_seconds: int = 8) -> dict[str, Any]:
    """Preferred Brain execution entrypoint. Submit a registered intent; Brain owns routing and Run Core execution."""
    return helper_call("RUN_REGISTERED_TASK", {
        "task": task,
        "wait_seconds": wait_seconds,
    })


@mcp.tool(annotations=RO)
def execution_status(request_handle: str) -> dict[str, Any]:
    """Read the bounded result status for one Controlled Execution request handle."""
    return helper_call("EXECUTION_STATUS", {"request_handle": request_handle})


def main() -> None:
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
