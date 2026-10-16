"""Product activation boundary; not a tenant identity provider.

Current shared OAuth implementation authenticates a *single private operator*.
External tenant access must not be enabled by a deployment environment switch.
A future authenticated per-user/token-exchange implementation is required.
"""
from __future__ import annotations

import os


class ProductAccessError(RuntimeError):
    pass


def require_private_operator_mode(environ=None) -> None:
    env = os.environ if environ is None else environ
    mode = env.get("BUSINESS_MCP_CLIENT_MODE", "private_operator")
    if mode != "private_operator":
        raise ProductAccessError("BUSINESS_MCP_TENANT_AUTH_NOT_IMPLEMENTED")
    if env.get("BUSINESS_MCP_PUBLIC_CLIENTS_ENABLED", "false").strip().lower() not in ("", "false", "0"):
        raise ProductAccessError("BUSINESS_MCP_PUBLIC_CLIENTS_NOT_AUTHORIZED")
    if env.get("MCP_AUTH_MODE", "") != "oauth_private":
        raise ProductAccessError("BUSINESS_MCP_PRIVATE_OAUTH_REQUIRED")
    scopes = set(env.get("MCP_OAUTH_SCOPES", "").split(","))
    if "business.read" not in {scope.strip() for scope in scopes}:
        raise ProductAccessError("BUSINESS_MCP_READ_SCOPE_REQUIRED")
