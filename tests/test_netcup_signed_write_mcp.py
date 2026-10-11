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
        self.assertIn("path.resolve(strict=True) != path", source)
        self.assertIn("NETCUP_WRITE_OAUTH_SCOPE_MISMATCH", source)
        self.assertIn("NETCUP_SIGNED_HELPER_PATH_DENIED", source)
        self.assertIn('"/usr/bin/sudo", "-n", str(HELPER)', source)
        self.assertNotIn("shell=True", source)

if __name__ == "__main__":
    unittest.main()
