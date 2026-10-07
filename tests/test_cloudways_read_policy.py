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


if __name__ == "__main__":
    unittest.main()
