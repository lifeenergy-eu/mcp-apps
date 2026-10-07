from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent.parent / "packages", HERE / "packages"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

os.environ.setdefault("MCP_OAUTH_DB_PATH", "/srv/project-brain/mcp-oauth/oauth.sqlite3")
os.environ.setdefault("MCP_OAUTH_PASSWORD_FILE", "/srv/project-brain/secrets/p620-mcp-oauth-password")
os.environ.setdefault("MCP_OAUTH_STATIC_CLIENT_ID_FILE", "/srv/project-brain/secrets/p620-mcp-oauth-client-id")
os.environ.setdefault("MCP_OAUTH_STATIC_CLIENT_SECRET_FILE", "/srv/project-brain/secrets/p620-mcp-oauth-client-secret")

from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

__all__ = ["AUTH_MODE", "AUTH_PROVIDER", "AUTH_SETTINGS", "OAUTH_SCOPES", "oauth_login_handler"]
