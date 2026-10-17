#!/usr/bin/env python3
"""Public MCP presentation guard for canonical Project Brain deployment receipts.

No execution, filesystem reads, secret access or caller-supplied routes.
The authenticated Brain helper owns all verification.
"""
from __future__ import annotations
import re
from typing import Any
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SELF_OP = re.compile(r"^PB-PUBLIC-BRAIN-DEPLOY-[A-F0-9]{20}$")

def guard(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"status":"FAIL_CLOSED","failure_code":"PUBLIC_DEPLOY_RESPONSE_INVALID",
                "production_accepted":False}
    row=dict(response)
    op=row.get("operation_id")
    if not isinstance(op,str) or not _SELF_OP.fullmatch(op):
        return row
    if row.get("status")!="PASS":
        row["production_accepted"]=False
        return row
    verified=row.get("native_deploy_readback")
    sha=row.get("execution_source_sha")
    if (not isinstance(verified,dict)
            or verified.get("status")!="PASS"
            or verified.get("target_readback_verified") is not True
            or not isinstance(sha,str) or not _SHA.fullmatch(sha)
            or verified.get("active_source_sha")!=sha):
        row["production_accepted"]=False
        row["target_receipt_required"]=True
        row["target_completion"]={
            "run_core_pass_is_deployment_pass":False,
            "required_proof":"NATIVE_EXACT_SHA_RECEIPT_RUNSTORE_AND_PRODUCTION_READBACK",
        }
        return row
    # Native source cutover is proven but full CURRENT_STATE and service scope
    # acceptance remains a separate canonical step.
    row["target_receipt_required"]=False
    row["reconciliation_required"]=True
    row["production_accepted"]=False
    return row
