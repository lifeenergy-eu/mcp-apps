#!/usr/bin/env python3
"""Isolated functional and negative tests of the signed four-host release leaf."""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

FILE=Path(__file__).resolve().parents[1]/"packages/universal_server_mcp/host_release.py"
spec=importlib.util.spec_from_file_location("pb_unified_host_release_test",FILE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SignedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory(prefix="pb-unified-host-test-")
        self.addCleanup(self.d.cleanup)
        self.root=Path(self.d.name)
        self.priv=self.root/"private.pem"
        self.pub=self.root/"public.pem"
        subprocess.run(["openssl","genpkey","-algorithm","Ed25519","-out",str(self.priv)],check=True,capture_output=True)
        subprocess.run(["openssl","pkey","-in",str(self.priv),"-pubout","-out",str(self.pub)],check=True,capture_output=True)
        self.source=self.root/"source";self.source.mkdir()
        (self.source/"profiles").mkdir()
        self.auth=self.root/"auth";self.auth.mkdir()
        self.binding={
            "hostname":"unit-test-host","service":"test-mcp.service",
            "server":str(self.root/"active"/"server.py"),
            "helper":str(self.root/"active"/"root_helper.py"),
            "executor":str(self.root/"active"/"admin_executor.py"),
            "profile":"server-ssd-nodes-brain.json","port":18795}
        (self.root/"active").mkdir()
        for name in mod.FILES:
            (self.source/name).write_text("NEW_SOURCE_"+name+"\n")
            (self.root/"active"/name).write_text("OLD_SOURCE_"+name+"\n")
        self.profile={
            "target_id":"SERVER-SSD-NODES-BRAIN","display_name":"Testing Server MCP",
            "root_helper":self.binding["helper"],"auth_packages":str(self.auth),
            "bind_port":18795}
        (self.source/"profiles"/self.binding["profile"]).write_text(json.dumps(self.profile))
        files={name:self.source/name for name in mod.FILES}
        files[self.binding["profile"]]=self.source/"profiles"/self.binding["profile"]
        self.digests={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in files.items()}
        self.state=self.root/"state";self.state.mkdir(mode=0o700)
        self.profile_target=self.root/"active-profile.json"
    def ticket(self,action="install_v1"):
        now=dt.datetime.now(dt.timezone.utc)
        ticket={
            "schema_version":"1.0","profile":mod.PROFILE,"ticket_id":"PB-UMCP-TEST"+os.urandom(8).hex().upper(),
            "target_id":"SERVER-SSD-NODES-BRAIN","repository":mod.SOURCE,
            "source_sha":"9cc401eb0301843059845d1b9b3e1b9272215c82",
            "action":action,
            "issued_at":(now-dt.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at":(now+dt.timedelta(minutes=8)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nonce":os.urandom(32).hex(),
            "payload_digests":self.digests,
        }
        ticket["signature"]=mod.openssl_sign(mod.canonical(ticket),self.priv)
        return ticket
    def test_signed_ticket_accepts_exact_target(self):
        self.assertEqual(mod.verify_ticket(self.ticket(),self.pub),mod.TARGETS["SERVER-SSD-NODES-BRAIN"])
    def test_tampered_signed_ticket_rejected(self):
        ticket=self.ticket();ticket["source_sha"]="0"*40
        with self.assertRaises(mod.ReleaseDenied):
            mod.verify_ticket(ticket,self.pub)
    def test_expired_ticket_rejected(self):
        ticket=self.ticket();ticket["expires_at"]="2020-01-01T00:00:00Z"
        with self.assertRaises(mod.ReleaseDenied):
            mod.verify_ticket(ticket,self.pub)
    def test_unknown_target_rejected(self):
        ticket=self.ticket();ticket["target_id"]="SERVER-OTHER"
        with self.assertRaises(mod.ReleaseDenied):
            mod.verify_ticket(ticket,self.pub)
    def test_payload_digest_mismatch_rejected(self):
        ticket=self.ticket()
        (self.source/"server.py").write_text("CHANGED!")
        with patch.dict(mod.TARGETS,{"SERVER-SSD-NODES-BRAIN":self.binding}):
            with self.assertRaises(mod.ReleaseDenied):
                mod.source_files(ticket,self.source)
    def test_valid_payload_with_trusted_host_profile(self):
        ticket=self.ticket()
        with patch.dict(mod.TARGETS,{"SERVER-SSD-NODES-BRAIN":self.binding}):
            self.assertEqual(len(mod.source_files(ticket,self.source)),4)
    @unittest.skipUnless(os.geteuid()==0,"root-only physical release integration")
    def test_signed_install_and_independent_readback_without_live_services(self):
        ticket=self.ticket()
        readback=self.ticket("readback_v1")
        original_run=subprocess.run
        def intercept(argv,*args,**kwargs):
            if argv[:2]==["/usr/bin/systemctl","restart"]:
                return subprocess.CompletedProcess(argv,0,b"",b"")
            return original_run(argv,*args,**kwargs)
        with patch.dict(mod.TARGETS,{"SERVER-SSD-NODES-BRAIN":self.binding}),\
             patch.object(mod,"ISSUER",self.pub),\
             patch.object(mod,"HOST_SIGNER",self.priv),\
             patch.object(mod,"PROFILE_TARGET",self.profile_target),\
             patch.object(mod,"STATE",self.state),\
             patch.object(mod,"trusted",side_effect=lambda x,*args:x),\
             patch.object(mod.socket,"gethostname",return_value="unit-test-host"),\
             patch.object(mod,"service_active",return_value=True),\
             patch.object(mod,"oauth_negative",return_value=True),\
             patch.object(mod,"await_health",return_value=True),\
             patch.object(mod.subprocess,"run",side_effect=intercept):
            receipt=mod.run(ticket,self.source)
            self.assertEqual(receipt["status"],"PASS")
            self.assertEqual(receipt["action"],"install_v1")
            self.assertEqual((self.root/"active"/"server.py").read_text(),"NEW_SOURCE_server.py\n")
            self.assertTrue(self.profile_target.is_file())
            with self.assertRaises(mod.ReleaseDenied):
                mod.run(ticket,self.source)
            check=mod.run(readback,self.source)
            self.assertTrue(check["independent_readback"])
            self.assertEqual(check["observed_hashes"]["server.py"],self.digests["server.py"])
            decoded=base64.b64decode(check["signature"],validate=True)
            self.assertTrue(mod.openssl_check(mod.canonical({k:v for k,v in check.items() if k!="signature"}),decoded,self.pub))

if __name__=="__main__":
    unittest.main()
