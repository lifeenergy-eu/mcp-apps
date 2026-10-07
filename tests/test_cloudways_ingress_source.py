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

    def test_bridge_is_fixed_loopback_path_allowlisted_and_streaming(self) -> None:
        source = (ROOT / "adapters/cloudways-shared/ingress/pb-mcp/index.php").read_text()
        self.assertIn("http://127.0.0.1:8792", source)
        self.assertIn("CURLOPT_RETURNTRANSFER => false", source)
        self.assertIn("CURLOPT_WRITEFUNCTION", source)
        self.assertIn("X-Accel-Buffering: no", source)
        self.assertNotIn("CURLOPT_FOLLOWLOCATION => true", source)
        self.assertIn("MCP_INGRESS_PATH_DENIED", source)
        self.assertIn("MCP_INGRESS_HOST_DENIED", source)
        self.assertIn("mcp-session-id", source)
        self.assertIn("last-event-id", source)
        control = (ROOT / "adapters/cloudways-shared/ingress/pb-control-mcp/index.php").read_text()
        self.assertIn("http://127.0.0.1:8793", control)
        self.assertIn("CONTROL_MCP_INGRESS_PATH_DENIED", control)

    def test_well_known_metadata_uses_flat_handlers(self) -> None:
        ingress = ROOT / "adapters/cloudways-shared/ingress"
        htaccess = (ingress / ".well-known/.htaccess").read_text()
        self.assertIn("oauth-authorization-server.php", htaccess)
        self.assertIn("oauth-protected-resource.php", htaccess)

        self.assertFalse((ingress / ".well-known/oauth-authorization-server").exists())
        self.assertFalse((ingress / ".well-known/oauth-protected-resource").exists())

        for name in ("oauth-authorization-server.php", "oauth-protected-resource.php"):
            source = (ingress / ".well-known" / name).read_text()
            self.assertIn("require dirname(__DIR__) . '/pb-mcp/index.php';", source)


if __name__ == "__main__":
    unittest.main()
