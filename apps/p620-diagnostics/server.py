#!/usr/bin/env python3
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "packages", HERE / "packages"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler
from infrastructure_read_policy import FixedHelperClient, install_read_only_tools

VERSION = "0.7.1"
DEFAULT_HELPER = "/usr/local/libexec/p620-debug-read"
DEFAULT_TOKEN_FILE = "/srv/project-brain/secrets/p620-mcp.token"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else default


HOST = _env("MCP_BIND_HOST", "127.0.0.1")
PORT = int(_env("MCP_BIND_PORT", "8792"))
PUBLIC_HOST = _env("MCP_PUBLIC_HOST", "localhost")
TOKEN_FILE = Path(_env("MCP_BEARER_TOKEN_FILE", DEFAULT_TOKEN_FILE))
HELPER = FixedHelperClient.from_environment(
    default_helper=DEFAULT_HELPER,
    default_mode="sudo_noninteractive",
)


def load_token() -> str:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise RuntimeError("MCP_BEARER_TOKEN_UNAVAILABLE") from exc
    if len(token) < 32:
        raise RuntimeError("MCP_BEARER_TOKEN_INVALID")
    return token


BOOTSTRAP_TOKEN = load_token() if AUTH_MODE == "bootstrap_bearer" else None
SECURITY_SCHEMES = [{"type": "oauth2", "scopes": ["control.execute"]}] if AUTH_MODE == "oauth_private" else []


class PluginFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        if not SECURITY_SCHEMES:
            return tools
        out = []
        for tool in tools:
            meta = dict(tool.meta or {})
            meta["securitySchemes"] = SECURITY_SCHEMES
            out.append(tool.model_copy(update={"meta": meta, "securitySchemes": SECURITY_SCHEMES}))
        return out


security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", f"https://{PUBLIC_HOST}", f"https://{PUBLIC_HOST}:*"],
)

mcp = PluginFastMCP(
    "P620 Ubuntu Server MCP",
    instructions=(
        "Direct P620 Ubuntu Server MCP with READ diagnostics and authenticated WRITE/CLI. "
        "Independent from Brain deploy and relay. Never expose credentials."
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


def connector_health() -> dict[str, Any]:
    return {
        "status": "PASS",
        "connector_version": VERSION,
        "transport": "streamable-http",
        "mcp_path": "/mcp",
        "authentication": "oauth2-private-single-user" if AUTH_MODE == "oauth_private" else "bootstrap-bearer-token-required",
        "oauth_scopes": OAUTH_SCOPES if AUTH_MODE == "oauth_private" else [],
        "product_data_path": "remote-mcp-client-direct-to-host",
        "cloudways_in_product_data_path": False,
        "read_only": False,
        "arbitrary_shell": True,
        "mutation_tools": True,
        "deploy_tools": False,
        "helper_mode": HELPER.mode,
        "server_name": "P620 Ubuntu Server MCP",
        "admin_helper": ADMIN_HELPER,
        "secret_values_emitted": False,
    }


install_read_only_tools(
    mcp,
    HELPER,
    connector_health,
    default_git_repo="/srv/project-brain/source/project-brain",
)


# Direct P620 host administration. OAuth is upgraded to control.execute on deployment.
import base64
import json
import secrets
import subprocess

ADMIN_HELPER = "/opt/p620-server-mcp/root_helper.py"
WRITE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}

def _admin_invoke(operation: str, **kwargs: Any) -> dict[str, Any]:
    req = {"operation": operation, "request_id": "P620-" + secrets.token_hex(20), **kwargs}
    try:
        proc = subprocess.run(
            ["/usr/bin/sudo", "-n", "/usr/bin/python3", "-I", ADMIN_HELPER],
            input=json.dumps(req), text=True, capture_output=True,
            timeout=145, check=False, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
        if len(proc.stdout) > 100000:
            return {"status": "ERROR", "code": "OUTPUT_TOO_LARGE"}
        out = json.loads(proc.stdout)
        return out if isinstance(out, dict) else {"status": "ERROR", "code": "INVALID_REPLY"}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "ERROR", "code": "ROOT_HELPER_FAILURE"}

@mcp.tool(annotations=WRITE)
def run_command(argv: list[str], cwd: str = "/", timeout_seconds: int = 60) -> dict[str, Any]:
    """Execute bounded direct command on P620 Ubuntu. Never send credentials."""
    return _admin_invoke("run", argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)

@mcp.tool(annotations=WRITE)
def write_file(path: str, content_base64: str, mode: int = 384) -> dict[str, Any]:
    """Atomically write file on P620 Ubuntu."""
    return _admin_invoke("write_file", path=path, data_base64=content_base64, mode=mode)

@mcp.tool(annotations=WRITE)
def create_directory(path: str, parents: bool = True, exist_ok: bool = True) -> dict[str, Any]:
    """Create directory on P620 Ubuntu."""
    return _admin_invoke("mkdir", path=path, parents=parents, exist_ok=exist_ok)

@mcp.tool(annotations=WRITE)
def change_permissions(path: str, mode: int) -> dict[str, Any]:
    """Change filesystem mode on P620 Ubuntu."""
    return _admin_invoke("chmod", path=path, mode=mode)

@mcp.tool(annotations=WRITE)
def remove_path(path: str, recursive: bool = False) -> dict[str, Any]:
    """Remove a specified path on P620 Ubuntu. Destructive operation."""
    return _admin_invoke("remove", path=path, recursive=recursive)


class BootstrapBearerGate:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
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
