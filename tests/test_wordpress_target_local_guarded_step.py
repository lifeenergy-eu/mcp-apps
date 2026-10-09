from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "adapters/cloudways-wordpress/target_local_guarded_step.py"
spec = importlib.util.spec_from_file_location("wordpress_target_local_guarded_step", FILE)
assert spec and spec.loader
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class WordPressTargetLocalGuardTests(unittest.TestCase):
    def setUp(self):
        self.probe = {"action": "capability_probe", "app_id": "wsbmznzrem"}

    def test_capability_probe_and_cache_dry_run_only(self):
        self.assertEqual(target.mutation_scope(self.probe), self.probe)
        cleanup = {"action": "filesystem_cleanup", "app_id": "wsbmznzrem",
                   "targets": ["cache", "debug_log"], "dry_run": True}
        self.assertEqual(target.mutation_scope(cleanup), cleanup)
        for bad in (
            {"action": "plugin_disable_remove", "app_id": "wsbmznzrem"},
            {"action": "filesystem_cleanup", "app_id": "wsbmznzrem",
             "targets": ["cache"], "dry_run": False},
            {"action": "filesystem_cleanup", "app_id": "wsbmznzrem",
             "targets": ["cache", "cache"], "dry_run": True},
            {"action": "filesystem_cleanup", "app_id": "wsbmznzrem",
             "targets": ["../"], "dry_run": True},
            {"action": "capability_probe", "app_id": "wsbmznzrem", "shell": "id"},
            {"action": "capability_probe", "app_id": "unregistered"},
        ):
            with self.subTest(bad=bad), self.assertRaises(target.TargetLocalDenied):
                target.mutation_scope(bad)

    def test_trust_and_source_required_before_any_runner(self):
        request = {"ticket_envelope": {"ticket": {"dependency_receipts": []}},
                   "mutation": self.probe}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(target.TargetLocalDenied, "TRUSTED_SOURCE_IDENTITY"):
                target.execute_preauthorized_step(request)
        with patch.dict(os.environ, {"PB_CONTROL_EXACT_SOURCE_SHA": "a" * 40}, clear=True):
            with self.assertRaisesRegex(target.TargetLocalDenied, "CUTOVER_NOT_AUTHORIZED"):
                target.execute_preauthorized_step(request)
        with patch.dict(os.environ, {"PB_CONTROL_EXACT_SOURCE_SHA": "a" * 40,
                                     "PB_WORDPRESS_TARGET_LOCAL_ENABLED": "1"}, clear=True):
            with self.assertRaisesRegex(target.TargetLocalDenied, "TRUST_FILE_UNAVAILABLE"):
                target.execute_preauthorized_step(request)

    def test_signed_ticket_dependency_must_be_empty_until_verifier_registered(self):
        request = {"ticket_envelope": {"ticket": {"dependency_receipts": ["STEP-EXTERNAL-1"]}},
                   "mutation": self.probe}
        with self.assertRaisesRegex(target.TargetLocalDenied, "DEPENDENCY_RECEIPTS_NOT_AVAILABLE"):
            target.execute_preauthorized_step(request)

    def test_nonce_is_durable_and_one_time(self):
        with tempfile.TemporaryDirectory() as home:
            dbdir = Path(home) / "state"
            dbdir.mkdir(mode=0o700)
            database = dbdir / "tickets.sqlite3"
            with patch.object(target, "NONCE_FILE", database):
                self.assertTrue(target.consume_once("nonce_fixture_0001", 2200, "RUN-00000001", "STEP-00000001"))
                self.assertFalse(target.consume_once("nonce_fixture_0001", 2200, "RUN-00000001", "STEP-00000001"))
                self.assertFalse(target.consume_once("nonce_fixture_0002", 2200, "RUN-00000001", "STEP-00000001"))
                self.assertEqual(database.stat().st_mode & 0o077, 0)

    def test_insecure_nonce_directory_denied(self):
        with tempfile.TemporaryDirectory() as home:
            dbdir = Path(home) / "state"
            dbdir.mkdir(mode=0o755)
            with patch.object(target, "NONCE_FILE", dbdir / "tickets.sqlite3"):
                with self.assertRaisesRegex(target.TargetLocalDenied, "NONCE_STORE_UNAVAILABLE"):
                    target.consume_once("nonce_fixture_0001", 2200, "RUN-00000001", "STEP-00000001")

    def test_unverified_signature_cannot_reach_runner(self):
        request = {"ticket_envelope": {"ticket": {"dependency_receipts": []}},
                   "mutation": self.probe}
        rejecting = types.SimpleNamespace(verify_ticket=lambda *a, **kw: {"status": "FAIL_CLOSED"})
        with (patch.dict(os.environ, {"PB_CONTROL_EXACT_SOURCE_SHA": "a" * 40,
                                    "PB_WORDPRESS_TARGET_LOCAL_ENABLED": "1"}, clear=True),
              patch.object(target, "private_file", return_value=b"A" * 32),
              patch.object(target, "load_verifier", return_value=rejecting),
              patch.object(target, "guarded_php_call") as runner):
            with self.assertRaisesRegex(target.TargetLocalDenied, "TICKET_VERIFICATION_DENIED"):
                target.execute_preauthorized_step(request)
            runner.assert_not_called()

    def test_runner_called_only_after_verified_ticket(self):
        ticket = {"dependency_receipts": [], "run_id": "RUN-00000001",
                  "step_id": "STEP-00000001"}
        request = {"ticket_envelope": {"ticket": ticket}, "mutation": self.probe}
        verified = types.SimpleNamespace(verify_ticket=lambda *a, **kw: {"status": "PASS"})
        outcome = {"status": "PASS", "action": "capability_probe", "app_id": "wsbmznzrem",
                   "write_verified": True, "cleanup_verified": True}
        with (patch.dict(os.environ, {"PB_CONTROL_EXACT_SOURCE_SHA": "a" * 40,
                                    "PB_WORDPRESS_TARGET_LOCAL_ENABLED": "1"}, clear=True),
              patch.object(target, "private_file", return_value=b"A" * 32),
              patch.object(target, "load_verifier", return_value=verified),
              patch.object(target, "guarded_php_call", return_value=outcome) as runner):
            result = target.execute_preauthorized_step(request)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["write_verified"])
            self.assertTrue(result["cleanup_verified"])
            runner.assert_called_once_with(self.probe)

    def test_request_cannot_choose_runner_or_ticket_key(self):
        request = {"ticket_envelope": {"ticket": {}}, "mutation": self.probe, "runner": "/bin/bash"}
        with self.assertRaisesRegex(target.TargetLocalDenied, "REQUEST_FIELDS_FORBIDDEN"):
            target.execute_preauthorized_step(request)


if __name__ == "__main__":
    unittest.main()
