#!/usr/bin/env python3
"""WordPress-scoped MCP adapter into the canonical GitHub relay / Run Core.

Uses *existing* Project Brain relay_batch and wordpress_application_mutation
runners. It does not execute remote SSH, PHP, shell, SQL or WordPress mutation.
An independent, private GitHub contents credential is required on this host.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE = Path.home() / ".project-brain/controlled-execution-mcp-wordpress"
TOKEN_FILE = BASE / "state/github_operation_token"
HANDLES = BASE / "state/relay_handles"
REPO = "lifeenergy-eu/project-brain"
API = f"https://api.github.com/repos/{REPO}"
MCP_SCOPE = "SERVER-CLOUDWAYS-WORDPRESS"
SAFE_APP = re.compile(r"^[a-z0-9]{8,16}$")
SAFE_HANDLE = re.compile(r"^[a-f0-9]{64}$")
EXPOSED = {
    "WORDPRESS_CAPABILITY_PROBE_V1": "capability_probe",
    "WORDPRESS_CACHE_INSPECT_V1": "filesystem_cleanup",
}
CLEANUP = {"cache", "breeze_cache", "debug_log", "upgrade_temp"}

class Failure(Exception):
    def __init__(self, code: str):
        self.code = code

def token() -> str:
    if not TOKEN_FILE.is_file() or TOKEN_FILE.stat().st_mode & 0o077:
        raise Failure("WORDPRESS_RELAY_GITHUB_CREDENTIAL_MISSING_OR_INSECURE")
    value = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(value) < 30:
        raise Failure("WORDPRESS_RELAY_GITHUB_CREDENTIAL_INVALID")
    return value

def api(method: str, resource: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    headers = {
        "Authorization": "Bearer " + token(),
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Project-Brain-WordPress-Write-MCP/1",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + resource, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            obj = json.loads(response.read(3_000_000))
            if not isinstance(obj, dict):
                raise Failure("WORDPRESS_RELAY_GITHUB_RESPONSE_INVALID")
            return obj
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Failure("WORDPRESS_RELAY_GITHUB_NOT_FOUND") from exc
        if exc.code in (401, 403):
            raise Failure("WORDPRESS_RELAY_GITHUB_CREDENTIAL_REJECTED") from exc
        if exc.code in (409, 422):
            raise Failure("WORDPRESS_RELAY_GITHUB_CONFLICT") from exc
        raise Failure("WORDPRESS_RELAY_GITHUB_HTTP_FAILED") from exc
    except urllib.error.URLError as exc:
        raise Failure("WORDPRESS_RELAY_GITHUB_UNREACHABLE") from exc

def fetch(path: str, ref: str = "main") -> dict:
    resource = "/contents/" + urllib.parse.quote(path, safe="/") + "?ref=" + urllib.parse.quote(ref)
    obj = api("GET", resource)
    encoded = str(obj.get("content") or "").replace("\n", "")
    if obj.get("encoding") != "base64" or not encoded:
        raise Failure("WORDPRESS_RELAY_GITHUB_FILE_INVALID")
    data = json.loads(base64.b64decode(encoded, validate=True))
    if not isinstance(data, dict):
        raise Failure("WORDPRESS_RELAY_GITHUB_JSON_INVALID")
    return data

def create(path: str, data: dict, message: str) -> str:
    encoded = base64.b64encode((json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()).decode()
    obj = api("PUT", "/contents/" + urllib.parse.quote(path, safe="/"), {
        "message": message, "content": encoded, "branch": "main",
    })
    sha = str((obj.get("commit") or {}).get("sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Failure("WORDPRESS_RELAY_COMMIT_UNVERIFIED")
    return sha

def canonical() -> tuple[str, set[str]]:
    state = fetch("control-plane/CURRENT_STATE.json")
    row = (((state.get("control_plane") or {}).get("current_releases") or {}).get("systems") or {}).get("PROJECT-BRAIN-CONTROL-PLANE") or {}
    sha = str(row.get("source_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Failure("WORDPRESS_RELAY_EXECUTION_SHA_UNRESOLVED")
    caps = fetch("control-plane/EXECUTION_CAPABILITY_CONTRACTS.json")
    wp = (caps.get("systems") or {}).get("SYSTEM-WORDPRESS") or {}
    mutation = wp.get("MUTATE_WORDPRESS_APPLICATION_GUARDED_WORKFLOW") or {}
    if mutation.get("route") != "wordpress_application_mutation" or mutation.get("architecture_binding") != "RUN_CORE_INTERNAL_LEAF_ONLY":
        raise Failure("WORDPRESS_RELAY_CAPABILITY_NOT_REGISTERED")
    registry = fetch("systems/wordpress.json")
    installations = registry.get("installations") or {}
    apps = {str(v.get("application_id")) for v in installations.values() if isinstance(v, dict) and v.get("server_id") == MCP_SCOPE}
    return sha, apps

def health() -> dict:
    sha, apps = canonical()
    return {
        "status": "PASS", "target_id": MCP_SCOPE, "transport": "EXISTING_GITHUB_RELAY",
        "execution_binding": "RUN_CORE_BOUND_RELAY_BATCH", "write_backend": "CANONICAL_RELAY",
        "canonical_execution_source_sha": sha, "registered_wordpress_installations": len(apps),
        "registered_workflows": sorted(EXPOSED), "read_mcp_separate": True,
        "arbitrary_shell": False, "raw_sql": False, "caller_selected_runner": False,
        "secrets_emitted": False,
    }

def workflow(payload: dict) -> dict:
    name = str(payload.get("workflow_id") or "")
    action = EXPOSED.get(name)
    if action is None:
        raise Failure("WORDPRESS_WORKFLOW_NOT_REGISTERED")
    operation = payload.get("operation")
    if not isinstance(operation, dict):
        raise Failure("WORDPRESS_WORKFLOW_PAYLOAD_INVALID")
    app_id = str(operation.get("app_id") or "")
    if not SAFE_APP.fullmatch(app_id):
        raise Failure("WORDPRESS_APPLICATION_ID_INVALID")
    execution_sha, apps = canonical()
    if app_id not in apps:
        raise Failure("WORDPRESS_APPLICATION_NOT_IN_CANONICAL_REGISTRY")
    if action == "capability_probe":
        if set(operation) != {"app_id"}:
            raise Failure("WORDPRESS_PROBE_FIELDS_FORBIDDEN")
        mutation = {"action": action, "app_id": app_id}
    else:
        if set(operation) - {"app_id", "targets", "dry_run"}:
            raise Failure("WORDPRESS_CACHE_INSPECT_FIELDS_FORBIDDEN")
        targets = operation.get("targets")
        if not isinstance(targets, list) or not targets or len(targets) > 4 or any(x not in CLEANUP for x in targets):
            raise Failure("WORDPRESS_CACHE_TARGETS_INVALID")
        if operation.get("dry_run") is not True:
            raise Failure("WORDPRESS_CACHE_INSPECT_DRY_RUN_REQUIRED")
        mutation = {"action": action, "app_id": app_id, "targets": targets, "dry_run": True}
    # Match current canonical PB_RELAY_BATCH_V1 plan and its internal WP mutation leaf.
    moment = dt.datetime.now(dt.timezone.utc)
    now = moment.isoformat(timespec="seconds").replace("+00:00", "Z")
    expires = (moment + dt.timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    suffix = secrets.token_hex(10).upper()
    op_id = "WP-MCP-" + moment.strftime("%Y%m%dT%H%M%SZ") + "-" + suffix
    run_id = "RUN-" + op_id
    plan_path = f"control-plane/operations/plans/{op_id}.json"
    leaf = {
        "schema_version": "1.0", "plan_id": op_id + "-WP-LEAF",
        "plan_profile": "WORDPRESS_APPLICATION_MUTATION_V1",
        "repository": REPO, "source_sha": execution_sha,
        "target_id": "wordpress-production", "github_actions_execution": False,
        "production_application_mutation": True, "production_database_mutation": False,
        "mutation": mutation,
    }
    plan = {
        "schema_version": "1.0", "plan_id": op_id, "plan_profile": "PB_RELAY_BATCH_V1",
        "repository": REPO, "source_sha": execution_sha, "run_id": run_id,
        "github_actions_execution": False, "result_mode": "COMPACT",
        "production_application_mutation": True, "production_database_mutation": False,
        "steps": [{"step_id": "STEP-WORDPRESS-MUTATION", "operation_kind": "wordpress_application_mutation",
                   "dependency_refs": [], "plan": leaf}],
    }
    control_sha = create(plan_path, plan, "Queue bounded WordPress MCP canonical relay plan")
    result_token = secrets.token_hex(32)
    envelope = {
        "schema_version": "1.0", "operation_id": op_id, "operation_kind": "relay_batch",
        "control_repository": REPO, "control_source_sha": control_sha,
        "execution_source_sha": execution_sha, "plan_ref": plan_path,
        "created_at": now, "expires_at": expires, "result_token": result_token,
    }
    # Persist identity before enqueue to avoid losing the status handle.
    HANDLES.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(HANDLES, 0o700)
    handle = hashlib.sha256((op_id + "\0" + result_token).encode()).hexdigest()
    mapping = HANDLES / (handle + ".json")
    with mapping.open("x", encoding="utf-8") as f:
        json.dump({"operation_id": op_id, "result_token_hash": hashlib.sha256(result_token.encode()).hexdigest()}, f)
    os.chmod(mapping, 0o600)
    create(f"control-plane/operations/inbox/{op_id}.json", envelope, "Queue WordPress MCP task via canonical Run Core relay")
    return {
        "status": "QUEUED", "request_handle": handle, "operation_id": op_id,
        "execution_architecture": "RUN_CORE_BOUND_RELAY_BATCH", "target_id": MCP_SCOPE,
        "github_actions_used": False, "secrets_emitted": False,
    }

def status(payload: dict) -> dict:
    handle = str(payload.get("request_handle") or "")
    if not SAFE_HANDLE.fullmatch(handle):
        raise Failure("WORDPRESS_EXECUTION_HANDLE_INVALID")
    mapping = HANDLES / (handle + ".json")
    if not mapping.is_file():
        return {"status": "NOT_FOUND", "request_handle": handle, "secrets_emitted": False}
    data = json.loads(mapping.read_text(encoding="utf-8"))
    op_id = data["operation_id"]
    try:
        result = fetch(f"control-plane/operations/results/{op_id}.json")
    except Failure as e:
        if e.code == "WORDPRESS_RELAY_GITHUB_NOT_FOUND":
            return {"status": "PENDING", "request_handle": handle, "operation_id": op_id, "secrets_emitted": False}
        raise
    if result.get("result_token_sha256") != data.get("result_token_hash"):
        raise Failure("WORDPRESS_RELAY_RESULT_TOKEN_MISMATCH")
    # Relay receipts contain sanitized statuses and bounded evidence.
    return {"status": result.get("status"), "request_handle": handle, "operation_id": op_id,
            "result": {k:v for k,v in result.items() if k not in {"result_token","credentials","secrets"}},
            "secrets_emitted": False}

def dispatch(request: dict) -> dict:
    action = str(request.get("action") or "")
    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        raise Failure("WORDPRESS_REQUEST_PAYLOAD_INVALID")
    if action == "CONNECTOR_HEALTH":
        return health()
    if action == "RUN_APPLICATION_WORKFLOW":
        return workflow(payload)
    if action == "EXECUTION_STATUS":
        return status(payload)
    if action == "DEPLOY_REGISTERED_SOURCE":
        raise Failure("WORDPRESS_SOURCE_DEPLOY_CONTRACT_NOT_REGISTERED")
    if action == "RUN_DATABASE_WORKFLOW":
        raise Failure("WORDPRESS_DATABASE_WRITE_CONTRACT_NOT_REGISTERED")
    raise Failure("WORDPRESS_ACTION_NOT_REGISTERED")

if __name__ == "__main__":
    try:
        req = json.load(sys.stdin)
        if not isinstance(req, dict):
            raise Failure("WORDPRESS_REQUEST_NOT_OBJECT")
        output = dispatch(req)
        print(json.dumps(output, sort_keys=True))
    except Failure as exc:
        print(json.dumps({"status":"FAIL_CLOSED","code":exc.code,"secrets_emitted":False},sort_keys=True))
        sys.exit(2)
    except Exception:
        print(json.dumps({"status":"FAIL_CLOSED","code":"WORDPRESS_RELAY_ADAPTER_INTERNAL_ERROR","secrets_emitted":False},sort_keys=True))
        sys.exit(2)
