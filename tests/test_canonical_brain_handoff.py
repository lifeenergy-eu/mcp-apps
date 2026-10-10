"""Contract-only source tests. No network, production writes or credentials."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class CanonicalBrainHandoffTest(unittest.TestCase):
    def test_p620_deploy_is_handoff_not_inbound_execution(self):
        mod = load("adapters/p620/controlled-execution-relay-helper.py", "p620_handoff_contract")
        r = mod.dispatch({"action":"DEPLOY_REGISTERED_SOURCE",
                          "payload":{"system_id":"SYSTEM-LOCAL-AI","source_sha":"a"*40}})
        self.assertEqual(r["status"], "HANDOFF_REQUIRED")
        self.assertEqual(r["next_tool"], "brain_execute")
        self.assertEqual(r["next_intent_key"], "P620_RUNTIME_DEPLOY")
        self.assertEqual(r["next_intent_inputs"], {"p620_runtime_sha":"a"*40})
        self.assertFalse(r["execution_performed"])
    def test_p620_unregistered_target_fails_closed(self):
        mod = load("adapters/p620/controlled-execution-relay-helper.py", "p620_handoff_denied")
        r = mod.dispatch({"action":"DEPLOY_REGISTERED_SOURCE",
                          "payload":{"system_id":"SYSTEM-WORDPRESS","source_sha":"a"*40}})
        self.assertEqual(r["status"], "FAIL_CLOSED")
    def test_wp_deploy_is_central_handoff(self):
        mod = load("adapters/cloudways-wordpress/controlled-execution-relay-helper.py", "wp_handoff_contract")
        r = mod.dispatch({"action":"DEPLOY_REGISTERED_SOURCE", "payload":{}})
        self.assertEqual(r["status"], "HANDOFF_REQUIRED")
        self.assertEqual(r["next_tool"], "brain_execute")
        self.assertFalse(r["execution_performed"])
    def test_wp_registered_probe_remains_registered(self):
        mod = load("adapters/cloudways-wordpress/controlled-execution-relay-helper.py", "wp_probe_contract")
        r = mod.dispatch({"action":"RUN_APPLICATION_WORKFLOW",
                          "payload":{"workflow_id":"WORDPRESS_CAPABILITY_PROBE_V1",
                                     "operation":{"app_id":"wsbmznzrem"}}})
        self.assertEqual(r["status"], "HANDOFF_REQUIRED")
        self.assertEqual(r["next_intent_key"], "WORDPRESS_GUARDED_PROBE")
        self.assertEqual(r["mutation"], {"action":"capability_probe", "app_id":"wsbmznzrem"})
if __name__=="__main__":
    unittest.main()
