#!/usr/bin/env bash
set -euo pipefail
# Usage: bash deploy_mcp_apps_magento_sha.sh MCP_APPS_SHA [BRAIN_SHA]
# Existing on-host exact releases only. No git, token, SSH, secret reads or new PM2 service.
MCP_SHA="${1:-}"
BRAIN_SHA="${2:-0f672966f862c6f08e9c208c0c7ff1aaef27ef66}"
[[ "$MCP_SHA" =~ ^[0-9a-f]{40}$ && "$BRAIN_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'Usage: bash deploy_mcp_apps_magento_sha.sh <40-character MCP_APPS_SHA> [40-character BRAIN_SHA]' >&2
  exit 2
}
MCP_SHA="$MCP_SHA" BRAIN_SHA="$BRAIN_SHA" python3 - <<'PY'
import ast,glob,hashlib,json,os,re,shutil,socket,subprocess,sys,time,urllib.error,urllib.request
from pathlib import Path
NAME='project-brain-controlled-execution-mcp'
BASE=Path('/home/master/.project-brain/control-plane/controlled-execution-mcp')
MCP_SHA=os.environ['MCP_SHA']; BRAIN_SHA=os.environ['BRAIN_SHA']
PIN_MCP='797c99330e1cbb505fb04fc4889bcd1fec018093'
PIN_BRAIN='0f672966f862c6f08e9c208c0c7ff1aaef27ef66'
MCP_BLOB='c5d6845d00c61b4df1037dd1422d7641316eb098'
BRAIN_BLOB='31bf4fdd65610f782a85448d28060e7b698904d1'
RELS={'mcp':'apps/project-brain-controlled-execution/server.py','brain':'control-plane/controlled-execution/helper.py'}

def deny(code): raise RuntimeError(code)
def run(args,env=None,timeout=45):
 p=subprocess.run(args,capture_output=True,text=True,env=env,timeout=timeout)
 if p.returncode:deny('COMMAND_FAILED '+str(args[:2])+' '+p.stderr[:220])
 return p.stdout

def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def port(n):
 try:
  with socket.create_connection(('127.0.0.1',n),timeout=2):return True
 except OSError:return False

def procenv(pid):
 d={}
 for part in (Path('/proc')/str(pid)/'environ').read_bytes().split(b'\0'):
  if b'=' in part:
   k,v=part.split(b'=',1);d[os.fsdecode(k)]=os.fsdecode(v)
 return d

if os.geteuid()==0:deny('RUN_AS_MASTER_NOT_ROOT')
candidates=[shutil.which('pm2'),'/home/master/.nvm/versions/node/v22.22.2/bin/pm2',
 *sorted(glob.glob('/home/master/.nvm/versions/node/v*/bin/pm2'),reverse=True)]
cli=next((x for x in dict.fromkeys(candidates) if x and Path(x).is_file() and os.access(x,os.X_OK)),None)
if not cli:deny('EXISTING_PM2_NOT_FOUND')
os.environ['PATH']=str(Path(cli).parent)+os.pathsep+os.environ.get('PATH','')
def rows():return [x for x in json.loads(run([cli,'jlist'])) if x.get('name')==NAME]
found=rows()
if len(found)!=1 or (found[0].get('pm2_env') or {}).get('status')!='online':deny('PM2_NOT_UNIQUE_ONLINE')
old=found[0];pm=old['pm2_env'];pid=old['pid'];live=procenv(pid)
old_args=pm.get('args') or []
if isinstance(old_args,str):old_args=[old_args]
if len(old_args)!=1:deny('PM2_SERVER_ARGS_INVALID')
old_server=Path(old_args[0]);old_helper=Path(live.get('PB_CONTROLLED_EXECUTION_HELPER',''))
py=Path(pm.get('pm_exec_path',''));cwd=str(pm.get('pm_cwd') or '')
if not old_server.is_file() or not old_helper.is_file() or not py.is_file():deny('CURRENT_RUNTIME_FILES_MISSING')
if not port(8792) or not port(8793):deny('MCP_PORT_MISSING')
for k in ('MCP_PUBLIC_HOST','MCP_OAUTH_DB_PATH','MCP_OAUTH_PASSWORD_FILE'):
 if not live.get(k):deny('OAUTH_ENV_MISSING_'+k)
def oauth_gate():
 try:urllib.request.urlopen('http://127.0.0.1:8793/mcp',timeout=3);deny('OAUTH_UNPROTECTED')
 except urllib.error.HTTPError as e:
  if e.code not in (401,403):deny('OAUTH_GATE_INVALID_'+str(e.code))
oauth_gate()
print('PREFLIGHT_PASS: existing PM2, OAuth, 8792/8793',flush=True)

# Historical verified 2-file overlay, exactly as successful previous deployment.
# Future SHAs must have a full source release plus Brain's exact-SHA manifest.
source_root=Path('/home/master/.project-brain/control-plane/runtime/source-ingress')
def locate(kind,sha):
 repo='lifeenergy-eu__mcp-apps' if kind=='mcp' else 'lifeenergy-eu__project-brain'
 expected='lifeenergy-eu/mcp-apps' if kind=='mcp' else 'lifeenergy-eu/project-brain'
 root_options=[BASE/('mcp-apps' if kind=='mcp' else 'brain-source')/sha,
               source_root/'releases'/repo/sha,
               Path('/home/master/.project-brain/control-plane/controlled-execution-mcp')/('mcp-apps' if kind=='mcp' else 'brain-source')/('overlay-'+sha)]
 for root in root_options:
  file=root/RELS[kind]
  if not file.is_file():continue
  manifest=root/'.pb-source-manifest.json'
  if manifest.is_file():
   m=json.loads(manifest.read_text())
   if m.get('repository')!=expected or m.get('source_sha')!=sha:deny('SOURCE_MANIFEST_IDENTITY_MISMATCH_'+kind)
   files=m.get('files') or []
   row=next((r for r in files if isinstance(r,dict) and r.get('path')==RELS[kind]),None)
   if not row or hashlib.sha256(file.read_bytes()).hexdigest()!=row.get('sha256'):deny('SOURCE_MANIFEST_FILE_HASH_MISMATCH_'+kind)
   return root,file,'MANIFEST_VERIFIED'
  if (kind=='mcp' and sha==PIN_MCP and blob(file.read_bytes())==MCP_BLOB) or (kind=='brain' and sha==PIN_BRAIN and blob(file.read_bytes())==BRAIN_BLOB):
   return root,file,'KNOWN_EXACT_FILE_BLOB_OVERLAY'
 deny('SHA_SOURCE_NOT_LOCALLY_VERIFIED_'+kind+': '+sha+'. Materialize registered exact-SHA source through Brain first; no PM2 changes made.')

mr,server,ms=locate('mcp',MCP_SHA)
br,helper,bs=locate('brain',BRAIN_SHA)
if mr==br:deny('MCP_AND_BRAIN_SOURCE_ROOT_CONFLICT')
ast.parse(server.read_text());ast.parse(helper.read_text())
compiler=br/'control-plane/run-core/chat_intent_compiler.py'
if not compiler.is_file() or 'if intent == "DEPLOY":' not in compiler.read_text():deny('BRAIN_DEPLOY_COMPILER_MISSING')
if 'set(task) == {"repository", "commit_sha"}' not in helper.read_text():deny('BRAIN_HELPER_PUBLIC_SHA_INPUT_MISSING')
if not port(8792):deny('READ_MCP_8792_PRE_SWITCH_FAILED')
print('SOURCE_PASS:',MCP_SHA,ms,BRAIN_SHA,bs,flush=True)

clean={k:v for k,v in live.items() if k not in ('pm_id','NODE_APP_INSTANCE') and not k.startswith('PM2_')}
old_env=os.environ.copy();old_env.update(clean)
new_env=old_env.copy();new_env['PB_CONTROLLED_EXECUTION_HELPER']=str(helper)
newcwd=str(mr)
def start(target,root,env):run([cli,'start',str(py),'--name',NAME,'--interpreter','none','--cwd',root,'--',str(target)],env=env)
def accept(target,helper_path):
 for _ in range(35):
  z=rows()
  if len(z)==1 and (z[0].get('pm2_env') or {}).get('status')=='online':
   newpid=z[0].get('pid'); args=z[0]['pm2_env'].get('args') or []
   if isinstance(args,str):args=[args]
   if isinstance(newpid,int) and newpid>1:
    try:
     pe=procenv(newpid)
     if args==[str(target)] and pe.get('PB_CONTROLLED_EXECUTION_HELPER')==str(helper_path) and port(8792) and port(8793):
      oauth_gate();return
    except (OSError,ValueError):pass
  time.sleep(1)
 deny('PM2_ACCEPTANCE_FAILED')

if server==old_server and helper==old_helper:
 print(json.dumps({'status':'ALREADY_ACTIVE','mcp_sha':MCP_SHA,'brain_sha':BRAIN_SHA,'pm2_unchanged':True}));sys.exit(0)
others_before={x.get('name'):x.get('pm_id') for x in json.loads(run([cli,'jlist'])) if x.get('name')!=NAME}
switched=False
try:
 run([cli,'delete',str(old['pm_id'])]);switched=True
 start(server,newcwd,new_env);accept(server,helper)
 others_after={x.get('name'):x.get('pm_id') for x in json.loads(run([cli,'jlist'])) if x.get('name')!=NAME}
 if others_before!=others_after:deny('OTHER_PM2_PROCESS_CHANGED')
 run([cli,'save'])
 print(json.dumps({'status':'PASS_PM2_ACTIVATED','mcp_sha':MCP_SHA,'brain_sha':BRAIN_SHA,
 'mcp_server':str(server),'brain_helper':str(helper),'mcp_source_verification':ms,'brain_source_verification':bs,
 'oauth':'PROTECTED','read_mcp_8792':'PRESERVED',
 'full_exact_sha_materialization':ms=='MANIFEST_VERIFIED' and bs=='MANIFEST_VERIFIED'},indent=2))
except Exception:
 if switched:
  try:
   for x in rows():run([cli,'delete',str(x['pm_id'])])
   start(old_server,cwd,old_env);accept(old_server,old_helper);run([cli,'save'])
   print('ROLLBACK_PASS',file=sys.stderr)
  except Exception as exc:print('ROLLBACK_FAILED: '+str(exc),file=sys.stderr)
 raise
PY
