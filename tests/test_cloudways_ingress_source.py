from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CloudwaysIngressSourceTests(unittest.TestCase):
    def test_target_public_urls_are_fixed(self) -> None:
        mag = json.loads((ROOT / "adapters/cloudways-magento/profile.json").read_text())
        wp = json.loads((ROOT / "adapters/cloudways-wordpress/profile.json").read_text())
        self.assertEqual(mag["public_ingress"]["resource_url"], "https://ai-runtime.larimarcode.com/pb-mcp/mcp")
        self.assertEqual(wp["public_ingress"]["resource_url"], "https://smoothiebarmen.com/pb-mcp/mcp")
        self.assertEqual(mag["public_ingress"]["backend_bind"], "127.0.0.1:8792")
        self.assertEqual(wp["public_ingress"]["backend_bind"], "127.0.0.1:8792")

    def test_bridge_is_fixed_loopback_and_path_allowlisted(self) -> None:
        source = (ROOT / "adapters/cloudways-shared/ingress/pb-mcp/index.php").read_text()
        self.assertIn("http://127.0.0.1:8792", source)
        self.assertNotIn("CURLOPT_FOLLOWLOCATION => true", source)
        self.assertIn("MCP_INGRESS_PATH_DENIED", source)
        self.assertIn("MCP_INGRESS_HOST_DENIED", source)

if __name__ == "__main__":
    unittest.main()
