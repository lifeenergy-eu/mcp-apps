#!/usr/bin/env python3
"""D5 production smoke: public development stays behind existing helper gate."""
import ast
import unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/'apps/project-brain-controlled-execution/server.py'
class D5BoundarySmoke(unittest.TestCase):
    def test_existing_mcp_delegation_is_gated(self):
        src=SOURCE.read_text(encoding='utf-8')
        tree=ast.parse(src)
        fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='brain_develop')
        body=ast.get_source_segment(src,fn)
        self.assertIn('PB_DEVELOPMENT_BACKEND_ENABLED',body)
        self.assertIn('PUBLIC_DEVELOPMENT',body)
        self.assertIn('guard_deployment_result',body)
if __name__=='__main__':unittest.main()
