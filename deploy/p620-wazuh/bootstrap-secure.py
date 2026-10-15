#!/usr/bin/env python3
"""Secure bootstrap of a *runtime copy* of upstream Wazuh 4.14.9 single-node.
No credentials are committed to GitHub or printed to stdout.
"""
from __future__ import annotations
import json
import os
import re
import secrets
from pathlib import Path
import bcrypt

BASE = Path("/opt/p620-wazuh")
RUNTIME = BASE / "runtime"
SECRETS = BASE / "secrets"
VAULT = SECRETS / "credentials.json"
USERS = RUNTIME / "config/wazuh_indexer/internal_users.yml"
COMPOSE = RUNTIME / "docker-compose.yml"
DASHBOARD = RUNTIME / "config/wazuh_dashboard/wazuh.yml"

def make_password() -> str:
    return secrets.token_urlsafe(30) + "A1!"

def save(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)

def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("ROOT_REQUIRED")
    if VAULT.exists():
        raise SystemExit("ALREADY_INITIALIZED_CREDENTIALS_PRESENT")
    for path in (USERS, COMPOSE, DASHBOARD):
        if not path.is_file():
            raise SystemExit("REQUIRED_CONFIG_MISSING:" + str(path))
    SECRETS.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRETS, 0o700)
    users = ("admin", "kibanaserver", "kibanaro", "logstash", "readall", "snapshotrestore")
    passwords = {name: make_password() for name in users}
    passwords["wazuh_api_wui"] = make_password()
    text = USERS.read_text(encoding="utf-8")
    for name in users:
        expression = r"(?ms)^(%s:\n  hash: )[^\n]+" % re.escape(name)
        new_hash = bcrypt.hashpw(passwords[name].encode(), bcrypt.gensalt(rounds=12, prefix=b"2a")).decode()
        text, count = re.subn(expression, lambda m: m.group(1) + '"' + new_hash + '"', text)
        if count != 1:
            raise SystemExit("EXPECTED_ONE_USER_HASH:" + name + ":" + str(count))
    compose = COMPOSE.read_text(encoding="utf-8")
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    replacements = {
        "SecretPassword": passwords["admin"],
        "kibanaserver": passwords["kibanaserver"],
        "MyS3cr37P450r.*-": passwords["wazuh_api_wui"],
    }
    # Replace password values only, never the 'kibanaserver' username.
    compose = compose.replace("INDEXER_PASSWORD=SecretPassword", "INDEXER_PASSWORD=" + passwords["admin"])
    compose = compose.replace("DASHBOARD_PASSWORD=kibanaserver", "DASHBOARD_PASSWORD=" + passwords["kibanaserver"])
    compose = compose.replace("API_PASSWORD=MyS3cr37P450r.*-", "API_PASSWORD=" + passwords["wazuh_api_wui"])
    dashboard = dashboard.replace("MyS3cr37P450r.*-", passwords["wazuh_api_wui"])
    if ("SecretPassword" in compose or "MyS3cr37P450r.*-" in compose
        or "DASHBOARD_PASSWORD=kibanaserver" in compose or "MyS3cr37P450r.*-" in dashboard):
        raise SystemExit("DEFAULT_CREDENTIALS_REMAIN")
    # Store the credentials before changing operational config. Never echo the values.
    save(VAULT, json.dumps(passwords, indent=2) + "\n")
    save(USERS, text)
    save(COMPOSE, compose)
    save(DASHBOARD, dashboard)
    print("WAZUH_RUNTIME_CREDENTIALS_ROTATED; vault=" + str(VAULT))
    print("CHANGED_INDEXER_USERS=" + str(len(users)) + "; API_WUI=1")

if __name__ == "__main__":
    main()
