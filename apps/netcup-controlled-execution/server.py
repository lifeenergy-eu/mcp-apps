#!/usr/bin/env python3
"""Netcup-only MCP for Brain-signed typed tickets; no public CLI or deploy authority."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent.parent / "packages", HERE / "packages"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

TARGET = "SERVER-NETCUP-WORDPRESS"
PROFILE = "NETCUP_WORDPRESS_ROOT_WRITE_V1"
CLASS = "NETCUP_SELF_MANAGED_ROOT_SERVER"
SOURCE_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TICKET_KEYS = frozenset({
    "schema_version", "target_id", "profile_id", "job_id", "action", "args",
    "issued_at", "expires_at", "source_sha", "nonce", "signature",
})


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(name + "_REQUIRED")
    return value


def validate_helper(value: str) -> Path:
    root = Path("/opt/project-brain/netcup-control/releases")
    path = Path(value)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("NETCUP_SIGNED_HELPER_PATH_DENIED") from exc
    if len(relative.parts) != 3 or not SOURCE_PATTERN.fullmatch(relative.parts[0]) or relative.parts[1:] != ("netcup_agent", "write_entry.py"):
        raise RuntimeError("NETCUP_SIGNED_HELPER_PATH_DENIED")
    # Reject writable/symlinked Python import roots as well as the helper itself.
    for item in (Path("/opt"), Path("/opt/project-brain"), Path("/opt/project-brain/netcup-control"), root,
                 root / relative.parts[0], path.parent, path, path.parent / "__init__.py", path.parent / "agent.py"):
        if (item.is_symlink() or not item.exists() or item.resolve(strict=True) != item
                or item.stat().st_uid != 0 or item.stat().st_mode & 0o022):
            raise RuntimeError("NETCUP_SIGNED_HELPER_INTEGRITY_DENIED")
    if not path.is_file() or not (path.parent / "agent.py").is_file():
        raise RuntimeError("NETCUP_SIGNED_HELPER_INTEGRITY_DENIED")
    return path


def validate_runtime() -> tuple[str, int, str, Path]:
    required = {
        "MCP_TARGET_ID": TARGET,
        "MCP_PROFILE_ID": PROFILE,
        "MCP_TARGET_CLASS": CLASS,
        "MCP_AUTH_MODE": "oauth_private",
        "MCP_BIND_HOST": "127.0.0.1",
    }
    for name, expected in required.items():
        if require(name) != expected:
            raise RuntimeError("NETCUP_WRITE_IDENTITY_MISMATCH")
    if AUTH_MODE != "oauth_private" or OAUTH_SCOPES != ["control.execute"]:
        raise RuntimeError("NETCUP_WRITE_OAUTH_SCOPE_MISMATCH")
    port = int(require("MCP_BIND_PORT"))
    if port != 8793:
        raise RuntimeError("NETCUP_WRITE_BIND_DENIED")
    return require("MCP_BIND_HOST"), port, require("MCP_PUBLIC_HOST"), validate_helper(require("NETCUP_SIGNED_HELPER"))


HOST, PORT, PUBLIC_HOST, HELPER = validate_runtime()
SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", f"https://{PUBLIC_HOST}", f"https://{PUBLIC_HOST}:*"],
)
mcp = FastMCP(
    "project-brain-netcup-target-controlled-execution",
    instructions="Accept Brain-authorized Ed25519 signed, target-bound single-use tickets only. No caller shell, raw SQL, arbitrary filesystem operations or independent deployment authority.",
    host=HOST, port=PORT, streamable_http_path="/mcp",
    stateless_http=True, json_response=True,
    transport_security=SECURITY, auth=AUTH_SETTINGS,
    auth_server_provider=AUTH_PROVIDER,
)
mcp.custom_route("/oauth/login", methods=["GET", "POST"], include_in_schema=False)(oauth_login_handler)
RO = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}


@mcp.tool(annotations=RO)
def connector_health() -> dict[str, Any]:
    """Return identity and the non-authoritative MCP transport posture."""
    return {
        "target_id": TARGET, "profile_id": PROFILE,
        "authentication": "oauth2-private", "oauth_scopes": OAUTH_SCOPES,
        "transport": "streamable-http", "mcp_path": "/mcp",
        "privileged_execution": "ONLY_SIGNED_RUN_CORE_TICKET",
        "helper_activation_verified": False, "arbitrary_shell": False,
        "deploy_authority": False, "secrets_emitted": False,
    }


@mcp.tool(annotations=WRITE)
def submit_signed_run_core_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Delegate one fully signed exact Netcup action to the pinned root helper."""
    if not isinstance(ticket, dict) or set(ticket) != TICKET_KEYS or ticket.get("target_id") != TARGET:
        return {"status": "FAIL_CLOSED", "code": "NETCUP_WRITE_TICKET_SHAPE_OR_TARGET_DENIED"}
    raw = json.dumps(ticket, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 8192:
        return {"status": "FAIL_CLOSED", "code": "NETCUP_WRITE_TICKET_TOO_LARGE"}
    try:
        proc = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/bin/env", f"PYTHONPATH={HELPER.parent.parent}", "/usr/bin/python3", "-P", str(HELPER)],
            input=raw, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
            timeout=60, check=False,
        )
        if not proc.stdout or len(proc.stdout) > 16384:
            return {"status": "FAIL_CLOSED", "code": "NETCUP_WRITE_HELPER_RESPONSE_INVALID"}
        response = json.loads(proc.stdout)
        # Only disclose fixed verifier codes; never expose helper stderr or secrets.
        safe_codes = {"TICKET_REPLAY_REJECTED", "TICKET_TIME_REJECTED", "TICKET_TARGET_MISMATCH", "TICKET_SIGNATURE_REJECTED", "WRITE_SOURCE_SHA_MISMATCH", "ACTION_NOT_REGISTERED"}
        if proc.returncode != 0 and isinstance(response, dict) and response.get("status") == "FAIL_CLOSED" and response.get("code") in safe_codes:
            return {"status": "FAIL_CLOSED", "code": response["code"], "target_id": TARGET}
        if not isinstance(response, dict) or response.get("target_id") != TARGET or response.get("action") != ticket["action"] or response.get("job_id") != ticket["job_id"] or response.get("status") != "PASS" or proc.returncode != 0:
            return {"status": "FAIL_CLOSED", "code": "NETCUP_WRITE_HELPER_REJECTED"}
        return response
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "FAIL_CLOSED", "code": "NETCUP_WRITE_HELPER_UNAVAILABLE"}


if __name__ == "__main__":
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT)
