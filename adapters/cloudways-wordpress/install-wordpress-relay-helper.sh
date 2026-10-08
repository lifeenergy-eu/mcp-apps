#!/usr/bin/env bash
# Connect WordPress WRITE MCP to existing Project Brain GitHub relay / Run Core.
# No second executor, new server socket, SQL or arbitrary remote shell.
set -Eeuo pipefail
umask 077
SHA=805f30428eb24385b1a92f6399a3c1603414de72
BASE="$HOME/.project-brain/controlled-execution-mcp-wordpress"
STATE="$BASE/state"
HELPER="$BASE/adapter/helper.py"
TOKEN="$STATE/github_operation_token"
SRC="https://raw.githubusercontent.com/lifeenergy-eu/mcp-apps/$SHA/adapters/cloudways-wordpress/controlled-execution-relay-helper.py"
install -d -m 700 "$STATE" "$BASE/adapter" "$BASE/backups"
test -f "$BASE/runtime.env" || { echo "MISSING: existing WRITE MCP runtime.env"; exit 1; }
test -f "$HELPER" || { echo "MISSING: existing WRITE MCP helper"; exit 1; }

TMP="$(mktemp --suffix=.py)"
trap 'rm -f "$TMP"' EXIT
curl --fail --silent --show-error --location --max-time 30 "$SRC" -o "$TMP"
python3 -m py_compile "$TMP"
if ! test -s "$TOKEN"; then
  echo "GitHub fine-grained token required once:"
  echo "Repository: lifeenergy-eu/project-brain"
  echo "Permission: Contents read/write"
  read -r -s -p "GitHub token (not echoed): " GH_TOKEN
  printf '\n'
  test "$(printf '%s' "$GH_TOKEN" | wc -c)" -ge 30 || { echo "TOKEN: missing or too short"; exit 1; }
  printf '%s\n' "$GH_TOKEN" > "$TOKEN"
  unset GH_TOKEN
fi
chmod 600 "$TOKEN"
CHECK="$(printf '%s\n' '{"action":"CONNECTOR_HEALTH"}' | /usr/bin/python3 "$TMP" || true)"
printf '%s\n' "$CHECK" | /usr/bin/python3 -c '
import json,sys
x=json.load(sys.stdin)
if x.get("status")!="PASS" or x.get("execution_binding")!="RUN_CORE_BOUND_RELAY_BATCH" or x.get("target_id")!="SERVER-CLOUDWAYS-WORDPRESS":
    print("CANONICAL RELAY CONNECTION FAILED:", x.get("code","INVALID_HEALTH"))
    sys.exit(1)
print("CANONICAL RELAY AUTH: PASS")
print("REGISTERED WORDPRESS APPS:", x.get("registered_wordpress_installations"))
'
cp -p "$HELPER" "$BASE/backups/helper-before-github-relay-$(date -u +%Y%m%dT%H%M%SZ).py"
install -m 700 "$TMP" "$HELPER"
python3 -m py_compile "$HELPER"
FINAL="$(printf '%s\n' '{"action":"CONNECTOR_HEALTH"}' | /usr/bin/python3 "$HELPER")"
printf '%s\n' "$FINAL" | /usr/bin/python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x["status"]=="PASS" and x["write_backend"]=="CANONICAL_RELAY"
print("WORDPRESS WRITE MCP -> EXISTING RUN CORE: CONNECTED")
print("SAFE WORKFLOWS: "+", ".join(x["registered_workflows"]))
'
echo "WORDPRESS WRITE MCP ADAPTER: INSTALLED"
