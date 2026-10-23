#!/usr/bin/env python3
"""Target-bound exact-SHA Server MCP release leaf.

This is a bounded physical executor for the EXISTING Brain Run Core. It has
no source-selection, scheduling, credential-broker or deployment authority.
Only a short-lived Ed25519 Run Core ticket can authorize one of the four
registered Server Management MCP unit/file bindings. It never touches apps,
databases, OAuth stores, business services or unrelated systemd units.
"""
from __future__ import annotations

import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PROFILE = "BRAIN_UNIFIED_SERVER_MCP_EXACT_SHA_RELEASE_V1"
SOURCE = "lifeenergy-eu/mcp-apps"
KEYDIR = Path("/etc/project-brain/server-mcp")
ISSUER = KEYDIR / "run-core-issuer-public.pem"
HOST_SIGNER = KEYDIR / "receipt-signing-private.pem"
PROFILE_TARGET = KEYDIR / "profile.json"
STATE = Path("/var/lib/project-brain/server-mcp-release")
FILES = {"server.py":"server", "root_helper.py":"helper",
         "admin_executor.py":"executor"}
SHA40 = re.compile(r"^[a-f0-9]{40}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^PB-UMCP-[A-Z0-9_-]{8,64}$")
TARGETS = {
    "SERVER-SSD-NODES-BRAIN": {
        "hostname":"brain-ssd-fra01", "service":"ssd-server-mcp.service",
        "server":"/opt/ssd-server-mcp/app/server.py",
        "helper":"/opt/ssd-server-mcp/root_helper.py",
        "executor":"/opt/ssd-server-mcp/admin_executor.py",
        "profile":"server-ssd-nodes-brain.json","port":18795
    },
    "SERVER-NETCUP-MAGENTO": {
        "hostname":"magento-prod", "service":"netcup-magento-mcp.service",
        "server":"/opt/netcup-magento-mcp/server.py",
        "helper":"/opt/netcup-magento-mcp/root_helper.py",
        "executor":"/opt/netcup-magento-mcp/admin_executor.py",
        "profile":"server-netcup-magento.json","port":18793
    },
    "SERVER-NETCUP-WORDPRESS": {
        "hostname":"wordpress-prod", "service":"netcup-migration-mcp.service",
        "server":"/opt/netcup-migration-mcp/server.py",
        "helper":"/opt/netcup-migration-mcp/root_helper.py",
        "executor":"/opt/netcup-migration-mcp/admin_executor.py",
        "profile":"server-netcup-wordpress.json","port":18793
    },
    "SERVER-P620-WSL": {
        "hostname":"DESKTOP-133GO83", "service":"project-brain-p620-mcp.service",
        "server":"/opt/p620-server-mcp/app/server.py",
        "helper":"/opt/p620-server-mcp/root_helper.py",
        "executor":"/opt/p620-server-mcp/admin_executor.py",
        "profile":"server-p620-wsl.json","port":8792
    }
}

class ReleaseDenied(ValueError):
    def __init__(self,code): super().__init__(code);self.code=code

def require(value,code):
    if not value: raise ReleaseDenied(code)

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def trusted(path, mode=0o022):
    require(path.is_file() and not path.is_symlink(),"UNIFIED_TRUST_FILE_MISSING")
    st=path.stat()
    require(st.st_uid==0 and not st.st_mode & mode,"UNIFIED_TRUST_OWNERSHIP_INVALID")
    return path

def parse_utc(value):
    require(isinstance(value,str) and value.endswith("Z"),"UNIFIED_TICKET_TIME_INVALID")
    try: return dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError: raise ReleaseDenied("UNIFIED_TICKET_TIME_INVALID") from None

def openssl_check(payload,signature,public):
    with tempfile.TemporaryDirectory(prefix="pb-unified-mcp-verify-") as root:
        directory=Path(root); message=directory/"message"; signed=directory/"signature"
        message.write_bytes(payload);signed.write_bytes(signature)
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-verify","-pubin",
                          "-inkey",str(public),"-rawin","-in",str(message),
                          "-sigfile",str(signed)],capture_output=True,timeout=12,check=False)
        return p.returncode==0

def openssl_sign(payload,private):
    with tempfile.TemporaryDirectory(prefix="pb-unified-mcp-sign-") as root:
        directory=Path(root); message=directory/"message"; signed=directory/"signature"
        message.write_bytes(payload)
        p=subprocess.run(["/usr/bin/openssl","pkeyutl","-sign","-inkey",
                          str(private),"-rawin","-in",str(message),"-out",
                          str(signed)],capture_output=True,timeout=12,check=False)
        require(p.returncode==0,"UNIFIED_HOST_SIGNING_FAILED")
        sig=signed.read_bytes()
        require(len(sig)==64,"UNIFIED_HOST_SIGNATURE_INVALID")
        return base64.b64encode(sig).decode("ascii")

