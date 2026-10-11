from pathlib import Path
import ast
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/cloudways-infrastructure-access"

class NetcupReadProfileContractTests(unittest.TestCase):
    def test_shared_app_source_parses(self):
        ast.parse((APP / "server.py").read_text(encoding="utf-8"))

    def test_explicit_target_guard_prevents_cloudways_env_reuse(self):
        src = (APP / "server.py").read_text(encoding="utf-8")
        for required in (
            'MCP_TARGET_CLASS', 'NETCUP_SELF_MANAGED_ROOT_SERVER',
            'NETCUP_WORDPRESS_ROOT_SERVER_V1', 'SERVER-NETCUP-WORDPRESS',
            'NETCUP_TARGET_PROFILE_MISMATCH', 'NETCUP_MCP_LOOPBACK_REQUIRED',
            'NETCUP_READ_OAUTH_REQUIRED', 'NETCUP_TARGET_CLASS_REQUIRED',
        ):
            self.assertIn(required, src)

    def test_read_only_net_cup_source_manifest(self):
        app = json.loads((APP / "app.json").read_text(encoding="utf-8"))
        self.assertIn("NETCUP_WORDPRESS_ROOT_SERVER_V1", app["target_profiles"])
        self.assertTrue(app["read_only"])
        self.assertFalse(app["arbitrary_shell"])
        self.assertFalse(app["mutation_tools"])
        self.assertFalse(app["deploy_tools"])
        self.assertEqual(app["target_class_selection"]["activation_status"], "SOURCE_CANDIDATE_NO_NETCUP_DEPLOY")

if __name__ == "__main__":
    unittest.main()
