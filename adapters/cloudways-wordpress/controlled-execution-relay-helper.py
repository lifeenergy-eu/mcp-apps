#!/usr/bin/env python3
"""WordPress WRITE MCP: credential-free ChatGPT GitHub Direct handoff.

The operator's authenticated ChatGPT GitHub Direct connector submits canonical
relay_batch requests to Project Brain. This target-scoped MCP validates and
returns typed intents; it does not pretend to execute them on the WordPress
host and never creates an alternate Run Core, SSH/HTTP mutation route or token.
"""
from __future__ import annotations
import json
import re
import sys
from typing import Any

TARGET = "SERVER-CLOUDWAYS-WORDPRESS"
WORKFLOWS = {
    "WORDPRESS_CAPABILITY_PROBE_V1": "capability_probe",
    "WORDPRESS_CACHE_INSPECT_V1": "filesystem_cleanup",
}
CACHE_TARGETS = {"cache", "breeze_cache", "debug_log", "upgrade_temp"}
APP_RE = re.compile(r"^[a-z0-9]{8,16}$")
ID_RE = re.compile(r"^WP-MCP-[A-Z0-9_.-]{8,70}$")

class Denied(Exception):
    pass

def fail(code: str) -> dict[str, Any]:
    return {"status": "FAIL_CLOSED", "code": code, "secrets_emitted": False}

def health() -> dict[str, Any]:
    return {
        "status": "PASS",
        "target_id": TARGET,
        "transport": "OTB_PLATFORM_PRIVATE_MCP",
        "execution_binding": "CHATGPT_GITHUB_DIRECT_TO_CANONICAL_RUN_CORE",
        "write_backend": "CHATGPT_COORDINATED_GITHUB_RELAY",
        "native_execution_connected": False,
        "credential_on_wordpress_required": False,
        "registered_workflows": sorted(WORKFLOWS),
        "read_mcp_separate": True,
        "arbitrary_shell": False,
        "raw_sql": False,
        "secrets_emitted": False,
    }

def application(payload: dict[str, Any]) -> dict[str, Any]:
    workflow_id = str(payload.get("workflow_id") or "")
    action = WORKFLOWS.get(workflow_id)
    if not action:
        raise Denied("WORDPRESS_WORKFLOW_NOT_REGISTERED")
    operation = payload.get("operation")
    if not isinstance(operation, dict):
        raise Denied("WORDPRESS_WORKFLOW_OPERATION_INVALID")
    app_id = operation.get("app_id")
    if not isinstance(app_id, str) or not APP_RE.fullmatch(app_id):
        raise Denied("WORDPRESS_APPLICATION_ID_INVALID")
    if action == "capability_probe":
        if set(operation) != {"app_id"}:
            raise Denied("WORDPRESS_CAPABILITY_PROBE_FIELDS_FORBIDDEN")
        mutation = {"action": action, "app_id": app_id}
    else:
        if set(operation) != {"app_id", "targets", "dry_run"}:
            raise Denied("WORDPRESS_CACHE_INSPECT_FIELDS_INVALID")
        targets = operation.get("targets")
        if not isinstance(targets, list) or not targets or len(targets) > 4:
            raise Denied("WORDPRESS_CACHE_INSPECT_TARGETS_INVALID")
        if any(not isinstance(v, str) or v not in CACHE_TARGETS for v in targets):
            raise Denied("WORDPRESS_CACHE_INSPECT_TARGET_NOT_ALLOWED")
        if len(set(targets)) != len(targets) or operation.get("dry_run") is not True:
            raise Denied("WORDPRESS_CACHE_INSPECT_MUST_BE_DRY_RUN")
        mutation = {"action": action, "app_id": app_id, "targets": targets, "dry_run": True}
    return {
        "status": "HANDOFF_REQUIRED",
        "code": "CHATGPT_GITHUB_DIRECT_RELAY_EXECUTION",
        "system_id": "SYSTEM-WORDPRESS",
        "target_id": TARGET,
        "workflow_id": workflow_id,
        "capability": "MUTATE_WORDPRESS_APPLICATION_GUARDED_WORKFLOW",
        "relay_operation_kind": "wordpress_application_mutation",
        "canonical_plan_profile": "WORDPRESS_APPLICATION_MUTATION_V1",
        "canonical_orchestration": "PB_RELAY_BATCH_V1",
        "mutation": mutation,
        "handoff_instructions": (
            "ChatGPT: resolve app_id against current Project Brain systems/wordpress.json "
            "and capability against canonical owners; submit a relay_batch plan and inbox "
            "through connected GitHub Direct using exact canonical SHA; read the "
            "result from control-plane/operations/results; never execute locally."
        ),
        "secrets_emitted": False,
    }

def status(payload: dict[str, Any]) -> dict[str, Any]:
    op_id = payload.get("request_handle")
    if not isinstance(op_id, str) or not ID_RE.fullmatch(op_id):
        raise Denied("WORDPRESS_RELAY_OPERATION_ID_INVALID")
    return {
        "status": "HANDOFF_REQUIRED",
        "code": "CHATGPT_GITHUB_DIRECT_READBACK",
        "operation_id": op_id,
        "result_ref": "control-plane/operations/results/" + op_id + ".json",
        "secrets_emitted": False,
    }

def dispatch(req: dict[str, Any]) -> dict[str, Any]:
    action = req.get("action")
    payload = req.get("payload") or {}
    if not isinstance(payload, dict):
        raise Denied("WORDPRESS_PAYLOAD_INVALID")
    if action == "CONNECTOR_HEALTH":
        return health()
    if action == "RUN_APPLICATION_WORKFLOW":
        return application(payload)
    if action == "EXECUTION_STATUS":
        return status(payload)
    if action == "DEPLOY_REGISTERED_SOURCE":
        raise Denied("WORDPRESS_SOURCE_DEPLOY_NOT_REGISTERED")
    if action == "RUN_DATABASE_WORKFLOW":
        raise Denied("WORDPRESS_DATABASE_WRITE_NOT_REGISTERED")
    raise Denied("WORDPRESS_ACTION_NOT_REGISTERED")

def main() -> int:
    try:
        req = json.load(sys.stdin)
        if not isinstance(req, dict):
            raise Denied("WORDPRESS_REQUEST_NOT_OBJECT")
        print(json.dumps(dispatch(req), sort_keys=True))
        return 0
    except Denied as exc:
        print(json.dumps(fail(str(exc)), sort_keys=True))
        return 2
    except Exception:
        print(json.dumps(fail("WORDPRESS_HANDOFF_HELPER_FAILED"), sort_keys=True))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
