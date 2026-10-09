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

VERSION = "0.1.0"
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
        # Single public mutation ingress. Legacy typed handlers remain callable
        # for compatibility, but are not offered as competing choices by default.
        if os.environ.get("PB_EXPOSE_LEGACY_WRITE_TOOLS") != "1":
            visible = {"connector_health", "execution_status", "brain_execute"}
            tools = [tool for tool in tools if tool.name in visible]
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
    return body


@mcp.tool(annotations=WRITE)
def deploy_registered_source(
    system_id: str,
    source_sha: str,
    repository: str = "",
    paths: list[str] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Deploy one exact SHA through a registered system deployment contract."""
    return helper_call("DEPLOY_REGISTERED_SOURCE", {
        "system_id": system_id,
        "source_sha": source_sha,
        "repository": repository,
        "paths": paths or [],
        "wait_seconds": wait_seconds,
    })


@mcp.tool(annotations=WRITE)
def run_registered_application_workflow(
    workflow_id: str,
    operation: dict[str, Any],
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named registered application workflow through Project Brain."""
    return helper_call("RUN_APPLICATION_WORKFLOW", {
        "workflow_id": workflow_id,
        "operation": operation,
        "wait_seconds": wait_seconds,
    })


@mcp.tool(annotations=WRITE)
def run_registered_database_workflow(
    database_contract_id: str,
    payload: dict[str, Any] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named database contract. Unknown contracts and raw SQL/table selection fail closed."""
    return helper_call("RUN_DATABASE_WORKFLOW", {
        "database_contract_id": database_contract_id,
        "payload": payload or {},
        "wait_seconds": wait_seconds,
    })


@mcp.tool(annotations=WRITE)
def run_registered_task(task: dict[str, Any], wait_seconds: int = 8) -> dict[str, Any]:
    """Send only a registered task intent to Project Brain; no runner, SHA, target or plan."""
    return helper_call("RUN_REGISTERED_TASK", {
        "task": task,
        "wait_seconds": wait_seconds,
    })


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
