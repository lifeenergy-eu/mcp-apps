#!/usr/bin/env python3
"""D5 contract tests for the sole Brain development MCP facade.

Offline AST isolation avoids importing live OAuth/transport or invoking real
GitHub, attestation, Run Core or customer targets.
"""
from __future__ import annotations
import ast
import os
import pathlib
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "server.py"

def isolated_entrypoint(callback):
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [n for n in source.body if isinstance(n, ast.FunctionDef)
                 and n.name == "brain_develop"]
    assert len(functions) == 1
    node = functions[0]
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    scope = {
        "os": os,
        "helper_call": callback,
        "guard_deployment_result": lambda value: value,
        "Any": object,
    }
    exec(compile(module, str(SOURCE), "exec"), scope)
    return scope["brain_develop"]

class DevelopmentBridgeEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.facade = isolated_entrypoint(
            lambda action, payload: self.calls.append((action,payload)) or
            {"status": "PENDING", "operation_id": "A"*64,
             "production_accepted": False}
        )

    @patch.dict(os.environ, {"PB_DEVELOPMENT_BACKEND_ENABLED":"1"})
    def test_existing_exact_sha_delegates_only_registered_helper(self):
        sha = "a"*40
        result = self.facade("lifeenergy-eu/project-brain", "Verify",
                             existing_sha=sha)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(self.calls, [("PUBLIC_DEVELOPMENT", {
            "schema_version": "1.0",
            "repository": "lifeenergy-eu/project-brain",
            "intent": "Verify", "existing_sha": sha,
        })])

    @patch.dict(os.environ, {"PB_DEVELOPMENT_BACKEND_ENABLED":"1"})
    def test_changes_delegate_exact_payload(self):
        changes=[{"path":"control-plane/tests/example.txt",
                  "operation":"create","content":"fixture"}]
        self.facade("lifeenergy-eu/project-brain", "Test", changes=changes)
        self.assertEqual(self.calls[0][0], "PUBLIC_DEVELOPMENT")
        self.assertEqual(self.calls[0][1]["changes"],changes)

    @patch.dict(os.environ, {"PB_DEVELOPMENT_BACKEND_ENABLED":"1"})
    def test_checkpoint_cannot_be_client_selected(self):
        row=self.facade("lifeenergy-eu/project-brain", "Test",
                        existing_sha="b"*40,checkpoint={"request_id":"x"})
        self.assertEqual(row["status"],"FAIL_CLOSED")
        self.assertEqual(row["failure_code"],"DEV_COORDINATOR_CHECKPOINT_IS_SERVER_OWNED")
        self.assertEqual(self.calls,[])

    @patch.dict(os.environ, {"PB_DEVELOPMENT_BACKEND_ENABLED":"1"})
    def test_source_modes_fail_closed(self):
        self.assertEqual(self.facade("x/y","Test")["status"],"FAIL_CLOSED")
        self.assertEqual(self.facade("x/y","Test",changes=[],
                        existing_sha="c"*40)["status"],"FAIL_CLOSED")
        self.assertEqual(self.calls,[])

    @patch.dict(os.environ, {"PB_DEVELOPMENT_BACKEND_ENABLED":"1"})
    def test_no_fabricated_production_pass(self):
        row=self.facade("lifeenergy-eu/mcp-apps","test",
                        existing_sha="d"*40)
        self.assertFalse(row["production_accepted"])

if __name__ == "__main__":
    unittest.main()
