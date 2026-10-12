import ast
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps/netcup-controlled-execution/server.py"
PROFILE = ROOT / "apps/netcup-controlled-execution/app.json"

class NetcupSignedWriteMcpTests(unittest.TestCase):
    def test_source_and_posture(self):
        source = SOURCE.read_text()
        ast.parse(source)
        app = json.loads(PROFILE.read_text())
        self.assertEqual(app["target_id"], "SERVER-NETCUP-WORDPRESS")
        self.assertEqual(app["bind"], "127.0.0.1:8793")
        self.assertFalse(app["public_chatgpt_execution"])
        self.assertFalse(app["access"]["arbitrary_shell"])
        self.assertFalse(app["access"]["standalone_deploy"])
        self.assertIn("TICKET_KEYS", source)
        self.assertIn("sys.path.insert(0, str(candidate))", source)
        self.assertIn("item.resolve(strict=True) != item", source)
        self.assertIn("item.stat().st_uid != 0", source)
        self.assertIn("item.stat().st_mode & 0o022", source)
        self.assertIn("NETCUP_WRITE_OAUTH_SCOPE_MISMATCH", source)
        self.assertIn("NETCUP_SIGNED_HELPER_PATH_DENIED", source)
        self.assertIn('"/usr/bin/sudo", "-n", "/usr/bin/env"', source)
        self.assertIn('f"PYTHONPATH={HELPER.parent.parent}"', source)
        self.assertIn('"/usr/bin/python3", "-P", str(HELPER)', source)
        self.assertIn('path.parent / "agent.py"', source)
        self.assertNotIn('"/usr/bin/sudo", "-n", str(HELPER)', source)
        self.assertIn("TICKET_REPLAY_REJECTED", source)
        self.assertIn("safe_codes", source)
        self.assertNotIn("shell=True", source)

if __name__ == "__main__":
    unittest.main()