def verify_ticket(ticket,public,now=None):
    require(isinstance(ticket,dict),"UNIFIED_TICKET_TYPE_INVALID")
    names={"schema_version","profile","ticket_id","target_id","repository",
           "source_sha","action","issued_at","expires_at","nonce",
           "payload_digests","signature"}
    require(set(ticket)==names and ticket["schema_version"]=="1.0"
            and ticket["profile"]==PROFILE,"UNIFIED_TICKET_SCHEMA_INVALID")
    require(ticket["target_id"] in TARGETS and ticket["repository"]==SOURCE
            and ticket["action"] in ("install_v1","readback_v1"),
            "UNIFIED_TICKET_TARGET_INVALID")
    require(isinstance(ticket["ticket_id"],str) and ID.fullmatch(ticket["ticket_id"])
            and isinstance(ticket["source_sha"],str) and SHA40.fullmatch(ticket["source_sha"])
            and isinstance(ticket["nonce"],str) and HEX64.fullmatch(ticket["nonce"]),
            "UNIFIED_TICKET_IDENTITY_INVALID")
    expected={"server.py","root_helper.py","admin_executor.py",
              TARGETS[ticket["target_id"]]["profile"]}
    hashes=ticket["payload_digests"]
    require(isinstance(hashes,dict) and set(hashes)==expected
            and all(isinstance(x,str) and HEX64.fullmatch(x) for x in hashes.values()),
            "UNIFIED_TICKET_PAYLOAD_INVALID")
    issued=parse_utc(ticket["issued_at"]); expires=parse_utc(ticket["expires_at"])
    now=now or dt.datetime.now(dt.timezone.utc)
    require(dt.timedelta(0)<expires-issued<=dt.timedelta(minutes=20)
            and issued<=now+dt.timedelta(seconds=60) and expires>now,
            "UNIFIED_TICKET_EXPIRED")
    try:
        signature=base64.b64decode(ticket["signature"],validate=True)
    except (ValueError,TypeError):
        raise ReleaseDenied("UNIFIED_TICKET_SIGNATURE_INVALID") from None
    require(len(signature)==64 and openssl_check(
        canonical({k:v for k,v in ticket.items() if k!="signature"}),
        signature,public),"UNIFIED_TICKET_SIGNATURE_REJECTED")
    return TARGETS[ticket["target_id"]]

def service_active(service):
    p=subprocess.run(["/usr/bin/systemctl","is-active",service],
                     capture_output=True,timeout=12,check=False)
    return p.returncode==0 and p.stdout.strip()==b"active"

def oauth_negative(port):
    req=urllib.request.Request("http://127.0.0.1:"+str(port)+"/mcp")
    try:
        with urllib.request.urlopen(req,timeout=3) as response:
            return response.status==401
    except urllib.error.HTTPError as exc:
        return exc.code==401
    except (OSError,ValueError):
        return False

def await_health(binding,timeout=22):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if service_active(binding["service"]) and oauth_negative(binding["port"]):
            return True
        time.sleep(0.5)
    return False

def atomic_write(path,data,mode):
    parent=path.parent
    require(parent.is_dir() and not parent.is_symlink(),"UNIFIED_DESTINATION_PARENT_INVALID")
    fd,tmp=tempfile.mkstemp(prefix=".pb-unified-mcp-",dir=parent)
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),mode)
            f.write(data);f.flush();os.fsync(f.fileno())
        os.chown(tmp,0,0)
        os.replace(tmp,path)
    finally:
        if os.path.lexists(tmp): os.unlink(tmp)

def signed_receipt(obj):
    trusted(HOST_SIGNER,0o077)
    obj=dict(obj)
    obj["signature"]=openssl_sign(canonical(obj),HOST_SIGNER)
    return obj

def source_files(ticket,source):
    require(source.is_dir() and not source.is_symlink(),"UNIFIED_SOURCE_DIR_INVALID")
    binding=TARGETS[ticket["target_id"]]
    names=list(FILES)+[binding["profile"]]
    selected={}
    for name in names:
        path=source/name if name in FILES else source/"profiles"/name
        require(path.is_file() and not path.is_symlink()
                and path.stat().st_size<140000 and
                digest(path)==ticket["payload_digests"][name],
                "UNIFIED_CANDIDATE_DIGEST_MISMATCH")
        selected[name]=path.read_bytes()
    profile=json.loads(selected[binding["profile"]])
    require(profile["target_id"]==ticket["target_id"]
            and profile["root_helper"]==binding["helper"]
            and profile["bind_port"]==binding["port"],
            "UNIFIED_HOST_PROFILE_MISMATCH")
    require(Path(profile["auth_packages"]).is_dir(),"UNIFIED_HOST_AUTH_PACKAGES_MISSING")
    return selected

