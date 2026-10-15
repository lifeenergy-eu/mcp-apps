#!/usr/bin/env python3
"""Cloudways Magento user-mode executor. No sudo/root escalation; all requests run as the SSH user.\n"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any

ROOT = Path('/home/master')
MAX_PAYLOAD_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 32768
MAX_COMMAND_SECONDS = 120


class AdminError(Exception):
    pass


def canonical_path(raw: str) -> Path:
    if not isinstance(raw, str) or not raw.startswith('/') or '\x00' in raw:
        raise AdminError('ABSOLUTE_PATH_REQUIRED')
    p = Path(raw)
    # Resolve all existing symlinks to prevent disguising an alternate target.
    # Root '/' is the intentional scope; no narrow allowlist is assumed.
    return p.resolve(strict=False)


def _load_content(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise AdminError('INVALID_BASE64') from exc
    if len(data) > MAX_PAYLOAD_BYTES:
        raise AdminError('CONTENT_TOO_LARGE')
    return data


def execute(request: dict[str, Any]) -> dict[str, Any]:
    op = request.get('operation')
    if op == 'write_file':
        target = canonical_path(request['path'])
        data = _load_content(request['data_base64'])
        if target.is_dir():
            raise AdminError('TARGET_IS_DIRECTORY')
        mode = int(request.get('mode', 0o600))
        if not 0 <= mode <= 0o777:
            raise AdminError('INVALID_MODE')
        parent = target.parent
        if not parent.is_dir():
            raise AdminError('PARENT_NOT_FOUND')
        fd, tmp = tempfile.mkstemp(prefix='.magento-mcp-write-', dir=parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                os.fchmod(handle.fileno(), mode)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            dfd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {'status':'PASS','operation':op,'path':str(target),'bytes_written':len(data)}
    if op == 'mkdir':
        p = canonical_path(request['path'])
        p.mkdir(parents=bool(request.get('parents', False)), exist_ok=bool(request.get('exist_ok', False)))
        return {'status':'PASS','operation':op,'path':str(p)}
    if op == 'remove':
        p = canonical_path(request['path'])
        if p == ROOT or p == Path('/'):
            raise AdminError('ROOT_REMOVAL_DENIED')
        if p.is_dir() and not p.is_symlink():
            if request.get('recursive') is True:
                shutil.rmtree(p)
            else:
                p.rmdir()
        else:
            p.unlink()
        return {'status':'PASS','operation':op,'path':str(p)}
    if op == 'chmod':
        p = canonical_path(request['path'])
        mode = int(request['mode'])
        if not 0 <= mode <= 0o7777:
            raise AdminError('INVALID_MODE')
        p.chmod(mode)
        return {'status':'PASS','operation':op,'path':str(p)}
    if op == 'run':
        argv = request.get('argv')
        if not isinstance(argv,list) or not argv or len(argv)>64 or not all(isinstance(x,str) and x and '\x00' not in x and len(x)<=4096 for x in argv):
            raise AdminError('INVALID_ARGV')
        timeout = int(request.get('timeout_seconds',30))
        if not 1 <= timeout <= MAX_COMMAND_SECONDS:
            raise AdminError('INVALID_TIMEOUT')
        cwd = canonical_path(request.get('cwd','/home/master'))
        try:
            p = subprocess.run(argv,cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,timeout=timeout,check=False,env={'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
        except subprocess.TimeoutExpired:
            return {'status':'FAIL_CLOSED','operation':op,'code':'TIMEOUT'}
        return {'status':'PASS' if p.returncode == 0 else 'COMMAND_FAILED','operation':op,
            'returncode':p.returncode,'stdout':p.stdout[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),
            'stderr':p.stderr[:MAX_OUTPUT_BYTES].decode('utf-8','replace'),
            'stdout_truncated':len(p.stdout)>MAX_OUTPUT_BYTES,'stderr_truncated':len(p.stderr)>MAX_OUTPUT_BYTES}
    raise AdminError('UNKNOWN_OPERATION')


def main() -> int:
    import sys
    raw = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw) > MAX_PAYLOAD_BYTES:
        print(json.dumps({'status':'FAIL_CLOSED','code':'REQUEST_TOO_LARGE'}))
        return 2
    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise AdminError('OBJECT_REQUIRED')
        output = execute(request)
    except (AdminError, KeyError, ValueError, OSError) as exc:
        output = {'status':'FAIL_CLOSED','code':str(exc) if isinstance(exc,AdminError) else 'REQUEST_OR_OS_FAILURE'}
    print(json.dumps(output,sort_keys=True))
    return 0 if output.get('status') == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
