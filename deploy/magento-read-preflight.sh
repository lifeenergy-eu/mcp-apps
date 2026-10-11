#!/usr/bin/env bash
# Read-only Magento systemd READ MCP identity and full-source deployment preflight.
# bash magento-read-preflight.sh [TARGET_MCP_APPS_SHA40]
set -Eeuo pipefail
TARGET_SHA="${1:-38d02dd8c9cc03cd45ef1641858825a03f4c18b7}"
if [[ $# -gt 1 || ! "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage: bash magento-read-preflight.sh [TARGET_MCP_APPS_SHA40]' >&2
  exit 2
fi
TARGET_SHA="$TARGET_SHA" /usr/bin/python3 - <<'PY'
import os, re, subprocess, sys
from pathlib import Path
sha=os.environ['TARGET_SHA']
home=Path.home().resolve()
unit='project-brain-cloudways-mcp-magento.service'
prefix=home/'.project-brain/cloudways-mcp/magento/releases/lifeenergy-eu__mcp-apps'
expected_fragment=home/'.config/systemd/user'/unit
def run(*args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if p.returncode: raise RuntimeError('SYSTEMD_USER_QUERY_FAILED')
    return dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)
def check(ok,code):
    if not ok: raise RuntimeError(code)
def listener_pids(port):
    inodes=set()
    for file in (Path('/proc/net/tcp'),Path('/proc/net/tcp6')):
        for row in file.read_text().splitlines()[1:]:
            f=row.split()
            if len(f)>9 and f[3]=='0A' and int(f[1].rsplit(':',1)[-1],16)==port:
                inodes.add(f[9])
    pids=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdecimal(): continue
        try:
            if any(os.readlink(fd)==f'socket:[{inode}]' for fd in (p/'fd').iterdir() for inode in inodes):
                pids.append(int(p.name))
        except (OSError,PermissionError): pass
    return sorted(set(pids))
try:
    info=run('systemctl','--user','show',unit,'-p','Id','-p','ActiveState','-p','MainPID','-p','FragmentPath','-p','DropInPaths','-p','UnitFileState')
    check(info.get('Id')==unit,'READ_SYSTEMD_UNIT_MISMATCH')
    check(info.get('ActiveState')=='active','READ_SYSTEMD_INACTIVE')
    check(info.get('UnitFileState')=='enabled','READ_SYSTEMD_NOT_ENABLED')
    check(info.get('FragmentPath')==str(expected_fragment),'READ_SYSTEMD_FRAGMENT_UNEXPECTED')
    check(not info.get('DropInPaths'),'READ_SYSTEMD_DROPINS_REQUIRE_INSPECTION')
    pid=int(info.get('MainPID','0'))
    check(pid>1 and Path(f'/proc/{pid}').is_dir(),'READ_MAINPID_INVALID')
    read_pids=listener_pids(8792)
    write_pids=listener_pids(8793)
    check(read_pids==[pid],'READ_8792_SYSTEMD_IDENTITY_UNVERIFIED')
    check(len(write_pids)==1,'WRITE_8793_BASELINE_UNVERIFIED')
    root_candidates=[]
    cwd=(Path('/proc')/str(pid)/'cwd').resolve(strict=True)
    for root in [cwd,*cwd.parents]:
        if (root/'apps/cloudways-infrastructure-access/server.py').is_file() and (root/'packages/infrastructure_read_policy/cloudways_helper.py').is_file():
            root_candidates.append(root)
    check(len(root_candidates)==1,'READ_SOURCE_ROOT_UNVERIFIED')
    root=root_candidates[0].resolve(strict=True)
    check(root.parent==prefix,'READ_ROOT_OUTSIDE_REGISTERED_RELEASE_TREE')
    current_sha=root.name
    check(re.fullmatch('[a-f0-9]{40}',current_sha) is not None,'READ_CURRENT_SHA_UNVERIFIED')
    proc=(Path('/proc')/str(pid))
    cgroup=(proc/'cgroup').read_text(encoding='utf-8')
    check(unit in cgroup,'READ_CGROUP_SERVICE_MISMATCH')
    raw=(proc/'environ').read_bytes()
    pinned=[]
    for entry in raw.split(bytes([0])):
        if b'=' not in entry: continue
        k,v=entry.split(b'=',1)
        if current_sha.encode() in v:
            name=k.decode('ascii','replace')
            pinned.append(name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name) else 'INVALID_ENV_KEY')
    check(bool(pinned),'READ_RUNTIME_SHA_ENV_BINDING_MISSING')
    print('READ_DEPLOY_PREFLIGHT=PASS')
    print('TARGET_MCP_APPS_SHA='+sha)
    print('CURRENT_READ_SHA='+current_sha)
    print('READ_UNIT='+unit)
    print('READ_SUPERVISOR=SYSTEMD_USER')
    print('READ_ACTIVE_MAINPID='+str(pid))
    print('READ_8792_UNIQUE_OWNER=PASS')
    print('WRITE_8793_PRESERVED_BASELINE=PASS')
    print('READ_SOURCE_ROOT='+str(root))
    print('RUNTIME_SHA_PIN_ENV_KEYS='+','.join(sorted(pinned)))
    print('FULL_SOURCE_RELEASE_REQUIRED=YES')
    print('RUN_CORE_REGISTERED_SYSTEMD_ROLLOUT_REQUIRED=YES')
    print('NO_MUTATION=YES')
    print('PREFLIGHT_ONLY_NOT_DEPLOYED')
except Exception as e:
    print('READ_DEPLOY_PREFLIGHT=FAIL_CLOSED')
    print('FAILURE_CODE='+str(e))
    sys.exit(2)
PY
