#!/usr/bin/env python3
"""P620 scoped MCP transport adapter: typed GitHub Direct relay handoff only."""
import json
import re
import sys

TARGET = "P620"
SHA = re.compile(r"^[0-9a-f]{40}$")
HANDLE = re.compile(r"^P620-MCP-[A-Z0-9_.-]{8,70}$")

def fail(code):
    return {"status":"FAIL_CLOSED","code":code,"secrets_emitted":False}

def dispatch(req):
    if not isinstance(req,dict):
        return fail("INVALID_REQUEST")
    action=req.get("action")
    payload=req.get("payload") or {}
    if not isinstance(payload,dict):
        return fail("INVALID_PAYLOAD")
    if action=="CONNECTOR_HEALTH":
        return {"status":"PASS","target_id":TARGET,"transport":"P620_LOOPBACK_ONLY","execution_binding":"CHATGPT_GITHUB_DIRECT_TO_CANONICAL_RUN_CORE","write_backend":"CHATGPT_COORDINATED_GITHUB_RELAY","native_execution_connected":False,"direct_inbound_mutation":False,"credential_on_p620_required":False,"read_mcp_separate":True,"arbitrary_shell":False,"raw_sql":False,"registered_operations":["DEPLOY_P620_RUNTIME_FROM_GITHUB"],"secrets_emitted":False}
    if action=="DEPLOY_REGISTERED_SOURCE":
        sha=payload.get("source_sha")
        if payload.get("system_id")!="SYSTEM-LOCAL-AI" or not isinstance(sha,str) or not SHA.fullmatch(sha):
            return fail("P620_DEPLOY_TARGET_OR_SHA_INVALID")
        if payload.get("repository") not in ("","lifeenergy-eu/p620-ai-runtime",None) or payload.get("paths") not in ([],None):
            return fail("P620_DEPLOY_SOURCE_OR_PATHS_NOT_ALLOWED")
        return {"status":"HANDOFF_REQUIRED","code":"BRAIN_MCP_EXECUTION_REQUIRED","next_plugin":"Project Brain MCP","next_tool":"brain_execute","next_intent_key":"P620_RUNTIME_DEPLOY","next_intent_inputs":{"p620_runtime_sha":sha},"execution_performed":False,"target_id":TARGET,"system_id":"SYSTEM-LOCAL-AI","capability":"DEPLOY_P620_RUNTIME_FROM_GITHUB","source_sha":sha,"source_repository":"lifeenergy-eu/p620-ai-runtime","canonical_execution":"PB_RELAY_BATCH_V1","execution_authority":"PROJECT-BRAIN-CONTROL-PLANE","instructions":"Use Project Brain MCP brain_execute with P620_RUNTIME_DEPLOY intent. Brain resolves Run Core and the registered execution route; no inbound P620 execution.","secrets_emitted":False}
    if action=="EXECUTION_STATUS":
        handle=payload.get("request_handle")
        if not isinstance(handle,str) or not HANDLE.fullmatch(handle):
            return fail("P620_RELAY_HANDLE_INVALID")
        return {"status":"HANDOFF_REQUIRED","code":"CHATGPT_GITHUB_DIRECT_READBACK","operation_id":handle,"result_ref":"control-plane/operations/results/"+handle+".json","secrets_emitted":False}
    if action=="RUN_APPLICATION_WORKFLOW":
        return fail("P620_APPLICATION_WORKFLOW_NOT_REGISTERED")
    if action=="RUN_DATABASE_WORKFLOW":
        return fail("P620_DATABASE_WRITE_NOT_REGISTERED")
    return fail("P620_ACTION_NOT_REGISTERED")

def main():
    try:
        result=dispatch(json.load(sys.stdin))
    except Exception:
        result=fail("P620_ADAPTER_ERROR")
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"] in ("PASS","HANDOFF_REQUIRED") else 2

if __name__=="__main__":
    raise SystemExit(main())
