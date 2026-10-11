from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CloudwaysReadV2HelperBindingTest(unittest.TestCase):
    def test_magento_v2_helper_is_release_local_only(self):
        text = (ROOT / "apps/cloudways-infrastructure-access/server.py").read_text()
        self.assertIn('TARGET_ID == "SERVER-CLOUDWAYS-MAGENTO"', text)
        self.assertIn('os.environ.get("MCP_READ_POLICY_V2") == "1"', text)
        self.assertIn('os.environ["MCP_READ_HELPER"] = str(HERE / "helper.py")', text)
        self.assertIn('"read_v2_helper_release_local":', text)
        self.assertIn("default_mode=\"python3_direct\"", text)

if __name__ == "__main__":
    unittest.main()
