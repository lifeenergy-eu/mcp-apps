#!/usr/bin/env python3
"""Source-only single-operator MCP prototype. NOT a public multi-tenant release."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGES = HERE.parents[1] / "packages"
if PACKAGES.is_dir():
    sys.path.insert(0, str(PACKAGES))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler
from business_api import BusinessApiClient, BusinessApiError

if AUTH_MODE != "oauth_private":
    raise RuntimeError("BUSINESS_MCP_OAUTH_REQUIRED")

host = os.environ.get("BUSINESS_MCP_BIND_HOST", "127.0.0.1")
port = int(os.environ.get("BUSINESS_MCP_BIND_PORT", "8795"))
public_host = os.environ.get("BUSINESS_MCP_PUBLIC_HOST", "localhost")

mcp = FastMCP(
    "business-intelligence",
    instructions="Read-only source-backed business facts. Missing facts must not be inferred.",
    host=host,
    port=port,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", public_host, f"{public_host}:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", f"https://{public_host}"],
    ),
    auth=AUTH_SETTINGS,
    auth_server_provider=AUTH_PROVIDER,
)

mcp.custom_route("/oauth/login", methods=["GET", "POST"], include_in_schema=False)(oauth_login_handler)


@mcp.tool()
def company_profile_by_oib(oib: str) -> dict:
    """Retrieve a source-backed Croatian company profile by exact 11-digit OIB."""
    return BusinessApiClient.from_environment().company_by_oib(oib)


@mcp.tool()
def company_source_provenance_by_oib(oib: str) -> dict:
    """Return verified source identifiers and retrieval timestamps for a Croatian company.

    Uses the same authorized Business API request and never accesses Fabric or CRM directly.
    """
    return BusinessApiClient.from_environment().company_source_provenance_by_oib(oib)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.streamable_http_app(), host=host, port=port, log_level="info")
