#!/usr/bin/env python3
"""Target-isolated Netcup READ helper; never runs privileged commands."""
from __future__ import annotations

import json
import os
from pathlib import PurePosixPath

from .cloudways_helper import helper_main

TARGET = "SERVER-NETCUP-WORDPRESS"
PROFILE = "NETCUP_WORDPRESS_ROOT_SERVER_V1"
TARGET_CLASS = "NETCUP_SELF_MANAGED_ROOT_SERVER"
SAFE_ROOTS = frozenset({
    "/var/log/nginx", "/var/log/mysql", "/var/log/redis",
    "/var/lib/project-brain/control",
    "/var/lib/project-brain/netcup-webstack",
})
SAFE_GIT_ROOTS = frozenset({
    "/opt/project-brain/netcup-control/releases",
    "/opt/project-brain/mcp/read/releases",
})
SAFE_UNITS = frozenset({
    "nginx.service", "php8.3-fpm.service", "redis-server.service",
    "mariadb.service", "ssh.service", "fail2ban.service",
    "auditd.service", "ufw.service", "chrony.service",
    "cloudflared.service", "tailscaled.service",
    "project-brain-netcup-read-mcp.service",
    "project-brain-netcup-controlled-execution-mcp.service",
})


def _list(name: str) -> list[str]:
    try:
        value = json.loads(os.environ.get(name, "[]"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("NETCUP_READ_ALLOWLIST_INVALID") from exc
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise RuntimeError("NETCUP_READ_ALLOWLIST_INVALID")
    return value


def validate_environment() -> None:
    exact = {
        "MCP_TARGET_ID": TARGET,
        "MCP_PROFILE_ID": PROFILE,
        "MCP_TARGET_CLASS": TARGET_CLASS,
        "MCP_AUTH_MODE": "oauth_private",
        "MCP_BIND_HOST": "127.0.0.1",
    }
    for key, expected in exact.items():
        if os.environ.get(key) != expected:
            raise RuntimeError("NETCUP_READ_TARGET_ENV_MISMATCH")
    if os.environ.get("MCP_READ_POLICY_V2", "0") == "1":
        raise RuntimeError("NETCUP_READ_CLOUDWAYS_V2_FORBIDDEN")
    if _list("MCP_V2_SYSTEM_LOG_ROOTS_JSON"):
        raise RuntimeError("NETCUP_READ_CLOUDWAYS_LOG_SCOPE_FORBIDDEN")
    roots = _list("MCP_ALLOWED_ROOTS_JSON")
    if not roots or len(roots) != len(set(roots)) or not set(roots) <= SAFE_ROOTS:
        raise RuntimeError("NETCUP_READ_ROOTS_UNSAFE")
    git_roots = _list("MCP_ALLOWED_GIT_ROOTS_JSON")
    if len(git_roots) != len(set(git_roots)) or not set(git_roots) <= SAFE_GIT_ROOTS:
        raise RuntimeError("NETCUP_READ_GIT_ROOTS_UNSAFE")
    units = _list("MCP_ALLOWED_SERVICES_JSON")
    if not units or len(units) != len(set(units)) or not set(units) <= SAFE_UNITS:
        raise RuntimeError("NETCUP_READ_SERVICES_UNSAFE")
    if _list("MCP_ALLOWED_SQLITE_PATHS_JSON"):
        raise RuntimeError("NETCUP_READ_SQLITE_NOT_ACTIVATED")


def netcup_helper_main() -> int:
    try:
        validate_environment()
    except RuntimeError as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED", "code": str(exc),
            "read_only": True, "mutation": False,
            "arbitrary_shell": False, "secret_values_emitted": False,
        }, sort_keys=True))
        return 2
    return helper_main()
