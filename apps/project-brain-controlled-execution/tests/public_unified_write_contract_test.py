#!/usr/bin/env python3
"""Public MCP surface remains narrow and deployment-compatible."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "server.py"


class PublicUnifiedWriteContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(SOURCE))
        cls.defs = {n.name: n for n in cls.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_four_public_tools(self):
        self.assertIn('{"brain_execute", "brain_source_mutate", "brain_operation_status", "brain_develop"}', self.source)

    def test_existing_deploy_signature_unmodified(self):
        self.assertEqual([a.arg for a in self.defs["brain_execute"].args.args], ["repository", "commit_sha"])

    def test_source_mutation_has_no_raw_runner_or_secret_fields(self):
        self.assertEqual([a.arg for a in self.defs["brain_source_mutate"].args.args],
            ["repository","base_sha","commit_message","idempotency_key","operations"])
        self.assertIn('"PUBLIC_SOURCE_MUTATION"', self.source)

    def test_status_read_only(self):
        self.assertEqual([a.arg for a in self.defs["brain_operation_status"].args.args], ["operation_id"])
        self.assertIn('helper_call("PUBLIC_OPERATION_STATUS"', self.source)

    def test_fixed_helper_transport(self):
        self.assertIn('shell=False', self.source)
        self.assertIn('timeout=30', self.source)


if __name__ == "__main__":
    unittest.main()
