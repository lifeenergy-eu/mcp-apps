from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ControlledExecutionSourceTests(unittest.TestCase):
    def test_app_is_typed_and_has_no_generic_execution_tool(self) -> None:
        app = json.loads((ROOT / "apps/project-brain-controlled-execution/app.json").read_text())
        self.assertFalse(app["execution_authority"])
        self.assertFalse(app["arbitrary_shell"])
        self.assertFalse(app["raw_sql"])
        self.assertFalse(app["caller_selected_runner"])
        self.assertEqual(app["oauth"]["scopes"], ["control.execute"])
        self.assertEqual(set(app["tools"]), {
            "connector_health","deploy_registered_source","run_registered_application_workflow",
            "run_registered_database_workflow","execution_status"
        })

    def test_server_uses_one_fixed_helper_without_shell(self) -> None:
        source = (ROOT / "apps/project-brain-controlled-execution/server.py").read_text()
        self.assertIn('PB_CONTROLLED_EXECUTION_HELPER', source)
        self.assertIn('["/usr/bin/python3", HELPER]', source)
        self.assertIn("shell=False", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("@mcp.tool", source.split("def helper_call",1)[0])

    def test_ingress_is_fixed_to_loopback_8793_and_control_prefix(self) -> None:
        source=(ROOT / "adapters/cloudways-shared/ingress/pb-control-mcp/index.php").read_text()
        self.assertIn("127.0.0.1:8793", source)
        self.assertIn("/pb-control-mcp", source)
        self.assertIn("CONTROL_MCP_INGRESS_PATH_DENIED", source)
        self.assertIn("CURLOPT_FOLLOWLOCATION=>false", source)

    def test_controlled_support_files_use_real_line_endings(self) -> None:
        app_root = ROOT / "apps/project-brain-controlled-execution"
        requirements = (app_root / "requirements.txt").read_text()
        oauth = (app_root / "OAUTH.md").read_text()
        auth_handler = (ROOT / "adapters/cloudways-shared/ingress/.well-known/oauth-authorization-server-control.php").read_text()
        resource_handler = (ROOT / "adapters/cloudways-shared/ingress/.well-known/oauth-protected-resource-control.php").read_text()

        for content in (requirements, oauth, auth_handler, resource_handler):
            self.assertNotIn("\\n", content)

        self.assertEqual(requirements.splitlines(), [
            "mcp==1.26.0",
            "uvicorn>=0.30,<1",
            "python-multipart>=0.0.20,<1",
        ])
        self.assertTrue(auth_handler.startswith("<?php\ndeclare(strict_types=1);\n"))
        self.assertTrue(resource_handler.startswith("<?php\ndeclare(strict_types=1);\n"))


if __name__ == "__main__":
    unittest.main()
