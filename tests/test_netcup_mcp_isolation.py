import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "packages/infrastructure_read_policy/netcup_helper.py"
ENTRY = ROOT / "apps/cloudways-infrastructure-access/helper.py"
PROFILE = ROOT / "adapters/netcup-wordpress/profile.json"

class NetcupMcpIsolationTests(unittest.TestCase):
    def test_implementation_parses(self):
        ast.parse(MODULE.read_text())
        ast.parse(ENTRY.read_text())

    def test_target_separation(self):
        src = MODULE.read_text()
        entry = ENTRY.read_text()
        for value in ("SERVER-NETCUP-WORDPRESS", "NETCUP_WORDPRESS_ROOT_SERVER_V1", "NETCUP_SELF_MANAGED_ROOT_SERVER", "NETCUP_READ_TARGET_ENV_MISMATCH", "NETCUP_READ_SQLITE_NOT_ACTIVATED"):
            self.assertIn(value, src)
        self.assertIn("MCP_TARGET_CLASS", entry)
        self.assertIn("cloudways_helper", entry)

    def test_root_and_write_isolation(self):
        source = MODULE.read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("sudo", source)
        self.assertIn("NETCUP_READ_ROOTS_UNSAFE", source)
        profile = json.loads(PROFILE.read_text())
        self.assertEqual(profile["status"], "SOURCE_ONLY_NOT_DEPLOYED")
        self.assertFalse(profile["write"]["arbitrary_shell"])
        self.assertEqual(profile["write"]["authority"], "PROJECT_BRAIN_RUN_CORE_ONLY")
        self.assertFalse(profile["transport"]["public_unauthenticated"])

if __name__ == "__main__":
    unittest.main()
