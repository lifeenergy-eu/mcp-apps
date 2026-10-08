#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
SHA=ae98dd44d9f547a1de6f9f529027f53253513d59
B="$HOME/.project-brain/controlled-execution-mcp-wordpress"
DST="$B/adapter/helper.py"
SRC="https://raw.githubusercontent.com/lifeenergy-eu/mcp-apps/$SHA/adapters/cloudways-wordpress/controlled-execution-relay-helper.py"
test -f "$DST" || { echo "FAIL: WORDPRESS_WRITE_HELPER_MISSING"; exit 1; }
test -f "$B/runtime.env" || { echo "FAIL: WORDPRESS_WRITE_RUNTIME_ENV_MISSING"; exit 1; }
mkdir -p "$B/backups"
TMP="$(mktemp --suffix=.py)"
trap 'rm -f "$TMP"' EXIT
curl -fLSs --max-time 30 "$SRC" -o "$TMP"
python3 -m py_compile "$TMP"
printf '{"action":"CONNECTOR_HEALTH"}\n' | python3 "$TMP" | python3 -c '
import json,sys
r=json.load(sys.stdin)
assert r.get("status")=="PASS" and r.get("target_id")=="SERVER-CLOUDWAYS-WORDPRESS"
assert r.get("execution_binding")=="CHATGPT_GITHUB_DIRECT_TO_CANONICAL_RUN_CORE"
assert r.get("credential_on_wordpress_required") is False
print("SOURCE_PREFLIGHT_PASS")
'
printf '{"action":"RUN_APPLICATION_WORKFLOW","payload":{"workflow_id":"UNKNOWN","operation":{}}}\n' | python3 "$TMP" | python3 -c '
import json,sys
r=json.load(sys.stdin)
assert r["status"]=="FAIL_CLOSED"
assert r["code"]=="WORDPRESS_WORKFLOW_NOT_REGISTERED"
print("NEGATIVE_PATH_PASS")
'
cp -p "$DST" "$B/backups/helper-$(date -u +%Y%m%dT%H%M%SZ).py"
install -m 700 "$TMP" "$DST"
printf '{"action":"CONNECTOR_HEALTH"}\n' | python3 "$DST"
printf '{"action":"RUN_APPLICATION_WORKFLOW","payload":{"workflow_id":"WORDPRESS_CAPABILITY_PROBE_V1","operation":{"app_id":"wsbmznzrem"}}}\n' | python3 "$DST"
systemctl --user is-active pb-otb-write-mcp.service
echo "WORDPRESS_MCP_HANDOFF_INSTALLED"
