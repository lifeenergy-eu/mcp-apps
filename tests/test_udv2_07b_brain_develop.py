#!/usr/bin/env python3
"""UDV2-07B source-validation regression without a live MCP or secrets."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "apps/project-brain-controlled-execution/server.py"


def load_handler():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    target = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "brain_develop")
    target.decorator_list = []
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        target], type_ignores=[])
    env = {"hashlib": hashlib, "json": json, "re": re,
           "_verified_github_direct_source": lambda repository, sha, changes: "PASS",
           "helper_call": lambda action, payload: {"status": "QUEUED", "request_handle": "fixture"}}
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), env)
    return env["brain_develop"]


class DevelopBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.call = staticmethod(load_handler())

    def request(self, path="tests/fixture.txt", operation="create"):
        return self.call(repository="lifeenergy-eu/mcp-apps", intent="bounded regression",
                         changes=[{"path": path, "operation": operation, "content": "safe"}])

    def test_valid_request_stable_identity(self):
        a = self.request()
        b = self.request()
        self.assertEqual(a["status"], "HANDOFF_REQUIRED")
        self.assertEqual(a["request_id"], b["request_id"])
        self.assertFalse(a["production_accepted"])
        self.assertFalse(a["execution_performed"])

    def test_path_denials(self):
        for path in ("/abs", "../escape", "a/../b", "a//b", "a/./b",
                     "a\\b", "a/\\b", ""):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["failure_code"],
                                 "DEV_CHANGE_BOUNDARY_INVALID")

    def test_wrong_operation(self):
        self.assertEqual(self.request(operation="delete")["failure_code"],
                         "DEV_CHANGE_INVALID")

    def test_resume_requires_exact_request_identity(self):
        changes = [{"path": "tests/fixture.txt", "operation": "create", "content": "safe"}]
        req = self.call(repository="lifeenergy-eu/mcp-apps", intent="bounded regression", changes=changes)
        sha = "a" * 40
        resume = self.call(repository="lifeenergy-eu/mcp-apps", intent="bounded regression",
                           changes=changes, existing_sha=sha,
                           checkpoint={"request_id": req["request_id"], "github_commit_sha": sha})
        self.assertEqual(resume["code"], "DEV_HMAC_V2_RUN_CORE_SUBMITTED")
        self.assertTrue(resume["git_source_verified"])
        self.assertFalse(resume["production_accepted"])
        invalid = self.call(repository="lifeenergy-eu/mcp-apps", intent="bounded regression",
                            changes=changes, existing_sha=sha,
                            checkpoint={"request_id": "bad", "github_commit_sha": sha})
        self.assertEqual(invalid["failure_code"], "DEV_RESUME_REQUEST_MISMATCH")
        wrong_sha = self.call(repository="lifeenergy-eu/mcp-apps", intent="bounded regression",
                              changes=changes, existing_sha=sha,
                              checkpoint={"request_id": req["request_id"], "github_commit_sha": "b" * 40})
        self.assertEqual(wrong_sha["failure_code"], "DEV_RESUME_SHA_MISMATCH")

    def test_unsigned_sha_format_rejected(self):
        result = self.call(repository="lifeenergy-eu/mcp-apps",
                           intent="bad sha", existing_sha="bad")
        self.assertEqual(result["failure_code"], "DEV_SOURCE_SHA_INVALID")


if __name__ == "__main__":
    unittest.main()
