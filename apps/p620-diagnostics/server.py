#!/usr/bin/env python3
"""Permanent P620 Ubuntu Server MCP: direct read and write administration."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from typing import Any

HERE=Path(__file__).resolve().parent
# Installer points this at an existing trusted mcp-apps packages directory.
sys.path.insert(0, os.environ['P620_MCP_AUTH_PACKAGES'])
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp_auth import AUTH_MODE, AUTH_PROVIDER, AUTH_SETTINGS, OAUTH_SCOPES, oauth_login_handler

HOST='127.0.0.1'
PORT=int(os.environ.get('MCP_BIND_PORT','8792'))
PUBLIC_HOST=os.environ['MCP_PUBLIC_HOST']
assert PORT == 8792, 'INVALID_PORT'
assert PUBLIC_HOST and '/' not in PUBLIC_HOST and ':' not in PUBLIC_HOST, 'INVALID_HOST'
assert AUTH_MODE == 'oauth_private', 'PRIVATE_OAUTH_REQUIRED'
assert OAUTH_SCOPES == ['control.execute'], 'OAUTH_SCOPE_MISMATCH'
HELPER='/opt/p620-server-mcp/root_helper.py'
MCP=FastMCP('P620 Server MCP',
    instructions='Direct P620 Ubuntu server administration: authenticated diagnostics, read and write commands. Not a Brain deploy or execution gateway. Never output secrets.',
    host=HOST, port=PORT, streamable_http_path='/mcp',stateless_http=True,json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=['localhost:*','127.0.0.1:*',PUBLIC_HOST,f'{PUBLIC_HOST}:*'],
        allowed_origins=['http://localhost:*','http://127.0.0.1:*',f'https://{PUBLIC_HOST}',f'https://{PUBLIC_HOST}:*']),
    auth=AUTH_SETTINGS,auth_server_provider=AUTH_PROVIDER)
MCP.custom_route('/oauth/login',methods=['GET','POST'],include_in_schema=False)(oauth_login_handler)

RO={'readOnlyHint':True,'openWorldHint':False}
WR={'readOnlyHint':False,'destructiveHint':True,'openWorldHint':False}

def invoke(op: str, **kw: Any) -> dict[str,Any]:
    request={'operation':op,'request_id':'MIG-'+secrets.token_hex(20),**kw}
    try:
        result=subprocess.run(['/usr/bin/sudo','-n','/usr/bin/python3','-I',HELPER],
            input=json.dumps(request),text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            timeout=140,check=False,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin'})
        if len(result.stdout)>100000: return {'status':'ERROR','code':'OUTPUT_TOO_LARGE'}
        output=json.loads(result.stdout)
        return output if isinstance(output,dict) else {'status':'ERROR','code':'INVALID_REPLY'}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {'status':'ERROR','code':'ROOT_HELPER_FAILURE'}

@MCP.tool(annotations=RO)
def connector_health()->dict[str,Any]:
    """P620 Server Server MCP, direct private read and write access."""
    return {'target_id':'SERVER-NETCUP-WORDPRESS','transport':'streamable-http','path':'/mcp',
            'filesystem_root':'/','scope':'control.execute','temporary':False,'host_bind':'127.0.0.1',
            'root_helper':HELPER,'enabled':True,'display_name':'P620 Server Server MCP','read_write':True}

@MCP.tool(annotations=WR)
def run_command(argv:list[str],cwd:str='/',timeout_seconds:int=60)->dict[str,Any]:
    """Execute argv directly on P620 as root, with bounded output and timeout. Permanent direct server administration."""
    return invoke('run',argv=argv,cwd=cwd,timeout_seconds=timeout_seconds)

@MCP.tool(annotations=WR)
def write_file(path:str,content_base64:str,mode:int=384)->dict[str,Any]:
    """Atomically write binary file at absolute path under P620 /; content must be base64."""
    return invoke('write_file',path=path,data_base64=content_base64,mode=mode)

@MCP.tool(annotations=WR)
def create_directory(path:str,parents:bool=True,exist_ok:bool=True)->dict[str,Any]:
    """Create directory or directories under P620 /."""
    return invoke('mkdir',path=path,parents=parents,exist_ok=exist_ok)

@MCP.tool(annotations=WR)
def remove_path(path:str,recursive:bool=False)->dict[str,Any]:
    """Remove file or directory under P620 /. Destructive operation."""
    return invoke('remove',path=path,recursive=recursive)

@MCP.tool(annotations=WR)
def change_permissions(path:str,mode:int)->dict[str,Any]:
    """Change chmod mode on P620 path."""
    return invoke('chmod',path=path,mode=mode)


# Read tools are convenience wrappers over the existing authenticated root helper.
# Every result is bounded by its output limit and shares the same fixed P620 target.
@MCP.tool(annotations=RO)
def system_info()->dict[str,Any]:
    """Read P620 OS, uptime, CPU, memory and hostname."""
    return invoke('run',argv=['/usr/bin/hostnamectl','status'],timeout_seconds=15)

@MCP.tool(annotations=RO)
def disk_usage()->dict[str,Any]:
    """Read filesystem usage."""
    return invoke('run',argv=['/usr/bin/df','-hT'],timeout_seconds=15)

@MCP.tool(annotations=RO)
def service_status(units:list[str])->dict[str,Any]:
    """Read systemd state of explicitly specified service units."""
    if not units or len(units)>20 or any(not isinstance(u,str) or not u.replace('@','').replace('.','').replace('-','').replace('_','').isalnum() for u in units):
        return {'status':'ERROR','code':'INVALID_UNITS'}
    return invoke('run',argv=['/usr/bin/systemctl','show',*units,'--property=Id,LoadState,ActiveState,SubState,UnitFileState','--no-pager'],timeout_seconds=20)

@MCP.tool(annotations=RO)
def journal_read(unit:str,lines:int=80)->dict[str,Any]:
    """Read recent journal for one explicitly named unit, without secret env files."""
    if not isinstance(unit,str) or not unit.replace('@','').replace('.','').replace('-','').replace('_','').isalnum() or not 1<=lines<=300:
        return {'status':'ERROR','code':'INVALID_JOURNAL_ARGUMENTS'}
    return invoke('run',argv=['/usr/bin/journalctl','-u',unit,'-n',str(lines),'--no-pager','--output=short-iso'],timeout_seconds=20)

@MCP.tool(annotations=RO)
def process_list()->dict[str,Any]:
    """Read bounded active process list."""
    return invoke('run',argv=['/usr/bin/ps','-eo','pid,user,stat,comm,%cpu,%mem','--sort=-%cpu'],timeout_seconds=15)

@MCP.tool(annotations=RO)
def socket_list()->dict[str,Any]:
    """Read listening TCP and UDP ports."""
    return invoke('run',argv=['/usr/bin/ss','-lntup'],timeout_seconds=15)

@MCP.tool(annotations=RO)
def file_stat(path:str)->dict[str,Any]:
    """Read filesystem metadata, without revealing file contents."""
    if not isinstance(path,str) or not path.startswith('/') or '\\x00' in path:
        return {'status':'ERROR','code':'INVALID_PATH'}
    return invoke('run',argv=['/usr/bin/stat','--',path],timeout_seconds=15)

@MCP.tool(annotations=RO)
def dir_list(path:str)->dict[str,Any]:
    """Read a directory listing."""
    if not isinstance(path,str) or not path.startswith('/') or '\\x00' in path:
        return {'status':'ERROR','code':'INVALID_PATH'}
    return invoke('run',argv=['/usr/bin/ls','-la','--',path],timeout_seconds=15)


def _readable_path(path:str)->bool:
    if not isinstance(path,str) or not path.startswith('/') or '\\x00' in path:
        return False
    p=Path(path).resolve(strict=False)
    blocked=('/etc/shadow','/etc/gshadow','/etc/project-brain/secrets','/root',
             '/etc/ssl/private','/etc/project-brain/mcp')
    return not any(str(p)==x or str(p).startswith(x+'/') for x in blocked)

@MCP.tool(annotations=RO)
def file_read(path:str,lines:int=100)->dict[str,Any]:
    """Read bounded non-secret text files; credential paths denied."""
    if not _readable_path(path) or not 1<=lines<=300:
        return {'status':'ERROR','code':'PATH_OR_LINES_DENIED'}
    return invoke('run',argv=['/usr/bin/head','-n',str(lines),'--',path],timeout_seconds=15)

@MCP.tool(annotations=RO)
def file_find(root:str,name:str,max_depth:int=3)->dict[str,Any]:
    """Find file names under an explicit non-secret directory."""
    if not _readable_path(root) or not isinstance(name,str) or not name or '/' in name or not 1<=max_depth<=5:
        return {'status':'ERROR','code':'INVALID_FIND'}
    return invoke('run',argv=['/usr/bin/find',root,'-maxdepth',str(max_depth),'-name',name,'-print'],timeout_seconds=20)

@MCP.tool(annotations=RO)
def hash_file(path:str)->dict[str,Any]:
    """Compute SHA256 for non-secret file."""
    if not _readable_path(path):
        return {'status':'ERROR','code':'PATH_DENIED'}
    return invoke('run',argv=['/usr/bin/sha256sum','--',path],timeout_seconds=30)

@MCP.tool(annotations=RO)
def git_read(repository_path:str,operation:str='status')->dict[str,Any]:
    """Read Git repository status or HEAD, never mutate Git."""
    if not _readable_path(repository_path) or operation not in ('status','head','remote'):
        return {'status':'ERROR','code':'INVALID_GIT_READ'}
    args={'status':['status','--short'],'head':['rev-parse','HEAD'],'remote':['remote','-v']}[operation]
    return invoke('run',argv=['/usr/bin/git','-C',repository_path,*args],timeout_seconds=20)

@MCP.tool(annotations=RO)
def sqlite_read_only(path:str,query:str)->dict[str,Any]:
    """Read SQLite data through SELECT/WITH only."""
    if not _readable_path(path) or not isinstance(query,str) or len(query)>4000 or not query.lstrip().lower().startswith(('select ','with ')):
        return {'status':'ERROR','code':'SQL_READ_ONLY_REQUIRED'}
    return invoke('run',argv=['/usr/bin/sqlite3','-readonly',path,query],timeout_seconds=20)

if __name__=='__main__':
    uvicorn.run(MCP.streamable_http_app(),host=HOST,port=PORT)
