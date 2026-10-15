#!/usr/bin/env python3
"""Root-only P620 server administration helper, callable only through pinned sudo."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, '/opt/p620-server-mcp')
from admin_executor import execute,AdminError

def main() -> int:
    if os.geteuid()!=0:
        return 2
    raw=sys.stdin.buffer.read(1_200_000)
    try:
        if len(raw)>1_100_000: raise AdminError('REQUEST_TOO_LARGE')
        obj=json.loads(raw)
        if not isinstance(obj,dict) or not isinstance(obj.get('request_id'),str) or len(obj['request_id'])<20:
            raise AdminError('REQUEST_INVALID')
        # Never output raw input/keys to journal; write audited operation metadata only.
        output=execute(obj)
        import syslog
        syslog.openlog('p620-server-mcp')
        syslog.syslog(syslog.LOG_AUTHPRIV|syslog.LOG_NOTICE, f"operation={obj.get('operation')} status={output.get('status')} request={obj['request_id']}")
    except (AdminError, ValueError, KeyError, OSError, TypeError) as exc:
        output={'status':'FAIL_CLOSED','code':'ROOT_REQUEST_REJECTED'}
    print(json.dumps(output,sort_keys=True))
    return 0 if output.get('status')=='PASS' else 2

if __name__=='__main__':raise SystemExit(main())
