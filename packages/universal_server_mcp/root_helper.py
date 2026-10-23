#!/usr/bin/env python3
"""Universal target-local root helper for the canonical Server Management MCP.

Invoked only via a pinned sudo rule, not from a general network listener.
Host identity, logging tag and executor path are root-owned profile bindings.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sys
import syslog

PROFILE_PATH=Path('/etc/project-brain/server-mcp/profile.json')
MAX_REQUEST=1_100_000
TARGETS={'SERVER-SSD-NODES-BRAIN','SERVER-NETCUP-MAGENTO',
         'SERVER-NETCUP-WORDPRESS','SERVER-P620-WSL'}

def fail():
    return {'status':'FAIL_CLOSED','code':'ROOT_REQUEST_REJECTED'}

def main():
    if os.geteuid()!=0:
        return 2
    result=fail()
    try:
        st=PROFILE_PATH.stat()
        if (not PROFILE_PATH.is_file() or PROFILE_PATH.is_symlink()
            or st.st_uid!=0 or st.st_mode & 0o022):
            raise ValueError('PROFILE_UNTRUSTED')
        profile=json.loads(PROFILE_PATH.read_text())
        if (not isinstance(profile,dict) or profile.get('target_id') not in TARGETS
            or set(profile)!={'target_id','display_name','root_helper',
                                 'auth_packages','bind_port'}):
            raise ValueError('PROFILE_INVALID')
        executor=Path(__file__).resolve().parent/'admin_executor.py'
        if (not executor.is_file() or executor.is_symlink()
            or executor.stat().st_uid!=0 or executor.stat().st_mode & 0o022):
            raise ValueError('EXECUTOR_UNTRUSTED')
        spec=importlib.util.spec_from_file_location('pb_universal_server_admin',executor)
        if spec is None or spec.loader is None:
            raise ValueError('EXECUTOR_IMPORT_INVALID')
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        raw=sys.stdin.buffer.read(MAX_REQUEST+1)
        if not raw or len(raw)>MAX_REQUEST:
            raise ValueError('REQUEST_LENGTH_INVALID')
        request=json.loads(raw)
        if (not isinstance(request,dict) or
            not isinstance(request.get('request_id'),str) or
            len(request['request_id'])<20 or len(request['request_id'])>120):
            raise ValueError('REQUEST_INVALID')
        result=mod.execute(request)
        tag='universal-server-mcp'
        syslog.openlog(tag)
        syslog.syslog(syslog.LOG_AUTHPRIV|syslog.LOG_NOTICE,
                      f"target={profile['target_id']} operation={request.get('operation')} status={result.get('status')} request={request['request_id']}")
    except (ValueError,KeyError,TypeError,OSError,Exception):
        result=fail()
    print(json.dumps(result,sort_keys=True))
    return 0 if result.get('status')=='PASS' else 2

if __name__=='__main__':
    raise SystemExit(main())
