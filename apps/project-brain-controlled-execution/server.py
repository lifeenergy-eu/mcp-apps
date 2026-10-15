#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
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

from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

VERSION = "0.1.1"
RO = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _optional(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


HOST = _optional("MCP_BIND_HOST", "127.0.0.1")
PORT = int(_optional("MCP_BIND_PORT", "8793"))
PUBLIC_HOST = _required("MCP_PUBLIC_HOST")
HELPER = _required("PB_CONTROLLED_EXECUTION_HELPER")


class PluginFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        # The Brain MCP exposes exactly one ChatGPT-facing execution tool.
        # Legacy handlers remain defined only to respond to stale tool callers.
        allowed = {"brain_execute", "brain_source_mutate", "brain_operation_status", "brain_develop"}
        tools = [tool for tool in tools if tool.name in allowed]
        if AUTH_MODE != "oauth_private":
            return tools
        schemes = [{"type": "oauth2", "scopes": OAUTH_SCOPES}]
        out = []
        for tool in tools:
            meta = dict(tool.meta or {})
            meta["securitySchemes"] = schemes
            out.append(tool.model_copy(update={"meta": meta, "securitySchemes": schemes}))
        return out


security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", PUBLIC_HOST, f"{PUBLIC_HOST}:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", f"https://{PUBLIC_HOST}", f"https://{PUBLIC_HOST}:*"],
)

