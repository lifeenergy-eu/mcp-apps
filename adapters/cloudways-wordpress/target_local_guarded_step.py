#!/usr/bin/env python3
"""WordPress target-local bounded executor for a signed, registered Run Core step.

SOURCE ONLY. Not installed, advertised as MCP action, or activated by importing.
Run Core remains the sole source of authorization. Host deployment and trust
provisioning are separate registered activation steps; absent trust fails closed.
Only the existing fixed PHP WordPress runner may execute a mutation.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
from typing import Any

BASE = Path("/home/master/.project-brain/controlled-execution-mcp-wordpress")
KEY_FILE = BASE / "secrets" / "target-local-hmac-key"
VERIFIER_FILE = BASE / "trusted" / "target_local_ticket.py"
NONCE_FILE = BASE / "state" / "target-local-nonce.sqlite3"
RUNNER = Path("/home/master/.project-brain/server-control-runtime/current/remote/remote_runner.php")
PHP = "/usr/bin/php"
APP_RE = re.compile(r"^[a-z0-9]{8,16}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_CACHE = frozenset({"cache", "breeze_cache", "debug_log", "upgrade_temp"})


class TargetLocalDenied(RuntimeError):
    pass


def deny(code: str) -> None:
    raise TargetLocalDenied(code)


def private_file(path: Path, *, min_bytes: int = 1) -> bytes:
    if path.is_symlink() or not path.is_file():
        deny("WORDPRESS_LOCAL_TRUST_FILE_UNAVAILABLE")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        deny("WORDPRESS_LOCAL_TRUST_FILE_INSECURE")
    if path.parent.is_symlink() or not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        deny("WORDPRESS_LOCAL_TRUST_DIRECTORY_INSECURE")
    value = path.read_bytes()
    if len(value) < min_bytes or len(value) > 65536:
        deny("WORDPRESS_LOCAL_TRUST_FILE_INVALID")
    return value


def load_verifier():
    if VERIFIER_FILE.is_symlink() or not VERIFIER_FILE.is_file():
        deny("WORDPRESS_LOCAL_VERIFIER_NOT_INSTALLED")
    if VERIFIER_FILE.stat().st_mode & 0o022:
        deny("WORDPRESS_LOCAL_VERIFIER_WRITABLE_BY_UNTRUSTED_USER")
    spec = importlib.util.spec_from_file_location("pb_wordpress_pinned_target_local_ticket", VERIFIER_FILE)
    if not spec or not spec.loader:
        deny("WORDPRESS_LOCAL_VERIFIER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "verify_ticket", None)):
        deny("WORDPRESS_LOCAL_VERIFIER_INVALID")
    return module


def mutation_scope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        deny("WORDPRESS_LOCAL_PAYLOAD_INVALID")
    action = payload.get("action")
    app_id = payload.get("app_id")
    if not isinstance(app_id, str) or not APP_RE.fullmatch(app_id):
        deny("WORDPRESS_LOCAL_APP_UNREGISTERED")
    if action == "capability_probe":
        if set(payload) != {"action", "app_id"}:
            deny("WORDPRESS_LOCAL_MUTATION_FIELDS_FORBIDDEN")
        return {"action": action, "app_id": app_id}
    if action == "filesystem_cleanup":
        if set(payload) != {"action", "app_id", "targets", "dry_run"} or payload["dry_run"] is not True:
            deny("WORDPRESS_LOCAL_CACHE_MUST_BE_DRY_RUN")
        targets = payload["targets"]
        if (not isinstance(targets, list) or not 1 <= len(targets) <= 4
            or any(not isinstance(x, str) or x not in ALLOWED_CACHE for x in targets)
            or len(targets) != len(set(targets))):
            deny("WORDPRESS_LOCAL_CACHE_TARGET_FORBIDDEN")
        return {"action": action, "app_id": app_id, "targets": targets, "dry_run": True}
    deny("WORDPRESS_LOCAL_WORKFLOW_NOT_REGISTERED")


def consume_once(nonce: str, expiry: int, run_id: str, step_id: str) -> bool:
    if (NONCE_FILE.is_symlink() or NONCE_FILE.parent.is_symlink()
        or not NONCE_FILE.parent.is_dir() or NONCE_FILE.parent.stat().st_mode & 0o077):
        deny("WORDPRESS_LOCAL_PRIVATE_NONCE_STORE_UNAVAILABLE")
    if NONCE_FILE.exists() and (not NONCE_FILE.is_file() or NONCE_FILE.stat().st_mode & 0o077):
        deny("WORDPRESS_LOCAL_PRIVATE_NONCE_STORE_UNSAFE")
    previous_mask = os.umask(0o077)
    try:
        connection = sqlite3.connect(str(NONCE_FILE), timeout=5, isolation_level=None)
    except sqlite3.Error:
        deny("WORDPRESS_LOCAL_PRIVATE_NONCE_STORE_FAILED")
    finally:
        os.umask(previous_mask)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS consumed ("
            "nonce TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT NOT NULL,"
            "expires_at INTEGER NOT NULL, UNIQUE (run_id,step_id))"
        )
        inserted = connection.execute(
            "INSERT OR IGNORE INTO consumed (nonce,run_id,step_id,expires_at) VALUES (?,?,?,?)",
            (nonce, run_id, step_id, expiry)
        )
        connection.execute("COMMIT")
        return inserted.rowcount == 1
    except sqlite3.Error:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        deny("WORDPRESS_LOCAL_PRIVATE_NONCE_STORE_FAILED")
    finally:
        connection.close()


def guarded_php_call(mutation: dict[str, Any]) -> dict[str, Any]:
    if RUNNER.is_symlink() or not RUNNER.is_file() or not os.access(RUNNER, os.R_OK):
        deny("WORDPRESS_LOCAL_REGISTERED_RUNNER_UNAVAILABLE")
    if RUNNER.stat().st_mode & 0o022:
        deny("WORDPRESS_LOCAL_REGISTERED_RUNNER_UNSAFE")
    raw = json.dumps({"mode": "wordpress_mutation", "mutation": mutation},
                     separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) > 20000:
        deny("WORDPRESS_LOCAL_MUTATION_TOO_LARGE")
    try:
        completed = subprocess.run(
            [PHP, str(RUNNER)], input=base64.b64encode(raw),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
            check=False, shell=False,
        )
        envelope = json.loads(completed.stdout.decode("utf-8"))
        if completed.returncode or envelope.get("rc") != 0:
            deny("WORDPRESS_LOCAL_REGISTERED_RUNNER_REJECTED")
        result = json.loads(envelope["stdout"])
        if (not isinstance(result, dict) or result.get("status") != "PASS"
            or result.get("action") != mutation["action"]
            or result.get("app_id") != mutation["app_id"]):
            deny("WORDPRESS_LOCAL_REGISTERED_RECEIPT_INVALID")
        return result
    except (ValueError, KeyError, UnicodeError, subprocess.SubprocessError, OSError):
        deny("WORDPRESS_LOCAL_REGISTERED_EXECUTION_FAILED")


def execute_preauthorized_step(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) != {"ticket_envelope", "mutation"}:
        deny("WORDPRESS_LOCAL_REQUEST_FIELDS_FORBIDDEN")
    payload = request["mutation"]
    scope = mutation_scope(payload)
    signed = request["ticket_envelope"]
    if not isinstance(signed, dict):
        deny("WORDPRESS_LOCAL_TICKET_INVALID")
    ticket = signed.get("ticket")
    if not isinstance(ticket, dict):
        deny("WORDPRESS_LOCAL_TICKET_INVALID")
    # TL3 initial admission is single-step; never assert unverified cross-host dependencies.
    if ticket.get("dependency_receipts") != []:
        deny("WORDPRESS_LOCAL_DEPENDENCY_RECEIPTS_NOT_AVAILABLE")
    sha = os.environ.get("PB_CONTROL_EXACT_SOURCE_SHA", "")
    if not SHA40.fullmatch(sha):
        deny("WORDPRESS_LOCAL_TRUSTED_SOURCE_IDENTITY_UNAVAILABLE")
    if os.environ.get("PB_WORDPRESS_TARGET_LOCAL_ENABLED") != "1":
        deny("WORDPRESS_LOCAL_CUTOVER_NOT_AUTHORIZED")
    key = private_file(KEY_FILE, min_bytes=32)
    verifier = load_verifier()
    try:
        verified = verifier.verify_ticket(
            signed, runtime_trust_key=key, payload=payload,
            expected_system_id="SYSTEM-WORDPRESS",
            expected_target_id="wordpress-production",
            expected_capability_id="MUTATE_WORDPRESS_APPLICATION_GUARDED_WORKFLOW",
            expected_operation_profile="WORDPRESS_APPLICATION_MUTATION_V1",
            expected_source_sha=sha, expected_mutation_scope=scope,
            expected_dependency_receipts=[],
            dependency_receipt_verified=lambda _: False,
            durable_consume_nonce_once=consume_once,
        )
    except Exception:
        deny("WORDPRESS_LOCAL_TICKET_VERIFICATION_DENIED")
    if verified.get("status") != "PASS":
        deny("WORDPRESS_LOCAL_TICKET_VERIFICATION_DENIED")
    # Nonce was durably consumed before entering the registered PHP runner.
    result = guarded_php_call(payload)
    receipt = {
        "status": "PASS", "execution_authority": "PROJECT-BRAIN-CONTROL-PLANE",
        "target_id": "SERVER-CLOUDWAYS-WORDPRESS",
        "run_id": ticket["run_id"], "step_id": ticket["step_id"],
        "source_sha": sha, "action": payload["action"],
        "app_id": payload["app_id"],
        "receipt_sha256": hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(), "secrets_emitted": False,
    }
    if payload["action"] == "capability_probe":
        receipt["write_verified"] = result.get("write_verified") is True
        receipt["cleanup_verified"] = result.get("cleanup_verified") is True
    return receipt


def main() -> int:
    try:
        req = json.load(sys.stdin)
        result = execute_preauthorized_step(req)
        print(json.dumps(result, sort_keys=True))
        return 0
    except TargetLocalDenied as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "code": str(exc),
                          "secrets_emitted": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "FAIL_CLOSED",
                          "code": "WORDPRESS_LOCAL_EXECUTOR_INTERNAL_ERROR",
                          "secrets_emitted": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