def run(ticket,source):
    require(os.geteuid()==0,"UNIFIED_ROOT_REQUIRED")
    trusted(ISSUER)
    binding=verify_ticket(ticket,ISSUER)
    require(socket.gethostname()==binding["hostname"],"UNIFIED_HOST_IDENTITY_MISMATCH")
    require(service_active(binding["service"]),"UNIFIED_BASELINE_SERVICE_NOT_ACTIVE")
    state=STATE
    require(state.is_dir() and not state.is_symlink() and
            state.stat().st_uid==0 and not state.stat().st_mode&0o077,
            "UNIFIED_STATE_DIRECTORY_UNTRUSTED")
    with (state/"release.lock").open("a+") as mutex:
        fcntl.flock(mutex.fileno(),fcntl.LOCK_EX)
        receipt_path=state/(ticket["ticket_id"]+".json")
        require(not receipt_path.is_symlink(),"UNIFIED_RECEIPT_PATH_UNSAFE")
        require(not receipt_path.exists(),"UNIFIED_TICKET_REPLAY_REJECTED")
        destinations={name:Path(binding[tag]) for name,tag in FILES.items()}
        destinations[binding["profile"]]=PROFILE_TARGET
        observed_before={}
        for name,p in destinations.items():
            if p.exists():
                require(p.is_file() and not p.is_symlink(),"UNIFIED_DESTINATION_UNTRUSTED")
                observed_before[name]=digest(p)
            elif name!=binding["profile"]:
                raise ReleaseDenied("UNIFIED_BASELINE_FILE_MISSING")
        if ticket["action"]=="readback_v1":
            for name,p in destinations.items():
                require(p.is_file() and not p.is_symlink()
                        and digest(p)==ticket["payload_digests"][name],
                        "UNIFIED_READBACK_SHA_MISMATCH")
            require(oauth_negative(binding["port"]),"UNIFIED_READBACK_OAUTH_FAILED")
            body={"status":"PASS","target_id":ticket["target_id"],"source_sha":ticket["source_sha"],
                  "ticket_id":ticket["ticket_id"],"action":"readback_v1",
                  "observed_hashes":observed_before,"service_active":True,
                  "oauth_negative":True,"independent_readback":True}
            receipt=signed_receipt(body)
            atomic_write(receipt_path,canonical(receipt),0o600)
            return receipt
        selected=source_files(ticket,source)
        backup=state/ticket["ticket_id"]
        backup.mkdir(mode=0o700)
        require(backup.stat().st_uid==0,"UNIFIED_BACKUP_OWNERSHIP_INVALID")
        for name,p in destinations.items():
            if p.exists():
                shutil.copy2(p,backup/name)
        try:
            for name,p in destinations.items():
                data=selected[name]
                mode=0o755 if name=="root_helper.py" else 0o644
                atomic_write(p,data,mode)
            p=subprocess.run(["/usr/bin/systemctl","restart",binding["service"]],
                             capture_output=True,timeout=35,check=False)
            require(p.returncode==0 and await_health(binding),
                    "UNIFIED_NEW_SERVICE_HEALTH_FAILED")
            after={name:digest(path) for name,path in destinations.items()}
            require(all(after[k]==ticket["payload_digests"][k] for k in after),
                    "UNIFIED_AFTER_SHA_MISMATCH")
            body={"status":"PASS","target_id":ticket["target_id"],"source_sha":ticket["source_sha"],
                  "ticket_id":ticket["ticket_id"],"action":"install_v1",
                  "observed_hashes":after,"previous_hashes":observed_before,
                  "service_active":True,"oauth_negative":True,
                  "production_application_mutation":False,
                  "production_database_mutation":False,
                  "rollback_backup":str(backup)}
            receipt=signed_receipt(body)
            atomic_write(receipt_path,canonical(receipt),0o600)
            return receipt
        except Exception:
            for name,p in destinations.items():
                saved=backup/name
                if saved.exists():
                    original_mode=saved.stat().st_mode&0o777
                    atomic_write(p,saved.read_bytes(),original_mode)
                elif name==binding["profile"] and p.exists():
                    p.unlink()
            subprocess.run(["/usr/bin/systemctl","restart",binding["service"]],
                           capture_output=True,timeout=35,check=False)
            raise

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--ticket",required=True,type=Path)
    parser.add_argument("--source",required=True,type=Path)
    args=parser.parse_args()
    try:
        require(args.ticket.is_file() and not args.ticket.is_symlink()
                and args.ticket.stat().st_size<8192,"UNIFIED_TICKET_FILE_UNTRUSTED")
        ticket=json.loads(args.ticket.read_text(encoding="ascii"))
        result=run(ticket,args.source)
    except Exception as exc:
        code=exc.code if isinstance(exc,ReleaseDenied) else "UNIFIED_RELEASE_FAIL_CLOSED"
        result={"status":"FAIL_CLOSED","code":code,
                "production_application_mutation":False,
                "production_database_mutation":False}
    print(json.dumps(result,sort_keys=True))
    return 0 if result.get("status")=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
