from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from infrastructure_read_policy.client import FixedHelperClient, HelperClientError
from infrastructure_read_policy.tools import TOOL_NAMES


class FixedHelperClientCompatibilityTests(unittest.TestCase):
    def helper(self, body: dict) -> tuple[tempfile.TemporaryDirectory, FixedHelperClient]:
        tmp = tempfile.TemporaryDirectory()
        script = Path(tmp.name) / "helper.py"
        script.write_text(
            "import json,sys\n"
            "_ = sys.stdin.read()\n"
            f"print(json.dumps({body!r}))\n",
            encoding="utf-8",
        )
        return tmp, FixedHelperClient(str(script), mode="python3_direct")

    def test_existing_p620_helper_shape_is_accepted(self) -> None:
        tmp, client = self.helper({
            "status": "PASS",
            "action": "SYSTEM_INFO",
            "read_only": True,
            "result": {"ok": True},
        })
        try:
            result = client.call("SYSTEM_INFO")
            self.assertTrue(result["read_only"])
            self.assertTrue(result["result"]["ok"])
        finally:
            tmp.cleanup()

    def test_helper_explicit_mutation_true_is_rejected(self) -> None:
        tmp, client = self.helper({
            "status": "PASS",
            "action": "SYSTEM_INFO",
            "read_only": True,
            "mutation": True,
        })
        try:
            with self.assertRaises(HelperClientError) as ctx:
                client.call("SYSTEM_INFO")
            self.assertEqual(str(ctx.exception), "MCP_READ_HELPER_POLICY_INVARIANT_FAILED")
        finally:
            tmp.cleanup()

    def test_tool_surface_is_exactly_fourteen_read_only_tools(self) -> None:
        self.assertEqual(len(TOOL_NAMES), 14)
        self.assertEqual(len(set(TOOL_NAMES)), 14)
        self.assertEqual(
            TOOL_NAMES,
            (
                "connector_health",
                "system_info",
                "disk_usage",
                "service_status",
                "journal_read",
                "process_list",
                "socket_list",
                "file_read",
                "file_stat",
                "dir_list",
                "file_find",
                "hash_file",
                "git_read",
                "sqlite_read_only",
            ),
        )


if __name__ == "__main__":
    unittest.main()
