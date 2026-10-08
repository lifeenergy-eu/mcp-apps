#!/usr/bin/env bash
# P620 only — read-only verification of existing DEBUG MCP before separate WRITE MCP work.
set -euo pipefail
export LC_ALL=C
ROOT="/srv/project-brain/source/p620-ai-runtime"
MANIFEST="$ROOT/MCP_APP_SOURCE.json"
SERVICE="project-brain-p620-mcp.service"
echo "=== P620 DEBUG MCP REFERENCE ==="
python3 - "$MANIFEST" "$ROOT" <<'PY'
from pathlib import Path
import json,sys,subprocess
manifest=Path(sys.argv[1]); repo=Path(sys.argv[2])
if not manifest.is_file():
    print("SOURCE_MANIFEST=MISSING"); raise SystemExit(2)
m=json.loads(manifest.read_text())
print("MANIFEST_SOURCE_REPOSITORY="+str(m.get("source_repository")))
print("MANIFEST_APP_PATH="+str(m.get("app_path")))
print("MANIFEST_PIN="+str(m.get("source_sha")))
pin=str(m.get("source_sha") or "")
if len(pin)!=40 or m.get("source_repository")!="lifeenergy-eu/mcp-apps" or m.get("app_path")!="apps/p620-diagnostics":
    raise SystemExit("UNEXPECTED_P620_DEBUG_SOURCE")
live=Path("/srv/project-brain/mcp-apps/releases")/pin/"p620-diagnostics/server.py"
print("PINNED_APP_FILE="+("PRESENT" if live.is_file() else "MISSING"))
head=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,timeout=5)
print("WRAPPER_HEAD="+(head.stdout.strip() if head.returncode==0 else "UNAVAILABLE"))
PY
echo "=== ACTIVE DEBUG SERVICE ==="
systemctl show "$SERVICE" -p LoadState -p ActiveState -p SubState -p FragmentPath -p DropInPaths -p MainPID --no-pager
echo "=== SERVICE START SOURCE (SAFE PATHS ONLY) ==="
python3 - <<'PY'
import subprocess,re
s=subprocess.run(["systemctl","show","project-brain-p620-mcp.service","-p","ExecStart","--value"],capture_output=True,text=True,timeout=5).stdout
m=re.search(r'argv\[\]=([^;]+)',s)
argv=m.group(1) if m else ""
paths=re.findall(r'/srv/project-brain/mcp-apps/[^ ]+|/usr/local/libexec/[^ ]+',argv)
print("SERVICE_RUNTIME_PATHS="+",".join(x.strip() for x in paths) if paths else "UNRESOLVED")
PY
echo "=== DEBUG / WRITE SOCKET BINDING ==="
ss -ltn '( sport = :8792 or sport = :8793 )' || true
echo "=== DEBUG OAUTH CHALLENGE ==="
code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"p620-preflight","version":"1"}}}' \
  http://127.0.0.1:8792/mcp || true)
echo "DEBUG_UNAUTHENTICATED_HTTP=$code"
echo "=== SYSTEMD UNIT / SOURCE DROPIN ==="
for p in \
  /etc/systemd/system/project-brain-p620-mcp.service \
  /etc/systemd/system/project-brain-p620-mcp.service.d/10-source.conf \
  /usr/local/libexec/p620-debug-read \
  /srv/project-brain/mcp-apps/venv/bin/python
do
  if test -e "$p"; then echo "PRESENT $p"; else echo "MISSING $p"; fi
done
echo "=== TAILSCALE CONFIGURED EXPOSURE (NO CHANGES) ==="
if command -v tailscale >/dev/null; then
  tailscale serve status --json 2>/dev/null | python3 -c '
import json,sys
try:
 d=json.load(sys.stdin)
 print("TAILSCALE_INGRESS_CONFIG="+("PRESENT" if isinstance(d,dict) and bool(d) else "EMPTY"))
 print("TAILSCALE_TOP_LEVEL_KEYS="+",".join(sorted(d)[:10]) if isinstance(d,dict) else "UNKNOWN")
except Exception: print("TAILSCALE_INGRESS_CONFIG=UNAVAILABLE")
' || true
else
  echo "TAILSCALE_COMMAND=UNAVAILABLE"
fi
echo "=== P620 WRITE BOUNDARY ==="
echo "DEBUG_8792_MUST_STAY_UNCHANGED=YES"
echo "P620_DIRECT_INBOUND_MUTATION_ALLOWED=NO"
echo "WRITE_BACKEND_E2E_VERIFIED=NO"
echo "=== PREFLIGHT DONE ==="
