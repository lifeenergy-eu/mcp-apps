#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from auth import AUTH_MODE, AUTH_SETTINGS, OAUTH_SCOPES, TOKEN_VERIFIER

VERSION = "0.4.0"
DEFAULT_HELPER = "/usr/local/libexec/p620-debug-read"
DEFAULT_TOKEN_FILE = "/srv/project-brain/secrets/p620-mcp.token"

RO = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else default


HOST = _env("MCP_BIND_HOST", "127.0.0.1")
PORT = int(_env("MCP_BIND_PORT", "8792"))
PUBLIC_HOST = _env("MCP_PUBLIC_HOST", "localhost")
HELPER = _env("MCP_READ_HELPER", DEFAULT_HELPER)
TOKEN_FILE = Path(_env("MCP_BEARER_TOKEN_FILE", DEFAULT_TOKEN_FILE))


def load_token() -> str:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise RuntimeError("MCP_BEARER_TOKEN_UNAVAILABLE") from exc
    if len(token) < 32:
        raise RuntimeError("MCP_BEARER_TOKEN_INVALID")
    return token


BOOTSTRAP_TOKEN = load_token() if AUTH_MODE == "bootstrap_bearer" else None
SECURITY_SCHEMES = [{"type": "oauth2", "scopes": OAUTH_SCOPES}] if AUTH_MODE == "oauth" else []


class PluginFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        if not SECURITY_SCHEMES:
            return tools
        out = []
        for tool in tools:
            meta = dict(tool.meta or {})
            meta["securitySchemes"] = SECURITY_SCHEMES
            out.append(tool.model_copy(update={
                "meta": meta,
                "securitySchemes": SECURITY_SCHEMES,
            }))
        return out


security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "127.0.0.1:*",
        "localhost:*",
        PUBLIC_HOST,
        f"{PUBLIC_HOST}:*",
    ],
    allowed_origins=[
        "http://127.0.0.1:*",
        "http://localhost:*",
        f"https://{PUBLIC_HOST}",
        f"https://{PUBLIC_HOST}:*",
    ],
)

mcp = PluginFastMCP(
    "private-infrastructure-access",
    instructions=(
        "Private Infrastructure Access: authenticated read-only infrastructure diagnostics. "
        "Every host read is delegated to the configured fixed helper. "
        "No arbitrary shell, mutation, secret reads, or generic command execution."
    ),
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=security,
    auth=AUTH_SETTINGS,
    token_verifier=TOKEN_VERIFIER,
)


def helper_call(action: str, **params: Any) -> dict[str, Any]:
    payload = {"action": action, **params}
    p = subprocess.run(
        ["sudo", "-n", HELPER],
        input=json.dumps(payload, separators=(",", ":")),
        capture_output=True,
        text=True,
        timeout=40,
        shell=False,
    )
    raw = (p.stdout or "").strip()
    if not raw:
        raise RuntimeError("MCP_READ_HELPER_EMPTY_RESPONSE")
    try:
        body = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("MCP_READ_HELPER_INVALID_RESPONSE") from exc
    if p.returncode != 0 or body.get("status") != "PASS":
        raise RuntimeError(str(body.get("code") or "MCP_READ_HELPER_FAILED"))
    return body


@mcp.tool(annotations=RO)
def connector_health() -> dict[str, Any]:
    """Return connector version and enforced security posture."""
    return {
        "status": "PASS",
        "connector_version": VERSION,
        "transport": "streamable-http",
        "mcp_path": "/mcp",
        "authentication": (
            "oauth2-resource-server" if AUTH_MODE == "oauth"
            else "bootstrap-bearer-token-required"
        ),
        "oauth_scopes": OAUTH_SCOPES if AUTH_MODE == "oauth" else [],
        "product_data_path": "remote-mcp-client-direct-to-host",
        "cloudways_in_product_data_path": False,
        "read_only": True,
        "arbitrary_shell": False,
        "host_read_backend": HELPER,
        "secret_values_emitted": False,
    }


@mcp.tool(annotations=RO)
def system_info() -> dict[str, Any]:
    """Read OS, uptime, memory, CPU and available GPU diagnostics."""
    return helper_call("SYSTEM_INFO")


@mcp.tool(annotations=RO)
def disk_usage() -> dict[str, Any]:
    """Read filesystem and block-device usage."""
    return helper_call("DISK_USAGE")


@mcp.tool(annotations=RO)
def service_status(units: list[str]) -> dict[str, Any]:
    """Read systemd status for explicitly named units."""
    return helper_call("SERVICE_STATUS", units=units)


@mcp.tool(annotations=RO)
def journal_read(units: list[str], lines: int = 300, since: str = "", until: str = "") -> dict[str, Any]:
    """Read bounded systemd journal output for explicitly named units."""
    return helper_call("JOURNAL_READ", units=units, lines=lines, since=since, until=until)


@mcp.tool(annotations=RO)
def process_list() -> dict[str, Any]:
    """Read the process table ordered by CPU usage."""
    return helper_call("PROCESS_LIST")


@mcp.tool(annotations=RO)
def socket_list() -> dict[str, Any]:
    """Read listening TCP/UDP sockets and owning processes."""
    return helper_call("SOCKET_LIST")


@mcp.tool(annotations=RO)
def file_read(path: str, limit: int = 65536, offset: int = 0) -> dict[str, Any]:
    """Read bounded text from a host path allowed by the helper."""
    return helper_call("FILE_READ", path=path, limit=limit, offset=offset)


@mcp.tool(annotations=RO)
def file_stat(path: str) -> dict[str, Any]:
    """Read metadata for an allowed host path."""
    return helper_call("FILE_STAT", path=path)


@mcp.tool(annotations=RO)
def dir_list(path: str, limit: int = 200) -> dict[str, Any]:
    """List an allowed directory with a bounded result count."""
    return helper_call("DIR_LIST", path=path, limit=limit)


@mcp.tool(annotations=RO)
def file_find(path: str, name_contains: str, limit: int = 100) -> dict[str, Any]:
    """Find files/directories by bounded name substring under an allowed root."""
    return helper_call("FILE_FIND", path=path, name_contains=name_contains, limit=limit)


@mcp.tool(annotations=RO)
def hash_file(path: str) -> dict[str, Any]:
    """Return SHA-256 and size for an allowed file."""
    return helper_call("HASH_FILE", path=path)


@mcp.tool(annotations=RO)
def git_read(repo: str = "/srv/project-brain/source/project-brain", op: str = "status", limit: int = 20) -> dict[str, Any]:
    """Read bounded Git state from a host checkout allowed by the helper."""
    return helper_call("GIT_READ", repo=repo, op=op, limit=limit)


@mcp.tool(annotations=RO)
def sqlite_read_only(path: str, query: str, limit: int = 200) -> dict[str, Any]:
    """Execute one bounded read-only SQLite query through the helper."""
    return helper_call("SQLITE_READ_ONLY", path=path, query=query, limit=limit)


class BootstrapBearerGate:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin1").lower(): v.decode("latin1")
            for k, v in scope.get("headers", [])
        }
        expected = f"Bearer {BOOTSTRAP_TOKEN}"
        if not hmac.compare_digest(headers.get("authorization", ""), expected):
            body = b'{"error":"authentication_required"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="mcp"'),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def main() -> None:
    app = mcp.streamable_http_app()
    if AUTH_MODE == "bootstrap_bearer":
        app = BootstrapBearerGate(app)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
