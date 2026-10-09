from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from infrastructure_read_policy.cloudways_helper import PolicyError, execute_request


class CloudwaysReadPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "allowed"
        self.root.mkdir()
        (self.root / "hello.txt").write_text("hello token=abcdef\n", encoding="utf-8")
        self.db = self.root / "state.db"
        con = sqlite3.connect(self.db)
        con.execute("create table sample(id integer primary key, name text)")
        con.execute("insert into sample(name) values('alpha')")
        con.commit()
        con.close()
        os.environ.update({
            "MCP_TARGET_ID": "TEST-TARGET",
            "MCP_PROFILE_ID": "TEST_PROFILE",
            "MCP_ALLOWED_ROOTS_JSON": json.dumps([str(self.root)]),
            "MCP_ALLOWED_GIT_ROOTS_JSON": "[]",
            "MCP_ALLOWED_SERVICES_JSON": "[]",
            "MCP_ALLOWED_SQLITE_PATHS_JSON": json.dumps([str(self.db)]),
        })

    def tearDown(self) -> None:
        self.tmp.cleanup()
        for name in (
            "MCP_TARGET_ID", "MCP_PROFILE_ID", "MCP_ALLOWED_ROOTS_JSON",
            "MCP_ALLOWED_GIT_ROOTS_JSON", "MCP_ALLOWED_SERVICES_JSON",
            "MCP_ALLOWED_SQLITE_PATHS_JSON",
        ):
            os.environ.pop(name, None)

    def test_file_read_redacts_token(self) -> None:
        result = execute_request({"action": "FILE_READ", "path": str(self.root / "hello.txt")})
        content = result["result"]["content"]
        self.assertIn("[REDACTED]", content)
        self.assertNotIn("abcdef", content)

    def test_sensitive_path_denied(self) -> None:
        secret = self.root / ".env"
        secret.write_text("PASSWORD=nope", encoding="utf-8")
        with self.assertRaises(PolicyError) as ctx:
            execute_request({"action": "FILE_READ", "path": str(secret)})
        self.assertEqual(ctx.exception.code, "SENSITIVE_PATH_DENIED")

    def test_symlink_escape_denied(self) -> None:
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "escape.txt"
        link.symlink_to(outside)
        with self.assertRaises(PolicyError) as ctx:
            execute_request({"action": "FILE_READ", "path": str(link)})
        self.assertEqual(ctx.exception.code, "PATH_OUTSIDE_ALLOWED_ROOTS")

    def test_sqlite_read_only_select(self) -> None:
        result = execute_request({
            "action": "SQLITE_READ_ONLY",
            "path": str(self.db),
            "query": "SELECT id,name FROM sample ORDER BY id",
            "limit": 10,
        })
        self.assertEqual(result["result"]["rows"][0]["name"], "alpha")

    def test_sqlite_mutation_denied(self) -> None:
        with self.assertRaises(PolicyError) as ctx:
            execute_request({
                "action": "SQLITE_READ_ONLY",
                "path": str(self.db),
                "query": "DELETE FROM sample",
            })
        self.assertEqual(ctx.exception.code, "SQLITE_STATEMENT_DENIED")

    def test_sqlite_sensitive_column_query_denied(self) -> None:
        with self.assertRaises(PolicyError) as ctx:
            execute_request({
                "action": "SQLITE_READ_ONLY",
                "path": str(self.db),
                "query": "SELECT token FROM sample",
            })
        self.assertEqual(ctx.exception.code, "SQLITE_SENSITIVE_COLUMN_QUERY_DENIED")

    def test_unknown_action_denied(self) -> None:
        with self.assertRaises(PolicyError) as ctx:
            execute_request({"action": "SHELL"})
        self.assertEqual(ctx.exception.code, "ACTION_DENIED")


    def test_relay_health_bounded_no_log_secrets(self):
        from unittest.mock import patch
        from infrastructure_read_policy import cloudways_helper as module
        import time
        path = Path(self.tmp.name) / "relay"; path.mkdir()
        (path / "dispatcher_daemon.pid").write_text(str(os.getpid()))
        (path / "dispatcher_heartbeat_epoch").write_text(str(int(time.time())))
        (path / "relay.log").write_text('operation_id=PB-TEST-RELAY-RUN-01 FAIL_CLOSED password=DO_NOT_LEAK token=DO_NOT_LEAK')
        os.environ["MCP_TARGET_ID"] = "SERVER-CLOUDWAYS-MAGENTO"
        with patch.object(module, "RELAY_OBSERVABILITY_ROOT", path):
            result=execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH","max_events":4})
        data=result["result"]
        self.assertTrue(data["dispatcher_pid_alive"])
        self.assertLess(data["heartbeat_age_seconds"], 30)
        self.assertEqual(data["recent_operation_ids_matching_uppercase_id_format"],["PB-TEST-RELAY-RUN-01"])
        self.assertIn("FAIL_CLOSED",data["recent_fixed_failure_codes"])
        self.assertNotIn("DO_NOT_LEAK",json.dumps(result))
        self.assertTrue(result["read_only"])
    def test_relay_health_target_and_path_denials(self):
        with self.assertRaises(PolicyError):
            execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH"})
        os.environ["MCP_TARGET_ID"]="SERVER-CLOUDWAYS-MAGENTO"
        with self.assertRaises(PolicyError) as ex:
            execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH","path":"/etc/passwd"})
        self.assertEqual(ex.exception.code,"RELAY_DIAG_PARAMETERS_DENIED")
        with self.assertRaises(PolicyError) as ex:
            execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH","max_events":True})
        self.assertEqual(ex.exception.code,"RELAY_DIAG_LIMIT_DENIED")
    def test_relay_health_symlink_and_missing(self):
        from unittest.mock import patch
        from infrastructure_read_policy import cloudways_helper as module
        path=Path(self.tmp.name)/"relay";path.mkdir()
        os.environ["MCP_TARGET_ID"]="SERVER-CLOUDWAYS-MAGENTO"
        with patch.object(module,"RELAY_OBSERVABILITY_ROOT",path):
            status=execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH"})["result"]
            self.assertIsNone(status["heartbeat_age_seconds"])
            self.assertFalse(status["dispatcher_pid_alive"])
            (path/"relay.log").symlink_to(self.root/"hello.txt")
            with self.assertRaises(PolicyError) as ex:
                execute_request({"action":"PROJECT_BRAIN_RELAY_HEALTH"})
            self.assertEqual(ex.exception.code,"RELAY_DIAG_SYMLINK_DENIED")


if __name__ == "__main__":
    unittest.main()
