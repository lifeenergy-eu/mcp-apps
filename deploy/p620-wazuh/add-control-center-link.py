#!/usr/bin/env python3
"""Idempotently add Wazuh link to P620 Infrastructure Control Center UI."""
from pathlib import Path
import os, shutil, datetime, subprocess
path=Path("/home/p620/infrastructure/control-center/dashboard.py")
data=path.read_text()
if "'wazuh':'https://p620.taila88a6c.ts.net:10000/'" in data:
    print("WAZUH_LINK_ALREADY_PRESENT")
else:
    needle="'restic_browser':"
    if data.count(needle)!=1: raise SystemExit("EXPECTED_RESTIC_REFERENCE_MISSING_OR_AMBIGUOUS")
    new="'wazuh':'https://p620.taila88a6c.ts.net:10000/',"+needle
    updated=data.replace(needle,new,1)
    if "No second orchestrator." in updated:
        updated=updated.replace("Read-only portal: Beszel, Cockpit, Windows Restic Browser.","Read-only portal: Beszel, Cockpit, Wazuh, Windows Restic Browser.")
    tmp=path.with_suffix(".wazuh.tmp")
    tmp.write_text(updated)
    st=path.stat()
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, st.st_mode & 0o777)
    compile(updated,str(path),"exec")
    backup=path.with_suffix(".py.pre-wazuh-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(path,backup)
    os.replace(tmp,path)
    print("WAZUH_LINK_APPLIED_BACKUP",str(backup))
