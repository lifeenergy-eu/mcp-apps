"""Source-level security contract for Project Brain's MCP ingress.

Run: python3 -m unittest discover -s tests -p 'test_controlled_execution_surface.py'
No plugin import, credentials, network, or runtime mutation.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "apps/project-brain-controlled-execution/server.py"

class ControlledExecutionSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SERVER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_named_task_has_only_task_and_bounded_wait_inputs(self):
        fn = next(node for node in self.tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "run_registered_task")
        self.assertEqual([arg.arg for arg in fn.args.args], ["task", "wait_seconds"])
        self.assertIn('_legacy_handoff("RUN_REGISTERED_TASK")', ast.get_source_segment(self.source, fn))

    def test_brain_execute_is_intent_only(self):
        fn = next(node for node in self.tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "brain_execute")
        self.assertEqual([arg.arg for arg in fn.args.args], ["task", "wait_seconds"])
        self.assertIn("RUN_REGISTERED_TASK", ast.get_source_segment(self.source, fn))

    def test_default_tool_discovery_is_single_mutation_ingress(self):
        self.assertNotIn('PB_EXPOSE_LEGACY_WRITE_TOOLS', self.source)
        self.assertIn('tool.name == "brain_execute"', self.source)
        # Existing typed workflow functions remain present for compatibility.
        names = {node.name for node in self.tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({"deploy_registered_source", "run_registered_application_workflow",
                         "run_registered_database_workflow", "run_registered_task"}.issubset(names))

    def test_tool_discovery_filter_precedes_auth_enrichment(self):
        cls = next(node for node in self.tree.body
                   if isinstance(node, ast.ClassDef) and node.name == "PluginFastMCP")
        fn = next(node for node in cls.body
                  if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_tools")
        names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        self.assertIn("tools", names)
        filtered = [node for node in ast.walk(fn)
                    if isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "tools" for t in node.targets)
                    and isinstance(node.value, ast.ListComp)]
        self.assertTrue(filtered, "Public discovery must restrict legacy write tools")
        self.assertIn('tool.name == "brain_execute"', self.source)

    def test_legacy_write_tools_handoff_without_helper_execution(self):
        actions = {
            "deploy_registered_source": "DEPLOY_REGISTERED_SOURCE",
            "run_registered_application_workflow": "RUN_APPLICATION_WORKFLOW",
            "run_registered_database_workflow": "RUN_DATABASE_WORKFLOW",
            "run_registered_task": "RUN_REGISTERED_TASK",
        }
        for name, action in actions.items():
            fn = next(node for node in self.tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == name)
            body = ast.get_source_segment(self.source, fn)
            self.assertIn(f'_legacy_handoff("{action}")', body)
            self.assertNotIn("helper_call(", body)
        self.assertIn('"execution_performed": False', self.source)
        self.assertIn('"next_tool": "brain_execute"', self.source)

    def test_no_shell_execution_or_raw_execution_tool(self):
        self.assertNotIn("shell=True", self.source)
        names = {node.name for node in self.tree.body if isinstance(node, ast.FunctionDef)}
        self.assertFalse({"execute_shell", "execute_sql", "run_command", "run_arbitrary"} & names)

    def test_read_and_write_annotations_are_separate(self):
        for name, role in (("connector_health", "RO"), ("execution_status", "RO"),
                           ("run_registered_task", "WRITE"), ("brain_execute", "WRITE"),
                           ("deploy_registered_source", "WRITE")):
            fn = next(node for node in self.tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == name)
            decorations = [ast.get_source_segment(self.source, d) or "" for d in fn.decorator_list]
            self.assertTrue(any(f"annotations={role}" in d for d in decorations), name)

if __name__ == "__main__":
    unittest.main()