mcp = PluginFastMCP(
    "project-brain-controlled-execution",
    instructions=(
        "Project Brain Controlled Execution. Public deploy input: repository and commit_sha only. Execution authority remains in "
        "Project Brain capability contracts, Run Core and existing deterministic executors. "
        "No arbitrary shell, caller-selected runner, target, filesystem root, raw SQL or raw HTTP."
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


def helper_call(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = {"action": action, "payload": payload or {}}
    proc = subprocess.run(
        ["/usr/bin/python3", HELPER],
        input=json.dumps(request, separators=(",", ":")),
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_EMPTY_RESPONSE")
    try:
        body = json.loads(raw.splitlines()[-1])
    except Exception as exc:
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_INVALID_RESPONSE") from exc
    if not isinstance(body, dict):
        raise RuntimeError("CONTROLLED_EXECUTION_HELPER_RESPONSE_NOT_OBJECT")
    return body


@mcp.tool(annotations=RO)
def connector_health() -> dict[str, Any]:
    """Return Controlled Execution MCP health and enforced execution posture."""
    body = helper_call("CONNECTOR_HEALTH")
    body["connector_version"] = VERSION
    body["authentication"] = "oauth2-private-single-user"
    body["oauth_scopes"] = OAUTH_SCOPES
    body["mcp_path"] = "/mcp"
    body["primary_execution_tool"] = "brain_execute"
    body["public_tools"] = ["brain_source_mutate", "brain_execute", "brain_operation_status"]
    body["public_execution_tool_count"] = 3
    body["legacy_write_tools"] = "HANDOFF_REQUIRED_USE_BRAIN_EXECUTE"
    body["canonical_deploy_policy_ref"] = "control-plane/PROJECT_EXECUTION_POLICY.json#execution.commit_and_deploy.final_operating_model_v1.canonical_delivery_pipeline_v1"
    return body


def _legacy_handoff(action: str) -> dict[str, Any]:
    """A stale legacy tool call never executes; tell ChatGPT its next action."""
    return {
        "status": "HANDOFF_REQUIRED",
        "code": "USE_BRAIN_EXECUTE",
        "origin_surface": "PROJECT_BRAIN_MCP",
        "blocked_action": action,
        "next_surface": "PROJECT_BRAIN_MCP",
        "next_tool": "brain_execute",
        "required_next_action": "RESUBMIT_REPOSITORY_AND_COMMIT_SHA",
        "message": "This compatibility tool no longer executes. Use brain_execute with repository and commit_sha.",
        "retry_same_tool": False,
        "execution_performed": False,
        "secrets_emitted": False,
    }


@mcp.tool(annotations=WRITE)
def deploy_registered_source(
    system_id: str,
    source_sha: str,
    repository: str = "",
    paths: list[str] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Deploy one exact SHA through a registered system deployment contract."""
    return _legacy_handoff("DEPLOY_REGISTERED_SOURCE")

@mcp.tool(annotations=WRITE)
def run_registered_application_workflow(
    workflow_id: str,
    operation: dict[str, Any],
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named registered application workflow through Project Brain."""
    return _legacy_handoff("RUN_APPLICATION_WORKFLOW")

@mcp.tool(annotations=WRITE)
def run_registered_database_workflow(
    database_contract_id: str,
    payload: dict[str, Any] | None = None,
    wait_seconds: int = 8,
) -> dict[str, Any]:
    """Run one named database contract. Unknown contracts and raw SQL/table selection fail closed."""
    return _legacy_handoff("RUN_DATABASE_WORKFLOW")

@mcp.tool(annotations=WRITE)
def run_registered_task(task: dict[str, Any], wait_seconds: int = 8) -> dict[str, Any]:
    """Send only a registered task intent to Project Brain; no runner, SHA, target or plan."""
    return _legacy_handoff("RUN_REGISTERED_TASK")

@mcp.tool(annotations=WRITE)
def brain_source_mutate(
    repository: str, base_sha: str, commit_message: str,
    idempotency_key: str, operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Commit registered repository source through canonical HMAC V2 Run Core.

    Never deploys and never accepts a raw runner, plan, target or secret.
    """
    return helper_call("PUBLIC_SOURCE_MUTATION", {
        "repository": repository, "base_sha": base_sha,
        "commit_message": commit_message, "idempotency_key": idempotency_key,
        "operations": operations,
    })


@mcp.tool(annotations=RO)
def brain_operation_status(operation_id: str) -> dict[str, Any]:
    """Read a durable Run Core receipt or fixed Brain self-deploy operation."""
    return helper_call("PUBLIC_OPERATION_STATUS", {"operation_id": operation_id})


@mcp.tool(annotations=WRITE)
def brain_execute(repository: str, commit_sha: str) -> dict[str, Any]:
    """Deploy one registered GitHub repository at an exact 40-character commit SHA.

    Brain resolves the internal execution plan, targets, prerequisites and
    verification. No task_id, intent_key, runner or steps are caller inputs.
    """
    return helper_call("RUN_REGISTERED_TASK", {
        "task": {"repository": repository, "commit_sha": commit_sha},
        "wait_seconds": 8,
    })


def _verified_github_direct_source(repository: str, commit_sha: str,
                                   changes: list[dict[str, str]]) -> str:
    """Read only an allowlisted GitHub checkout; never commit or deploy."""
    if repository != "lifeenergy-eu/mcp-apps":
        return "DEV_READBACK_REPOSITORY_NOT_REGISTERED"
    checkout = Path("/home/master/.project-brain/releases/mcp-apps-latest")
    if not (checkout / ".git").is_dir():
        return "DEV_GITHUB_CHECKOUT_UNAVAILABLE"
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    def git(*argv: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(checkout), *argv],
            stderr=subprocess.DEVNULL, timeout=20, env=env,
        ).decode("utf-8")
    try:
        remote = git("remote", "get-url", "origin").strip()
        if remote not in (
            "https://github.com/lifeenergy-eu/mcp-apps.git",
            "git@github.com:lifeenergy-eu/mcp-apps.git",
        ):
            return "DEV_GITHUB_REMOTE_MISMATCH"
        head = git("ls-remote", "--heads", "origin", "main").split()
        if not head:
            return "DEV_GITHUB_HEAD_UNAVAILABLE"
        git("fetch", "--no-tags", "origin", commit_sha)
        if head[0] != commit_sha:
            git("fetch", "--no-tags", "origin", head[0])
            ancestry = subprocess.run(
                ["git", "-C", str(checkout), "merge-base", "--is-ancestor",
                 commit_sha, head[0]], env=env, timeout=20,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ancestry.returncode != 0:
                return "DEV_GITHUB_HEAD_MISMATCH"
            message = git("show", "-s", "--format=%B", head[0])
            if ("PB-Idempotency-Key: udv2-dev-" not in message or
                    "PB-Attestation-Version: 2" not in message or
                    "PB-Source-Attestation: hmac-sha256:" not in message):
                return "DEV_GITHUB_HEAD_MISMATCH"
        for change in changes:
            # Git's blob contents, not supplied client proof, are authoritative.
            content = subprocess.check_output(
                ["git", "-C", str(checkout), "show",
                 commit_sha + ":" + change["path"]],
                stderr=subprocess.DEVNULL, timeout=20, env=env,
            )
            if content != change["content"].encode("utf-8"):
                return "DEV_GITHUB_TREE_CONTENT_MISMATCH"
        return "PASS"
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return "DEV_GITHUB_READBACK_UNAVAILABLE"


@mcp.tool(annotations=WRITE)
def brain_develop(repository: str, intent: str,
                  changes: list[dict[str, str]] | None = None,
                  existing_sha: str | None = None,
                  checkpoint: dict[str, str] | None = None) -> dict[str, Any]:
    """Single ChatGPT entrypoint for a registered exact-SHA release.

    Source changes are committed through the official GitHub Direct app.
    For an existing signed SHA, reuse the active Brain deploy route.
    Brain owns the target, execution, verification, and durable receipt.
    """
    if not isinstance(intent, str) or not intent.strip() or len(intent) > 1000:
        return {"status": "FAIL_CLOSED", "failure_code": "DEV_INTENT_INVALID"}
    if changes is None and existing_sha is None:
        return {"status": "FAIL_CLOSED", "failure_code": "DEV_SELECT_CHANGES_OR_EXISTING_SHA"}
    if checkpoint is not None:
        if changes is None or existing_sha is None:
            return {"status": "FAIL_CLOSED", "failure_code": "DEV_RESUME_INPUTS_REQUIRED"}
        if not isinstance(checkpoint, dict) or set(checkpoint) != {"request_id", "github_commit_sha"}:
            return {"status": "FAIL_CLOSED", "failure_code": "DEV_RESUME_PROOF_INVALID"}
        if (checkpoint["github_commit_sha"] != existing_sha or
                not isinstance(existing_sha, str) or
                re.fullmatch(r"[0-9a-f]{40}", existing_sha) is None):
            return {"status": "FAIL_CLOSED", "failure_code": "DEV_RESUME_SHA_MISMATCH"}
    elif changes is not None and existing_sha is not None:
        return {"status": "FAIL_CLOSED", "failure_code": "DEV_CHECKPOINT_RESUME_PROOF_REQUIRED"}

    if changes is not None:
        # GitHub Direct is the sole authorized source writer. The digest is a
        # deterministic resumable checkpoint identity, not a commit or proof.
        if not isinstance(repository, str) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            return {"status": "FAIL_CLOSED", "failure_code": "DEV_REPOSITORY_INVALID"}
        if not isinstance(changes, list) or not 1 <= len(changes) <= 64:
            return {"status": "FAIL_CLOSED", "failure_code": "DEV_CHANGES_INVALID"}
        seen = set()
        for change in changes:
            if not isinstance(change, dict) or set(change) != {"path", "operation", "content"}:
                return {"status": "FAIL_CLOSED", "failure_code": "DEV_CHANGE_FIELDS_INVALID"}
            path, operation, content = (change["path"], change["operation"], change["content"])
            if operation not in ("create", "replace") or not isinstance(path, str) or not isinstance(content, str):
                return {"status": "FAIL_CLOSED", "failure_code": "DEV_CHANGE_INVALID"}
            if (not path or path.startswith("/") or chr(92) in path
                    or len(path) > 240 or path in seen
                    or any(segment in ("", ".", "..") for segment in path.split("/"))
                    or len(content.encode("utf-8")) > 1048576):
                return {"status": "FAIL_CLOSED", "failure_code": "DEV_CHANGE_BOUNDARY_INVALID"}
            seen.add(path)
        canonical = json.dumps({"repository": repository, "intent": intent,
                                "changes": changes}, sort_keys=True, separators=(",", ":"))
        request_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if checkpoint is not None:
            if checkpoint.get("request_id") != request_id:
                return {"status": "FAIL_CLOSED", "failure_code": "DEV_RESUME_REQUEST_MISMATCH"}
            readback = _verified_github_direct_source(repository, existing_sha, changes)
            if readback != "PASS":
                return {"status": "FAIL_CLOSED", "failure_code": readback,
                        "request_id": request_id, "production_accepted": False}
            # Existing HMAC V2 Run Core capability signs the GitHub Direct
            # source tree; this is NOT a general-purpose source commit writer.
            result = helper_call("PUBLIC_SOURCE_MUTATION", {
                "repository": repository,
                "base_sha": existing_sha,
                "commit_message": "UDV2 signed verified development request " + request_id[:20],
                "idempotency_key": "udv2-dev-" + request_id[:40],
                "operations": [
                    {"action": "replace", "path": change["path"],
                     "content": change["content"]} for change in changes
                ],
            })
            if not isinstance(result, dict) or result.get("status") not in ("QUEUED", "PENDING", "PASS"):
                return {"status": "FAIL_CLOSED", "failure_code": "DEV_HMAC_SUBMISSION_FAILED",
                        "request_id": request_id, "production_accepted": False}
            return {
                "status": result["status"],
                "code": "DEV_HMAC_V2_RUN_CORE_SUBMITTED",
                "request_id": request_id,
                "github_commit_sha": existing_sha,
                "hmac_request_handle": result.get("request_handle"),
                "hmac_receipt_ref": result.get("durable_result_ref"),
                "next_action": "POLL_HMAC_STATUS_VERIFY_SIGNED_GITHUB_SHA_THEN_BRAIN_EXECUTE",
                "git_source_verified": True,
                "execution_performed": False,
                "production_accepted": False,
            }
        return {
            "status": "HANDOFF_REQUIRED",
            "code": "DEV_GITHUB_DIRECT_COMMIT_REQUIRED",
            "request_id": request_id,
            "checkpoint_schema": "UDV2_GITHUB_DIRECT_HANDOFF_V1",
            "checkpoint_state": "AWAITING_OFFICIAL_GITHUB_DIRECT_COMMIT",
            "resume_requirements": {
                "github_commit_sha": "ACTUAL_40_HEX_SHA_FROM_GITHUB_DIRECT",
                "signed_sha": "ONLY_AFTER_SEPARATE_REGISTERED_HMAC_V2_PASS",
                "source_identity": request_id,
                "readback": "VERIFY_GITHUB_HEAD_AND_CHANGED_FILE_CONTENT_BEFORE_SIGNING"
            },
            "next_tool": "GitHub Direct",
            "required_next_action": "COMMIT_VALIDATED_CHANGES_THEN_RESUBMIT_SIGNED_SHA",
            "repository": repository,
            "change_count": len(changes),
            "execution_performed": False,
            "production_accepted": False,
            "secrets_emitted": False,
        }
    if not isinstance(existing_sha, str) or re.fullmatch(r"[0-9a-f]{40}", existing_sha) is None:
        return {"status": "FAIL_CLOSED", "failure_code": "DEV_SOURCE_SHA_INVALID"}
    # This is a deploy submission, not a claim of production acceptance.
    # Poll brain_operation_status and verify real target identity separately.
    result = helper_call("RUN_REGISTERED_TASK", {
        "task": {"repository": repository, "commit_sha": existing_sha},
        "wait_seconds": 8,
    })
    if not isinstance(result, dict):
        raise RuntimeError("DEV_BRAIN_DEPLOY_RESULT_INVALID")
    result["development_entrypoint"] = "brain_develop"
    result["requested_source_sha"] = existing_sha
    return result

@mcp.tool(annotations=RO)
def execution_status(request_handle: str) -> dict[str, Any]:
    """Read the bounded result status for one Controlled Execution request handle."""
    return helper_call("EXECUTION_STATUS", {"request_handle": request_handle})


def main() -> None:
    uvicorn.run(mcp.streamable_http_app(), host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
