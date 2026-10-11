#!/usr/bin/env bash
# Read-only Magento Brain WRITE full-release preflight.
# Usage: bash magento-write-preflight.sh [MCP_APPS_SHA40] [BRAIN_SHA40]
set -Eeuo pipefail
MCP_SHA="${1:-741936da7d72f2f503c6f94851aca074e91ffde2}"
BRAIN_SHA="${2:-cbfb2ceb5aac0fc920940d9935952779081aedf0}"
if [[ $# -gt 2 || ! "$MCP_SHA" =~ ^[a-f0-9]{40}$ || ! "$BRAIN_SHA" =~ ^[a-f0-9]{40}$ ]]; then
  echo 'Usage: bash magento-write-preflight.sh [MCP_APPS_SHA40] [BRAIN_SHA40]' >&2
  exit 2
fi
MCP_SHA="$MCP_SHA" BRAIN_SHA="$BRAIN_SHA" /usr/bin/python3 - <<'PY'
import json,os,shutil,socket,subprocess,sys
from pathlib import Path
name='project-brain-controlled-execution-mcp'
home=Path.home()
def check(ok,code):
    if not ok: raise RuntimeError(code)
def port(n):
    try:
        with socket.create_connection(('127.0.0.1',n),timeout=2):
            return True
    except OSError:return False
try:
    cli=shutil.which('pm2')
    if not cli:
        cand=sorted(home.glob('.nvm/versions/node/*/bin/pm2'))
        cli=str(cand[-1]) if cand else None
    check(cli is not None,'PM2_CLI_MISSING')
    p=subprocess.run([cli,'jlist'],capture_output=True,text=True,timeout=20)
    check(p.returncode==0,'PM2_JLIST_FAILED')
    rows=json.loads(p.stdout)
    rows=[r for r in rows if isinstance(r,dict) and r.get('name')==name]
    check(len(rows)==1,'WRITE_PM2_SERVICE_NOT_UNIQUE')
    row=rows[0]; env=row.get('pm2_env') or {}
    check(env.get('status')=='online','WRITE_PM2_NOT_ONLINE')
    args=env.get('args') or []
    if isinstance(args,str):args=[args]
    check(len(args)==1,'WRITE_PM2_SOURCE_ARGS_AMBIGUOUS')
    script=Path(args[0]).resolve(strict=True)
    expected=home/'.project-brain/control-plane/controlled-execution-mcp/mcp-apps'
    check(script.name=='server.py' and script.parent.name=='project-brain-controlled-execution',
          'WRITE_SERVER_ROLE_MISMATCH')
    current_sha=''
    for item in script.parents:
        if item.parent==expected:
            current_sha=item.name
            break
    check(bool(current_sha),'WRITE_SOURCE_ROOT_OUTSIDE_RELEASES')
    check((expected/current_sha/'.pb-source-manifest.json').is_file(),'WRITE_RELEASE_MANIFEST_MISSING')
    check(port(8792) and port(8793),'MCP_PORT_BASELINE_INCOMPLETE')
    print('WRITE_DEPLOY_PREFLIGHT=PASS')
    print('CURRENT_MCP_APPS_SHA='+current_sha)
    print('REQUESTED_MCP_APPS_SHA='+os.environ['MCP_SHA'])
    print('REQUESTED_BRAIN_SHA='+os.environ['BRAIN_SHA'])
    print('WRITE_SUPERVISOR=PM2')
    print('READ_8792_PRESERVED_BASELINE=PASS')
    print('WRITE_8793_ONLINE=PASS')
    print('SOURCE_SHA_SEPARATION=REQUIRED')
    print('HMAC_V2_AND_EXACT_SOURCE_RELEASE=REQUIRED_ON_DEPLOY')
    print('PREFLIGHT_ONLY_NOT_DEPLOYED')
except Exception as exc:
    print('WRITE_DEPLOY_PREFLIGHT=FAIL_CLOSED')
    print('FAILURE_CODE='+str(exc))
    sys.exit(2)
PY
