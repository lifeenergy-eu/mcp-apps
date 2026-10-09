#!/usr/bin/env python3
"""Source-only verifier for a preauthorized Project Brain target-local Run Core step.

This module does not issue tickets, select runners or execute a command.
It MUST NOT be wired into live mutation before canonical issuer, runtime trust,
durable replay store, target route and E2E acceptance have been registered.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any

ISSUER = "PROJECT-BRAIN-CONTROL-PLANE"
VERSION = "1"
REQUIRED = frozenset({
    "version", "issuer", "run_id", "step_id", "system_id", "target_id",
    "capability_id", "operation_profile", "source_sha", "payload_digest",
    "allowed_mutation_scope", "issued_at", "expires_at", "nonce",
    "dependency_receipts",
})
ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{7,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_LIFETIME = 300

class TicketDenied(ValueError):
    """Safe failure code. Never exposes private key or signed message."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TicketDenied("TICKET_CANONICAL_ENCODING_INVALID") from exc

def payload_digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()

def verify_ticket(
    envelope: Mapping[str, Any],
    *,
    runtime_trust_key: bytes,
    payload: Any,
    expected_system_id: str,
    expected_target_id: str,
    expected_capability_id: str,
    expected_operation_profile: str,
    expected_source_sha: str,
    expected_mutation_scope: Any,
    expected_dependency_receipts: list[str],
    dependency_receipt_verified: Callable[[str], bool] | None,
    durable_consume_nonce_once: Callable[[str, int, str, str], bool] | None,
    current_time: int | None = None,
) -> dict[str, Any]:
    """Validate only; caller retains Run Core authority and bound executor.

    The nonce consumer must atomically persist consumption until expiry.
    No mutation may run unless this function returns status PASS.
    """
    if not isinstance(envelope, Mapping) or set(envelope) != {"ticket", "signature"}:
        raise TicketDenied("TICKET_ENVELOPE_INVALID")
    ticket, signature = envelope["ticket"], envelope["signature"]
    if not isinstance(ticket, dict) or set(ticket) != REQUIRED:
        raise TicketDenied("TICKET_FIELDS_INVALID")
    if not isinstance(signature, str) or not SHA_RE.fullmatch(signature):
        raise TicketDenied("TICKET_SIGNATURE_FORMAT_INVALID")
    if not isinstance(runtime_trust_key, bytes) or len(runtime_trust_key) < 32:
        raise TicketDenied("TICKET_RUNTIME_TRUST_UNAVAILABLE")
    if durable_consume_nonce_once is None or not callable(durable_consume_nonce_once):
        raise TicketDenied("TICKET_DURABLE_REPLAY_GUARD_UNAVAILABLE")
    if ticket["version"] != VERSION or ticket["issuer"] != ISSUER:
        raise TicketDenied("TICKET_ISSUER_OR_VERSION_INVALID")
    for name in ("run_id", "step_id"):
        if not isinstance(ticket[name], str) or not ID_RE.fullmatch(ticket[name]):
            raise TicketDenied("TICKET_RUN_OR_STEP_INVALID")
    if not isinstance(ticket["nonce"], str) or not NONCE_RE.fullmatch(ticket["nonce"]):
        raise TicketDenied("TICKET_NONCE_INVALID")
    for name in ("system_id", "target_id", "capability_id", "operation_profile"):
        if not isinstance(ticket[name], str) or not ticket[name]:
            raise TicketDenied("TICKET_BINDING_INVALID")
    if not isinstance(ticket["source_sha"], str) or not SOURCE_RE.fullmatch(ticket["source_sha"]):
        raise TicketDenied("TICKET_SOURCE_SHA_INVALID")
    if not isinstance(ticket["payload_digest"], str) or not SHA_RE.fullmatch(ticket["payload_digest"]):
        raise TicketDenied("TICKET_PAYLOAD_DIGEST_INVALID")
    if not isinstance(ticket["issued_at"], int) or isinstance(ticket["issued_at"], bool):
        raise TicketDenied("TICKET_TIME_INVALID")
    if not isinstance(ticket["expires_at"], int) or isinstance(ticket["expires_at"], bool):
        raise TicketDenied("TICKET_TIME_INVALID")
    now = int(time.time()) if current_time is None else current_time
    if (not isinstance(now, int) or isinstance(now, bool) or
        ticket["issued_at"] > now + 30 or now >= ticket["expires_at"] or
        ticket["expires_at"] <= ticket["issued_at"] or
        ticket["expires_at"] - ticket["issued_at"] > MAX_LIFETIME):
        raise TicketDenied("TICKET_EXPIRED_OR_TIME_INVALID")
    expected = (
        ("system_id", expected_system_id), ("target_id", expected_target_id),
        ("capability_id", expected_capability_id),
        ("operation_profile", expected_operation_profile),
        ("source_sha", expected_source_sha),
    )
    if any(ticket[k] != value for k, value in expected):
        raise TicketDenied("TICKET_TARGET_OR_CAPABILITY_MISMATCH")
    if canonical_bytes(ticket["allowed_mutation_scope"]) != canonical_bytes(expected_mutation_scope):
        raise TicketDenied("TICKET_MUTATION_SCOPE_MISMATCH")
    if not hmac.compare_digest(ticket["payload_digest"], payload_digest(payload)):
        raise TicketDenied("TICKET_PAYLOAD_MISMATCH")
    deps = ticket["dependency_receipts"]
    if (not isinstance(deps, list) or
        any(not isinstance(v, str) or not ID_RE.fullmatch(v) for v in deps) or
        len(set(deps)) != len(deps) or
        deps != expected_dependency_receipts):
        raise TicketDenied("TICKET_DEPENDENCIES_MISMATCH")
    if deps and (dependency_receipt_verified is None or
                 any(dependency_receipt_verified(dep) is not True for dep in deps)):
        raise TicketDenied("TICKET_DEPENDENCIES_NOT_VERIFIED")
    expected_signature = hmac.new(runtime_trust_key, canonical_bytes(ticket), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise TicketDenied("TICKET_SIGNATURE_INVALID")
    try:
        consumed = durable_consume_nonce_once(ticket["nonce"], ticket["expires_at"],
                                              ticket["run_id"], ticket["step_id"])
    except Exception as exc:
        raise TicketDenied("TICKET_DURABLE_REPLAY_GUARD_FAILED") from exc
    if consumed is not True:
        raise TicketDenied("TICKET_NONCE_REPLAY_OR_GUARD_FAILED")
    return {
        "status": "PASS",
        "run_id": ticket["run_id"],
        "step_id": ticket["step_id"],
        "system_id": ticket["system_id"],
        "target_id": ticket["target_id"],
        "capability_id": ticket["capability_id"],
        "operation_profile": ticket["operation_profile"],
        "source_sha": ticket["source_sha"],
        "expires_at": ticket["expires_at"],
    }
