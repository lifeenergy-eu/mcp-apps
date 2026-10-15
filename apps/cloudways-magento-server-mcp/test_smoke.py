#!/usr/bin/env python3
"""Static and user-mode smoke tests for Cloudways Magento Server MCP."""
import ast
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
server = ROOT / "server.py"
helper = ROOT / "user_helper.py"
ast.parse(server.read_text())
ast.parse(helper.read_text())

s = server.read_text()
assert "SERVER-CLOUDWAYS-MAGENTO-DIRECT" in s
assert "PORT == 18794" in s
assert "'control.execute'" in s
assert "['/usr/bin/sudo'" not in s
assert "HELPER=str(HERE / 'user_helper.py')" in s
assert len([n for n in ast.walk(ast.parse(s)) if isinstance(n, ast.FunctionDef) and any(isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool" for d in n.decorator_list)]) == 19

def call(op, **kw):
    p = subprocess.run([sys.executable, "-I", str(helper)], input=json.dumps({"operation":op,"request_id":"TEST-"+"x"*24,**kw}), text=True, capture_output=True, timeout=10)
    obj=json.loads(p.stdout)
    assert obj.get("status") in ("PASS","FAIL_CLOSED","COMMAND_FAILED"), obj
    return obj

if os.geteuid()==0:
    assert call("run",argv=["/usr/bin/id"],cwd="/")["code"] == "ROOT_EXECUTION_FORBIDDEN"
else:
    assert call("run",argv=["/usr/bin/id","-u"],cwd="/")["status"]=="PASS"
    with tempfile.TemporaryDirectory() as d:
        path=str(Path(d)/"probe.txt")
        assert call("write_file",path=path,data_base64=base64.b64encode(b"magento-mcp-probe").decode(),mode=0o600)["status"]=="PASS"
        assert Path(path).read_bytes()==b"magento-mcp-probe"
        assert call("chmod",path=path,mode=0o640)["status"]=="PASS"
        assert call("remove",path=path)["status"]=="PASS"
        assert not Path(path).exists()
print("MAGENTO_MCP_STATIC_AND_HELPER_TESTS_PASS")
