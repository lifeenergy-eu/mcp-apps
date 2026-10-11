#!/usr/bin/env bash
# Magento — canonical full exact-SHA Brain + MCP Apps bootstrap.
# Usage: bash deploy_mcp_apps_sha_magento.sh [MCP_APPS_SHA40] [BRAIN_SHA40]
# Read-only diagnostics: bash deploy_mcp_apps_sha_magento.sh --diagnose [BRAIN_SHA40]
# Run as existing Cloudways master user. This is a bounded one-time
# bootstrap; after activation future production deployments go via Brain Run Core.
set -euo pipefail
umask 077
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo 'Usage: bash deploy_mcp_apps_sha_magento.sh [MCP_APPS_SHA40] [BRAIN_SHA40]'
  echo 'Default MCP Apps: 741936da7d72f2f503c6f94851aca074e91ffde2'
  echo 'Default Brain:    2553b7cf8a0896f28bef866b25654bceb975f258'
  echo 'SHA values are independent. Pass both to pin an exact future release.'
  echo 'Read-only: bash deploy_mcp_apps_sha_magento.sh --diagnose [BRAIN_SHA40]'
  exit 0
fi
# A read-only, fail-closed inspection of the previously failed installer.
# Do not rerun an unchanged failed deploy just to recover the missing error log.
if [[ "${1:-}" == "--diagnose" ]]; then
  BRAIN_DIAG_SHA="${2:-2553b7cf8a0896f28bef866b25654bceb975f258}"
  if [[ $# -gt 2 ]] || ! [[ "$BRAIN_DIAG_SHA" =~ ^[a-f0-9]{40}$ ]]; then
    echo 'Usage: bash deploy_mcp_apps_sha_magento.sh --diagnose [BRAIN_SHA40]' >&2
    exit 2
  fi
  BRAIN_DIAG_SHA="$BRAIN_DIAG_SHA" /usr/bin/python3 - <<'PY_DIAG'
import json,os,pwd,re,shutil,subprocess
from pathlib import Path
s=os.environ['BRAIN_DIAG_SHA']
home=Path('/home/master')
base=home/'.project-brain/control-plane'
src=base/'controlled-execution-mcp/brain-source'/s
inst=src/'control-plane/relay/install/install_relay_v20.sh'
rel=base/'relay'
print('DIAGNOSTIC_ONLY: no install, PM2 switch, daemon restart, source change, or secrets read',flush=True)
print('BRAIN_SHA='+s)
manifest=src/'.pb-source-manifest.json'
try:
    obj=json.loads(manifest.read_text())
    print('BRAIN_SOURCE_MATCH='+str(obj.get('repository')=='lifeenergy-eu/project-brain' and obj.get('source_sha')==s))
except Exception as e: print('BRAIN_SOURCE_MANIFEST_ERROR='+type(e).__name__)
print('CANONICAL_INSTALLER_PRESENT='+str(inst.is_file()))
if inst.is_file():
    v=subprocess.run(['/usr/bin/bash','-n',str(inst)],capture_output=True,text=True,timeout=10)
    print('INSTALLER_BASH_SYNTAX_RC='+str(v.returncode))
webroot=home/'applications/kshuetpccm/public_html'
print('EXPECTED_LARAVEL_ARTISAN='+str((webroot/'artisan').is_file()))
print('EXPECTED_LARAVEL_INDEX='+str((webroot/'public/index.php').is_file()))
try:
    pwd.getpwnam(webroot.parent.name)
    print('EXPECTED_APPLICATION_USER=EXISTS')
except KeyError: print('EXPECTED_APPLICATION_USER=MISSING')
for tool in ['setfacl','getfacl','crontab','php','php8.3','flock']:
    print('INSTALLER_TOOL_'+tool.upper().replace('.','_')+'='+('PRESENT' if shutil.which(tool) else 'MISSING'))
current=rel/'current'
print('RELAY_CURRENT_IS_SYMLINK='+str(current.is_symlink()))
if current.is_symlink():
    dest=current.resolve()
    print('RELAY_CURRENT_EQUALS_REQUESTED_SHA='+str(dest==rel/'releases'/s))
for test in ['control-plane/tests/operation_relay_selftest.py','control-plane/tests/browser_command_runtime_test.py']:
    testpath=src/test
    if not testpath.is_file():
        print('SOURCE_SELFTEST_'+testpath.name+'=MISSING')
        continue
    try:
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        r=subprocess.run(['/usr/bin/python3','-B',str(testpath)],env=env,timeout=45,capture_output=True,text=True)
        print('SOURCE_SELFTEST_'+testpath.name+'_RC='+str(r.returncode))
        if r.returncode:
            for marker in ['AssertionError','ImportError','ModuleNotFoundError','SyntaxError','PermissionError','FileNotFoundError','RuntimeError']:
                if marker in (r.stderr+r.stdout): print('SOURCE_SELFTEST_'+testpath.name+'_ERROR='+marker)
    except Exception as e: print('SOURCE_SELFTEST_'+testpath.name+'_FAILED='+type(e).__name__)
print('DIAGNOSTIC_DONE')
PY_DIAG
  exit $?
fi
if [[ $# -gt 2 ]]; then
  echo 'Usage: bash deploy_mcp_apps_sha_magento.sh [MCP_APPS_SHA40] [BRAIN_SHA40]' >&2
  exit 2
fi
MCP_SHA="${1:-741936da7d72f2f503c6f94851aca074e91ffde2}"
BRAIN_SHA="${2:-2553b7cf8a0896f28bef866b25654bceb975f258}"
if ! [[ "$MCP_SHA" =~ ^[a-f0-9]{40}$ && "$BRAIN_SHA" =~ ^[a-f0-9]{40}$ ]]; then
  echo 'Usage: bash deploy_mcp_apps_sha_magento.sh [MCP_APPS_SHA40] [BRAIN_SHA40]' >&2
  exit 2
fi
printf 'REQUESTED_EXACT_SHA: mcp_apps=%s brain=%s\n' "$MCP_SHA" "$BRAIN_SHA"
MCP_SHA="$MCP_SHA" BRAIN_SHA="$BRAIN_SHA" /usr/bin/python3 - <<'PY'
from __future__ import annotations
import ast, base64, fcntl, glob, hashlib, json, os, re, shutil, socket
import subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path, PurePosixPath

SHA40 = re.compile(r'^[a-f0-9]{40}$')
MCP_SHA = os.environ['MCP_SHA']
BRAIN_SHA = os.environ['BRAIN_SHA']
HOME = Path('/home/master')
PB = HOME / '.project-brain/control-plane'
CE = PB / 'controlled-execution-mcp'
# Use an isolated disposable source-ingress workspace; never prune the active cache.
SECRET_FILE = PB / 'secrets/github_source_token'
INGRESS_REL = 'control-plane/source/exact_sha_ingress.py'
HELPER_REL = 'control-plane/controlled-execution/helper.py'
SERVER_REL = 'apps/project-brain-controlled-execution/server.py'
PM2_NAME = 'project-brain-controlled-execution-mcp'
RELAY_PROFILE = 'PROJECT_BRAIN_RELAY_REFRESH_V1'

class Stop(Exception): pass
def check(ok, code):
    if not ok: raise Stop(code)
def info(message): print(message, flush=True)
def command(argv, *, env=None, input=None, timeout=100):
    r = subprocess.run([str(x) for x in argv], input=input, text=True,
                       capture_output=True, shell=False, timeout=timeout,
                       env=env)
    if r.returncode:
        # Never echo raw stderr or environment, which may contain sensitive data.
        raise Stop('SUBPROCESS_FAILED_' + Path(str(argv[0])).name.upper())
    return r.stdout

def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()

def port(number):
    try:
        with socket.create_connection(('127.0.0.1', number), timeout=2): return True
    except OSError: return False

def oauth_protected():
    try: urllib.request.urlopen('http://127.0.0.1:8793/mcp', timeout=4)
    except urllib.error.HTTPError as exc:
        check(exc.code in (401, 403), 'MCP_OAUTH_GATE_BAD_STATUS')
        return
    raise Stop('MCP_UNAUTHENTICATED_ACCESS_ALLOWED')

def process_env(pid):
    data = (Path('/proc') / str(pid) / 'environ').read_bytes()
    values = {}
    for item in data.split(b'\0'):
        if b'=' in item:
            key, val = item.split(b'=', 1)
            values[os.fsdecode(key)] = os.fsdecode(val)
    return values

def pm2_binary():
    options = [shutil.which('pm2'), '/home/master/.nvm/versions/node/v22.22.2/bin/pm2']
    options += sorted(glob.glob('/home/master/.nvm/versions/node/v*/bin/pm2'), reverse=True)
    path = next((p for p in dict.fromkeys(options) if p and Path(p).is_file()
                 and os.access(p, os.X_OK)), None)
    check(path is not None, 'EXISTING_PM2_NOT_FOUND')
    os.environ['PATH'] = str(Path(path).parent) + os.pathsep + os.environ.get('PATH', '')
    return path

def pm_rows(cli): return json.loads(command([cli, 'jlist'], timeout=35))
def running(cli):
    rows = [r for r in pm_rows(cli) if r.get('name') == PM2_NAME]
    check(len(rows) == 1, 'PM2_SERVICE_NOT_UNIQUE')
    return rows[0]

def safe_source(root, repo, sha, entry, min_files):
    root = Path(root)
    mf = root / '.pb-source-manifest.json'
    check(mf.is_file() and not mf.is_symlink(), 'CANONICAL_MANIFEST_NOT_PRESENT')
    data = json.loads(mf.read_text(encoding='utf-8'))
    check(data.get('repository') == repo and data.get('source_sha') == sha
          and data.get('production_activation') is False,
          'CANONICAL_MANIFEST_REPO_SHA_MISMATCH')
    items = data.get('files')
    check(isinstance(items, list) and len(items) >= min_files,
          'INCOMPLETE_WHOLE_SOURCE_MANIFEST')
    check(data.get('file_count') == len(items), 'MANIFEST_FILE_COUNT_MISMATCH')
    paths = set()
    for item in items:
        check(isinstance(item, dict), 'MANIFEST_RECORD_INVALID')
        name = item.get('path')
        check(isinstance(name, str) and name and name not in paths,
              'MANIFEST_SOURCE_NAME_INVALID')
        p = PurePosixPath(name)
        check(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts,
              'MANIFEST_PATH_UNSAFE')
        paths.add(name)
        f = root / name
        check(f.is_file() and not f.is_symlink(), 'SOURCE_MANIFEST_FILE_MISSING')
        check(f.stat().st_size == item.get('size') and sha256_file(f) == item.get('sha256'),
              'SOURCE_MANIFEST_FILE_HASH_MISMATCH')
    check(entry in paths, 'COMPLETE_RELEASE_ENTRYPOINT_MISSING')
    for p in root.rglob('*'):
        check(not p.is_symlink(), 'SOURCE_SYMLINK_NOT_ALLOWED')
        if p.is_file() and p != mf:
            check(p.relative_to(root).as_posix() in paths, 'SOURCE_MANIFEST_EXTRA_FILE')
    ast.parse((root / entry).read_text(encoding='utf-8'))
    return root / entry

def authenticated_json(url, token):
    req = urllib.request.Request(url,
        headers={'Authorization': 'Bearer ' + token,
                 'Accept': 'application/vnd.github+json',
                 'User-Agent': 'Project-Brain-Canonical-SSH-Bootstrap/1'})
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.load(resp)

def canonical_ingress_bootstrap(path, sha, token):
    # Authenticated GitHub Contents exact commit, with Git blob verification.
    url = ('https://api.github.com/repos/lifeenergy-eu/project-brain/contents/'
           + INGRESS_REL + '?ref=' + sha)
    obj = authenticated_json(url, token)
    check(obj.get('path') == INGRESS_REL and obj.get('encoding') == 'base64'
          and isinstance(obj.get('sha'), str), 'CANONICAL_INGRESS_GITHUB_RESPONSE_INVALID')
    source = base64.b64decode(obj['content'], validate=False)
    check(git_blob(source) == obj['sha'], 'CANONICAL_INGRESS_GIT_BLOB_MISMATCH')
    ast.parse(source.decode('utf-8'))
    path.write_bytes(source)
    return path

def ingest(script, repository, sha, token, stage_root):
    # Use the existing canonical source-ingress verifier, never a handcrafted manifest.
    env = dict(os.environ)
    env['PB_GITHUB_SOURCE_TOKEN'] = token
    proc = subprocess.run(['/usr/bin/python3', str(script), '--repository', repository,
                           '--source-sha', sha, '--stage-root', str(stage_root)],
                          env=env, text=True, capture_output=True, timeout=270,
                          shell=False)
    try: response = json.loads((proc.stdout or '').strip().splitlines()[-1])
    except (ValueError, IndexError): raise Stop('CANONICAL_INGRESS_RESPONSE_INVALID_' + repository.split('/')[-1])
    if proc.returncode or response.get('status') != 'PASS':
        code = str(response.get('code') or 'CANONICAL_SOURCE_VERIFICATION_FAILED')
        check(re.fullmatch(r'[A-Z0-9_]{4,95}', code) is not None, 'CANONICAL_INGRESS_FAILED')
        raise Stop(code)
    check(response.get('repository') == repository and response.get('source_sha') == sha,
          'CANONICAL_SOURCE_RESPONSE_IDENTITY_MISMATCH')
    if repository != 'lifeenergy-eu/project-brain':
        a = response.get('source_attestation') or {}
        check(a.get('status') == 'CANONICAL_ATTESTATION_V2_PASS' and a.get('required') is True,
              'HMAC_V2_ATTESTATION_NOT_VERIFIED')
    source = Path(stage_root) / 'releases' / repository.replace('/', '__') / sha
    return source

def immutable_full_release(source, dest, repository, sha, entry, min_files):
    safe_source(source, repository, sha, entry, min_files)
    if dest.exists():
        return safe_source(dest, repository, sha, entry, min_files)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / ('.complete-sha-stage-' + sha + '-' + str(os.getpid()))
    check(not tmp.exists(), 'EXACT_SHA_STAGE_COLLISION')
    try:
        shutil.copytree(source, tmp, symlinks=False)
        safe_source(tmp, repository, sha, entry, min_files)
        os.replace(tmp, dest)
    finally:
        if tmp.exists(): shutil.rmtree(tmp)
    return safe_source(dest, repository, sha, entry, min_files)

def probe_helper(helper):
    r = subprocess.run(['/usr/bin/python3', str(helper)],
        input=json.dumps({'action': 'CONNECTOR_HEALTH', 'payload': {}}),
        capture_output=True, text=True, timeout=25, shell=False)
    check(r.returncode == 0, 'NEW_BRAIN_HELPER_PROBE_FAILED')
    try: row = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError): raise Stop('NEW_BRAIN_HELPER_RESPONSE_INVALID')
    check(row.get('status') == 'PASS', 'NEW_BRAIN_HELPER_HEALTH_FAILED')

def verify_compiler(root, mcp_sha):
    # Compiler resolves an exact registered mcp-apps deploy, but does not execute it.
    program = '''import importlib.util,json,sys
from pathlib import Path
r=Path(sys.argv[1]);sha=sys.argv[2]
p=r/'control-plane/run-core/chat_intent_compiler.py'
s=importlib.util.spec_from_file_location('pb_bootstrap_deploy_compile',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
task={'schema_version':'1.0','task_id':'PB-BOOTSTRAP-DEPLOY-PROBE-20261011','intent_key':'DEPLOY','inputs':{'repository':'lifeenergy-eu/mcp-apps','source_sha':sha}}
o=m.resolve_named_task(task)
assert o['steps'][0]['capability']=='DEPLOY_MAGENTO_BRAIN_EXECUTE_MCP_EXACT_SHA'
compiled=m.compile_intent(task,r.name)
assert compiled['status']=='PASS' and compiled['validation_only'] is True
steps=compiled['plan']['steps']
assert len(steps)==1 and steps[0]['plan']['action']=='controlled_execution_product_exact_sha_deploy_v1'
assert steps[0]['plan']['target_id']=='SERVER-CLOUDWAYS-MAGENTO'
assert steps[0]['plan']['candidate_mcp_apps_sha']==sha
print('COMPILER_AND_FULL_RUN_CORE_PLAN_PASS')'''
    command(['/usr/bin/python3', '-c', program, str(root), mcp_sha], timeout=25)

def launch(cli, py, server, cwd, values):
    command([cli, 'start', str(py), '--name', PM2_NAME, '--interpreter', 'none',
             '--cwd', str(cwd), '--', str(server)], env=values, timeout=40)

def accept(cli, server, helper):
    for _ in range(36):
        try:
            row = running(cli)
            e = row.get('pm2_env') or {}
            args = e.get('args') or []
            if isinstance(args, str): args = [args]
            pid = row.get('pid')
            if (e.get('status') == 'online' and args == [str(server)]
                and isinstance(pid, int) and pid > 1
                and process_env(pid).get('PB_CONTROLLED_EXECUTION_HELPER') == str(helper)
                and port(8792) and port(8793)):
                oauth_protected()
                return pid
        except (Stop, OSError, ValueError, KeyError): pass
        time.sleep(1)
    raise Stop('PM2_RELEASE_ACCEPTANCE_FAILED')

def main():
    check(os.geteuid() != 0 and os.environ.get('HOME') == str(HOME),
          'RUN_AS_EXISTING_CLOUDWAYS_MASTER_NOT_ROOT')
    check(Path('/proc/self').exists(), 'LINUX_PROC_REQUIRED')
    check(SECRET_FILE.is_file() and not SECRET_FILE.is_symlink(),
          'CANONICAL_PRIVATE_GITHUB_TOKEN_FILE_MISSING')
    mode = SECRET_FILE.stat().st_mode & 0o777
    check(mode in (0o600, 0o400), 'CANONICAL_TOKEN_FILE_PERMISSIONS_INVALID')
    token = SECRET_FILE.read_text(encoding='utf-8').strip()
    check(bool(token) and '\n' not in token, 'CANONICAL_TOKEN_UNAVAILABLE')
    cli = pm2_binary()
    previous = running(cli)
    cfg = previous.get('pm2_env') or {}
    check(cfg.get('status') == 'online', 'EXISTING_PM2_OFFLINE')
    args = cfg.get('args') or []
    if isinstance(args, str): args = [args]
    check(len(args) == 1, 'EXISTING_PM2_ENTRYPOINT_INVALID')
    old_server = Path(args[0]); python = Path(str(cfg.get('pm_exec_path') or ''))
    old_cwd = Path(str(cfg.get('pm_cwd') or ''))
    old_pid = previous.get('pid')
    check(old_server.is_file() and python.is_file() and old_cwd.is_dir()
          and isinstance(old_pid, int) and old_pid > 1,
          'EXISTING_RUNTIME_FILES_UNAVAILABLE')
    live = process_env(old_pid)
    old_helper = Path(live.get('PB_CONTROLLED_EXECUTION_HELPER') or '/not-found')
    check(old_helper.is_file(), 'EXISTING_BRAIN_HELPER_MISSING')
    for key in ('MCP_PUBLIC_HOST','MCP_OAUTH_DB_PATH','MCP_OAUTH_PASSWORD_FILE'):
        check(bool(live.get(key)), 'EXISTING_OAUTH_ENV_INCOMPLETE')
    check(port(8792) and port(8793), 'EXISTING_READ_OR_EXECUTE_MCP_PORT_DOWN')
    oauth_protected()
    info('PREFLIGHT_PASS: current PM2, OAuth, Read MCP preserved')
    check(shutil.disk_usage(PB).free >= 650_000_000, 'NOT_ENOUGH_SPACE_FOR_TWO_COMPLETE_SOURCE_RELEASES')
    check(BRAIN_SHA != MCP_SHA, 'SOURCE_SHA_IDENTITY_INVALID')
    CE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pb-full-sha-bootstrap-',dir=str(CE)) as folder:
        stage_root = Path(folder) / 'canonical-source-ingress'
        stage_root.mkdir()
        bootstrap = canonical_ingress_bootstrap(Path(folder) / 'canonical_ingress.py', BRAIN_SHA, token)
        brain_source = ingest(bootstrap, 'lifeenergy-eu/project-brain', BRAIN_SHA, token, stage_root)
        brain_root = CE / 'brain-source' / BRAIN_SHA
        new_helper = immutable_full_release(brain_source, brain_root,
            'lifeenergy-eu/project-brain', BRAIN_SHA, HELPER_REL, 100)
        check((brain_root / INGRESS_REL).is_file(), 'BRAIN_CANONICAL_SOURCE_INGRESS_NOT_IN_RELEASE')
        probe_helper(new_helper)
        verify_compiler(brain_root, MCP_SHA)
        info('BRAIN_FULL_SOURCE_PASS: exact SHA, complete manifest, new helper and deploy compiler')

        mcp_source = ingest(brain_root / INGRESS_REL, 'lifeenergy-eu/mcp-apps', MCP_SHA, token, stage_root)
        mcp_root = CE / 'mcp-apps' / MCP_SHA
        new_server = immutable_full_release(mcp_source, mcp_root,
            'lifeenergy-eu/mcp-apps', MCP_SHA, SERVER_REL, 2)
        content = new_server.read_text(encoding='utf-8')
        check('def brain_execute(repository: str, commit_sha: str)' in content,
              'MCP_PUBLIC_SCHEMA_EXACT_TWO_PARAMETERS_MISSING')
        info('MCP_APPS_FULL_SOURCE_PASS: exact SHA, canonical HMAC V2, complete manifest')

        # Bootstraps the *existing registered* relay refresh, not an alternate runner.
        installer = brain_root / 'control-plane/relay/runtime_refresh.py'
        check(installer.is_file(), 'REGISTERED_RELAY_REFRESH_MISSING')
        refresh_plan = {
            'schema_version': '1.0',
            'plan_id': 'PB-SSH-CANONICAL-BOOTSTRAP-' + BRAIN_SHA[:16].upper(),
            'plan_profile': RELAY_PROFILE,
            'target_id': 'project-brain-control-plane-production',
            'repository': 'lifeenergy-eu/project-brain',
            'source_sha': BRAIN_SHA,
            'github_actions_execution': False,
            'production_application_mutation': False,
            'production_database_mutation': False,
        }
        plan_file = Path(folder) / 'registered-relay-refresh-plan.json'
        plan_file.write_text(json.dumps(refresh_plan, indent=2))
        info('RUNNING_REGISTERED_RELAY_REFRESH: canonical activation conformance before PM2 switch')
        refresh = subprocess.run(['/usr/bin/python3',str(installer),'--plan',str(plan_file)],
            capture_output=True,text=True,timeout=720,shell=False)
        try: result = json.loads((refresh.stdout or '').strip().splitlines()[-1])
        except (ValueError, IndexError): raise Stop('RELAY_REFRESH_RESULT_INVALID')
        if (refresh.returncode != 0 or result.get('status') != 'PASS'
                or result.get('source_sha') != BRAIN_SHA
                or (result.get('activation_conformance') or {}).get('status') != 'PASS'):
            # Emit only controlled diagnostic metadata, not arbitrary runner output
            # or secrets. Full logs remain inside the canonical runner.
            details = result.get('details') or {}
            if isinstance(details, dict):
                test_ref = str(details.get('test_ref') or '')
                if re.fullmatch(r'control-plane/tests/[a-zA-Z0-9_.-]+', test_ref):
                    print('FAILED_CONFORMANCE_TEST: ' + test_ref, file=sys.stderr)
                rc = details.get('rc')
                if type(rc) is int:
                    print('FAILED_CONFORMANCE_RC: ' + str(rc), file=sys.stderr)
                codes = set()
                for field in ('stdout_tail','stderr_tail'):
                    lines = str(details.get(field) or '').splitlines()
                    for line in lines:
                        for match in re.findall(r'(?:RELAY_ACTIVATION|INTAKE|CHAT_DEPLOY|SOURCE|MCP|RUNTIME|AssertionError|SyntaxError|ModuleNotFoundError)[A-Z0-9_]*', line):
                            if 8 <= len(match) <= 95:
                                codes.add(match)
                for code in sorted(codes)[:12]:
                    print('CONFORMANCE_FAILURE_INDICATOR: ' + code, file=sys.stderr)
                # Whitelist safe assertion locations from Python test tracebacks.
                # Never display raw log contents, process env or credentials.
                for field in ('stdout_tail', 'stderr_tail'):
                    for line in str(details.get(field) or '').splitlines():
                        m = re.search(r'File "[^"]*/(control-plane/tests/[A-Za-z0-9_.-]+)", line ([0-9]{1,5})', line)
                        if m:
                            print('FAILED_ASSERTION_LOCATION: ' + m.group(1) + ':' + m.group(2), file=sys.stderr)
            if result.get('code') == 'RELAY_INSTALL_FAILED':
                # Canonical runner captures the failing installer's stderr in its
                # typed result. The previous wrapper hid it entirely. Do NOT
                # display raw stderr, request headers, token values or env.
                print('FAILED_PHASE: CANONICAL_RELAY_INSTALLER', file=sys.stderr)
                if isinstance(details, dict):
                    err = str(details.get('stderr_tail') or '')[-4000:]
                    causes = {
                        'ACL_PERMISSION_DENIED': r'(?i)(setfacl.*(permission denied|operation not permitted)|permission denied.*acl)',
                        'ACL_INVALID_USER_OR_ARGUMENT': r'(?i)(setfacl.*(invalid argument|invalid user|no such user|invalid option))',
                        'LARAVEL_APP_PATH_OR_FILE_MISSING': r'(?i)(canonical Laravel transport application shape|required.*not found|no such file or directory)',
                        'CRONTAB_INSTALL_FAILURE': r'(?i)(crontab.*(error|not allowed|permission|invalid|bad))',
                        'PHP_LINT_FAILURE': r'(?i)(parse error|php fatal error|errors parsing|syntax error.*php)',
                        'PYTHON_SELFTEST_FAILURE': r'(?i)(assertionerror|modulenotfounderror|traceback|runtimeerror|file.*not found)',
                        'SOURCE_FILE_MISSING': r'FAIL: missing current V20 source',
                        'FILE_PERMISSION_FAILURE': r'(?i)(operation not permitted|permission denied)',
                        'DISK_SPACE_FAILURE': r'(?i)(no space left on device|disk quota exceeded)',
                    }
                    for name, expression in causes.items():
                        if re.search(expression, err):
                            print('INSTALLER_FAILURE_CLASS: '+name, file=sys.stderr)
                    for tool_name in ('setfacl','crontab','php8.3','python3','cp','mv','mkdir','ln','chmod','flock'):
                        if re.search(r'(?<![A-Za-z0-9_])'+re.escape(tool_name)+r'(?![A-Za-z0-9_])',err):
                            print('INSTALLER_FAILURE_TOOL: '+tool_name, file=sys.stderr)
                    for match in re.finditer(r'(?:line|linija)\s+([0-9]{1,5})',err,re.I):
                        print('INSTALLER_REPORTED_LINE: '+match.group(1),file=sys.stderr)
                    # Exact installer stderr is intentionally not emitted here.
                    if not err:
                        print('INSTALLER_STDERR: EMPTY_OR_UNAVAILABLE',file=sys.stderr)
            raise Stop(str(result.get('code') or 'REGISTERED_RELAY_REFRESH_FAILED'))
        check(port(8792) and port(8793), 'MCP_PORT_CHANGED_BY_RELAY_REFRESH')
        oauth_protected()
        info('RELAY_REFRESH_PASS: active canonical Run Core source and tests')

        # Never import GitHub credentials into PM2's long-lived environment.
        keep = {k:v for k,v in live.items()
                if k not in ('pm_id','NODE_APP_INSTANCE','PB_GITHUB_SOURCE_TOKEN')
                and not k.startswith('PM2_')}
        old_env = dict(os.environ); old_env.update(keep)
        old_env.pop('PB_GITHUB_SOURCE_TOKEN',None)
        new_env = dict(old_env)
        new_env['PB_CONTROLLED_EXECUTION_HELPER'] = str(new_helper)
        other_before = {str(r.get('pm_id')):(r.get('name'),str((r.get('pm2_env') or {}).get('pm_exec_path')))
                        for r in pm_rows(cli) if r.get('name') != PM2_NAME}
        switched = False
        try:
            command([cli,'delete',str(previous['pm_id'])], timeout=40)
            switched = True
            launch(cli,python,new_server,mcp_root,new_env)
            new_pid = accept(cli,new_server,new_helper)
            probe_helper(new_helper)
            other_after = {str(r.get('pm_id')):(r.get('name'),str((r.get('pm2_env') or {}).get('pm_exec_path')))
                           for r in pm_rows(cli) if r.get('name') != PM2_NAME}
            check(other_before == other_after,'UNRELATED_PM2_SERVICE_CHANGED')
            command([cli,'save'],timeout=45)
            # Inspect saved PM2 binding, rather than treating "pm2 save" as proof.
            dump = HOME / '.pm2/dump.pm2'
            check(dump.is_file(), 'PM2_DUMP_NOT_FOUND_AFTER_SAVE')
            saved = [r for r in json.loads(dump.read_text()) if r.get('name') == PM2_NAME]
            check(len(saved)==1,'PM2_PERSISTENCE_SERVICE_NOT_UNIQUE')
            saved_record=saved[0]
            saved_args=saved_record.get('args') or []
            if isinstance(saved_args,str):saved_args=[saved_args]
            check(saved_args == [str(new_server)],'PM2_PERSISTED_SOURCE_SHA_MISMATCH')
            info(json.dumps({'status':'PASS_FULL_EXACT_SHA_BOOTSTRAP_ACTIVATED',
                'brain_execution_source_sha':BRAIN_SHA,
                'mcp_apps_running_sha':MCP_SHA,
                'mcp_pm2_service':PM2_NAME,
                'running_pid':new_pid,
                'runtime_brain_helper':str(new_helper),
                'runtime_mcp_server':str(new_server),
                'source_model':'TWO_INDEPENDENT_COMPLETE_EXACT_SHA_REPOSITORY_RELEASES',
                'mcp_source_hmac_v2':'PASS','relay_activation_conformance':'PASS',
                'oauth':'PROTECTED','read_mcp_8792':'PRESERVED',
                'pm2_persistence':'PASS',
                'authenticated_chatgpt_tools_list':'REQUIRES_EXTERNAL_FOLLOWUP',
                'end_to_end_brain_execute':'REQUIRES_EXTERNAL_FOLLOWUP'},indent=2))
        except Exception:
            if switched:
                try:
                    for item in pm_rows(cli):
                        if item.get('name') == PM2_NAME:
                            command([cli,'delete',str(item['pm_id'])],timeout=40)
                    launch(cli,python,old_server,old_cwd,old_env)
                    accept(cli,old_server,old_helper)
                    command([cli,'save'],timeout=45)
                    info('ROLLBACK_PASS: prior Execute MCP restored; updated Run Core may remain active')
                except Exception:
                    raise Stop('ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED')
            raise

try:
    main()
except Stop as e:
    print('FAIL_CLOSED: ' + str(e), file=sys.stderr)
    raise SystemExit(2)
except (OSError, ValueError, KeyError, subprocess.TimeoutExpired, urllib.error.URLError, urllib.error.HTTPError) as e:
    # Codes only; never echo request headers, token, process env or raw response.
    print('FAIL_CLOSED: ' + type(e).__name__, file=sys.stderr)
    raise SystemExit(2)
PY