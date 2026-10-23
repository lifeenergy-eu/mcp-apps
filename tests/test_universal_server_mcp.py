#!/usr/bin/env python3
"""Source-only acceptance for the unified four-host Server Management MCP."""
import ast
import base64
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"packages/universal_server_mcp"
TARGETS={
    "SERVER-SSD-NODES-BRAIN":18795,
    "SERVER-NETCUP-MAGENTO":18793,
    "SERVER-NETCUP-WORDPRESS":18793,
    "SERVER-P620-WSL":8792,
}
EXPECTED_TOOLS={
    "connector_health","run_command","write_file","create_directory",
    "remove_path","change_permissions","system_info","disk_usage",
    "service_status","journal_read","process_list","socket_list",
    "file_stat","dir_list","file_read","file_find","hash_file",
    "git_read","sqlite_read_only",
}
# Actual Server MCP installations currently expose 19 named methods including
# the general connector health method. This test enforces exact surface parity.

class UniversalServerMCPTest(unittest.TestCase):
    def test_all_source_files_syntax(self):
        for name in ("server.py","admin_executor.py","root_helper.py"):
            with self.subTest(name=name):
                ast.parse((BASE/name).read_text(),filename=name)

    def test_exact_tools(self):
        tree=ast.parse((BASE/"server.py").read_text())
        names={f.name for f in tree.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))
              and any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute)
                      and d.func.attr=="tool" for d in f.decorator_list)}
        self.assertEqual(names,EXPECTED_TOOLS)

    def test_four_profiles(self):
        profiles=list((BASE/"profiles").glob("*.json"))
        self.assertEqual(len(profiles),4)
        seen=set()
        for path in profiles:
            row=json.loads(path.read_text())
            self.assertEqual(set(row),{"target_id","display_name","root_helper","auth_packages","bind_port"})
            target=row["target_id"]
            self.assertIn(target,TARGETS)
            self.assertNotIn(target,seen)
            self.assertEqual(row["bind_port"],TARGETS[target])
            self.assertTrue(row["root_helper"].startswith("/opt/"))
            self.assertTrue(row["auth_packages"].startswith("/opt/"))
            seen.add(target)
        self.assertEqual(seen,set(TARGETS))

    def test_no_bypass_or_deploy_runner(self):
        s=(BASE/"server.py").read_text()
        for forbidden in ("subprocess.Popen(","shell=True","os.system(","eval(","exec("):
            self.assertNotIn(forbidden,s)
        self.assertIn("AUTH_MODE == 'oauth_private'",s)
        self.assertIn("OAUTH_SCOPES == ['control.execute']",s)
        self.assertIn("PROFILE['target_id']",s)

    def test_shared_executor_is_functional_in_isolated_directory(self):
        module_path=BASE/"admin_executor.py"
        spec=importlib.util.spec_from_file_location("universal_admin_devtest",module_path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory(prefix="pb-universal-mcp-dev-") as tmp:
            target=Path(tmp)/"probe.txt"
            payload={"operation":"write_file","path":str(target),
                     "data_base64":base64.b64encode(b"unified").decode(),"mode":0o600}
            self.assertEqual(mod.execute(payload)["status"],"PASS")
            self.assertEqual(target.read_bytes(),b"unified")
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(mod.execute({"operation":"remove","path":str(target)})["status"],"PASS")
            self.assertFalse(target.exists())

    def test_shared_executor_rejects_invalid_inputs(self):
        module_path=BASE/"admin_executor.py"
        spec=importlib.util.spec_from_file_location("universal_admin_negative",module_path)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with self.assertRaises(mod.AdminError):
            mod.execute({"operation":"remove","path":"/"})
        with self.assertRaises(mod.AdminError):
            mod.execute({"operation":"run","argv":[]})
        with self.assertRaises(mod.AdminError):
            mod.execute({"operation":"write_file","path":"/tmp/invalid",
                         "data_base64":"not-base64$"})

    def test_root_helper_pinned_existing_protocol(self):
        s=(BASE/"root_helper.py").read_text()
        self.assertIn("os.geteuid()!=0",s)
        self.assertIn("PROFILE_PATH.is_symlink()",s)
        self.assertIn("ROOT_REQUEST_REJECTED",s)
        self.assertIn("syslog.LOG_AUTHPRIV",s)

if __name__=="__main__":
    unittest.main()
