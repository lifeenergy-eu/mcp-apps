from __future__ import annotations
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BrainControlledExecutionReleaseV011Test(unittest.TestCase):
    def test_release_identity_and_single_exposed_execution_surface(self):
        source = (ROOT / "apps/project-brain-controlled-execution/server.py").read_text(encoding="utf-8")
        app = json.loads((ROOT / "apps/project-brain-controlled-execution/app.json").read_text(encoding="utf-8"))
        self.assertIn('VERSION = "0.1.1"', source)
        self.assertEqual(app["version"], "0.1.1")
        self.assertEqual(app["tools"], ["brain_execute"])
        self.assertIn('tool.name == "brain_execute"', source)
        self.assertIn('body["primary_execution_tool"] = "brain_execute"', source)
        self.assertIn('body["public_execution_tool_count"] = 1', source)
        self.assertIn('_legacy_handoff("RUN_REGISTERED_TASK")', source)
        self.assertIn('helper_call("RUN_REGISTERED_TASK"', source)
        self.assertNotIn("shell=True", source)

if __name__ == "__main__":
    unittest.main()
