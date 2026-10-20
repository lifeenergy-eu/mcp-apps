#!/usr/bin/env python3
"""D5: public deploy accepts source identity, never target or runner input."""
import ast
import unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/"apps/project-brain-controlled-execution/server.py"
class D5SourceIdentity(unittest.TestCase):
    def test_public_deploy_parameter_boundary(self):
        tree=ast.parse(SOURCE.read_text(encoding="utf-8"))
        method=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="brain_execute")
        params=[item.arg for item in method.args.args]
        self.assertEqual(params,["repository","commit_sha"])
    def test_development_delegates_to_original_helper(self):
        source=SOURCE.read_text(encoding="utf-8")
        self.assertIn('helper_call("PUBLIC_DEVELOPMENT", payload)',source)
        self.assertIn("PB_DEVELOPMENT_BACKEND_ENABLED",source)
if __name__=="__main__":
    unittest.main()
