from __future__ import annotations

import json
import re
from unittest.mock import patch
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

    def test_cookie_header_redaction_real_and_escaped_newlines(self) -> None:
        from infrastructure_read_policy.cloudways_helper import redact_text
        samples = (
            "GET /x\nCookie: SID=REAL_COOKIE\nX-End: done",
            r"GET /x\nCookie: SID=ESCAPED_COOKIE\nX-End: done",
            "GET /x\r\nSet-Cookie: SID=CRLF_COOKIE\r\nX-End: done",
            r"GET /x\r\nSet-Cookie: SID=ESCAPED_CRLF_COOKIE\r\nX-End: done",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                actual = redact_text(sample)
                self.assertIn("Cookie: [REDACTED]", actual)
                self.assertNotIn("_COOKIE", actual)
                self.assertIn("X-End: done", actual)

    def test_registered_cloudways_sibling_logs(self) -> None:
        from infrastructure_read_policy import cloudways_helper as module
        public = self.root / "public_html"
        public.mkdir()
        logs = self.root / "logs"
        logs.mkdir()
        good = logs / "static_magento-159271-461445.cloudwaysapps.com.access.log"
        good.write_text('GET /?token_auth=SECRET123&foo=ok HTTP/1.1\\nCookie: PHPSESSID=SECRET456\\n', encoding="utf-8")
        bad = logs / "private.json"
        bad.write_text("private", encoding="utf-8")
        os.environ["MCP_TARGET_ID"] = "SERVER-CLOUDWAYS-MAGENTO"
        os.environ["MCP_ALLOWED_ROOTS_JSON"] = json.dumps([str(public)])
        pattern = re.compile("^" + re.escape(str(public)) + "$")
        with patch.object(module, "CLOUDWAYS_PUBLIC_ROOT_RE", pattern):
            found = execute_request({"action":"FILE_READ","path":str(good)})["result"]["content"]
            self.assertIn("foo=ok", found)
            self.assertNotIn("SECRET123", found)
            self.assertNotIn("SECRET456", found)
            listed = execute_request({"action":"DIR_LIST","path":str(logs)})["result"]["entries"]
            self.assertEqual([x["name"] for x in listed],[good.name])
            with self.assertRaises(PolicyError) as ctx:
                execute_request({"action":"FILE_READ","path":str(bad)})
            self.assertEqual(ctx.exception.code, "LOG_PATH_FILE_TYPE_DENIED")
            link = logs / "escape.log"
            link.symlink_to(self.root / "hello.txt")
            with self.assertRaises(PolicyError):
                execute_request({"action":"FILE_READ","path":str(link)})
        os.environ["MCP_TARGET_ID"] = "TEST-TARGET"
        with patch.object(module, "CLOUDWAYS_PUBLIC_ROOT_RE", pattern):
            with self.assertRaises(PolicyError) as ctx:
                execute_request({"action":"FILE_READ","path":str(good)})
            self.assertEqual(ctx.exception.code, "PATH_OUTSIDE_ALLOWED_ROOTS")

    def test_private_key_whole_block_redacted(self) -> None:
        from infrastructure_read_policy.cloudways_helper import redact_text
        sample = "BEGIN\n-----BEGIN RSA PRIVATE KEY-----\nBASE64_SECRET_PAYLOAD\n-----END RSA PRIVATE KEY-----\nEND"
        result = redact_text(sample)
        self.assertIn("[REDACTED_PRIVATE_KEY_CONTENT]", result)
        self.assertNotIn("BASE64_SECRET_PAYLOAD", result)
        self.assertNotIn("PRIVATE KEY-----", result)

    def test_cookie_regression_real_and_literal_escaped(self) -> None:
        from infrastructure_read_policy.cloudways_helper import redact_text
        samples = (
            "GET /\nCookie: SID=REAL_COOKIE\nX-End: done",
            r"GET /\nCookie: SID=ESCAPED_COOKIE\nX-End: done",
            "GET /\r\nSet-Cookie: SID=CRLF_COOKIE\r\nX-End: done",
            r"GET /\r\nSet-Cookie: SID=ESCAPED_CRLF_COOKIE\r\nX-End: done",
        )
        for sample in samples:
            result = redact_text(sample)
            self.assertNotIn("_COOKIE",result)
            self.assertIn("Cookie: [REDACTED]",result)

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


    def test_v2_safe_os_and_sensitive_path_variants(self):
        os.environ["MCP_TARGET_ID"] = "SERVER-CLOUDWAYS-MAGENTO"
        os.environ["MCP_READ_POLICY_V2"] = "1"
        try:
            if Path("/etc/os-release").is_file():
                self.assertIn("content", execute_request({"action":"FILE_READ","path":"/etc/os-release"})["result"])
            for name in (".env.production", ".env.local", "wp-config.php", "private.key", "dump.sql.gz"):
                p = self.root / name
                p.write_text("password=SECRET")
                with self.assertRaises(PolicyError):
                    execute_request({"action":"FILE_READ","path":str(p)})
        finally:
            os.environ.pop("MCP_READ_POLICY_V2",None)
            os.environ.pop("MCP_V2_SYSTEM_LOG_ROOTS_JSON",None)

    def test_v2_gzip_redaction_binary_and_root_denial(self):
        import gzip
        os.environ["MCP_TARGET_ID"] = "SERVER-CLOUDWAYS-MAGENTO"
        os.environ["MCP_READ_POLICY_V2"] = "1"
        try:
            p = self.root / "example.log.1.gz"
            with gzip.open(p, "wb") as f:
                f.write(b"password=GZIPSECRET\n")
            self.assertNotIn("GZIPSECRET", execute_request({"action":"FILE_READ","path":str(p)})["result"]["content"])
            binary = self.root / "binary.txt"
            binary.write_bytes(b"safe\x00secret")
            with self.assertRaises(PolicyError):
                execute_request({"action":"FILE_READ","path":str(binary)})
            os.environ["MCP_V2_SYSTEM_LOG_ROOTS_JSON"] = '["/"]'
            with self.assertRaises(PolicyError):
                execute_request({"action":"FILE_READ","path":str(p)})
        finally:
            os.environ.pop("MCP_READ_POLICY_V2",None)
            os.environ.pop("MCP_V2_SYSTEM_LOG_ROOTS_JSON",None)


if __name__ == "__main__":
    unittest.main()
