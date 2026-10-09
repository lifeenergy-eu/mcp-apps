#!/usr/bin/env python3
from __future__ import annotations

import hmac
import os
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

from infrastructure_read_policy import FixedHelperClient, install_read_only_tools
from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

VERSION = "0.1.0"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


HOST = _optional("MCP_BIND_HOST", "127.0.0.1")
PORT = int(_optional("MCP_BIND_PORT", "8792"))
PUBLIC_HOST = _required("MCP_PUBLIC_HOST")
TARGET_ID = _required("MCP_TARGET_ID")
PROFILE_ID = _required("MCP_PROFILE_ID")
HELPER = FixedHelperClient.from_environment(
    default_helper=str(HERE / "helper.py"),
    default_mode="python3_direct",
)
TOKEN_FILE = Path(_optional("MCP_BEARER_TOKEN_FILE", str(HERE / ".bootstrap-token")))


def load_token() -> str:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise RuntimeError("MCP_BEARER_TOKEN_UNAVAILABLE") from exc
    if len(token) < 32:
        raise RuntimeError("MCP_BEARER_TOKEN_INVALID")
    return token


BOOTSTRAP_TOKEN = load_token() if AUTH_MODE == "bootstrap_bearer" else None
SECURITY_SCHEMES = [{"type": "oauth2", "scopes": OAUTH_SCOPES}] if AUTH_MODE == "oauth_private" else []


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
    "private-infrastructure-access",
    instructions=(
        "Private Infrastructure Access for one fixed Cloudways target. "
        "Authenticated read-only diagnostics only. Every host read is delegated to "
        "the fixed target helper. No arbitrary shell, mutation, deploy, restart, "
        "secret reads, generic command execution, or caller-selected roots."
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
        "target_id": TARGET_ID,
        "profile_id": PROFILE_ID,
        "product_data_path": "remote-mcp-client-direct-to-cloudways-host",
        "cloudways_in_product_data_path": True,
        "read_only": True,
        "arbitrary_shell": False,
        "mutation_tools": False,
        "deploy_tools": False,
        "helper_mode": HELPER.mode,
        "secret_values_emitted": False,
    }


install_read_only_tools(mcp, HELPER, connector_health, target_id=TARGET_ID)


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
