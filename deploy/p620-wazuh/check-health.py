#!/usr/bin/env python3
"""P620 Wazuh health check: stdout/journal only. No secrets output."""
import json,subprocess,sys,urllib.request,urllib.error,ssl,base64
from pathlib import Path
ROOT=Path("/opt/p620-wazuh")
def cmd(args):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=25)
def main():
    issues=[]
    d=cmd(["docker","ps","--format","{{.Names}}"])
    running=set(d.stdout.splitlines()) if d.returncode==0 else set()
    for name in ("runtime-wazuh.manager-1","runtime-wazuh.indexer-1","runtime-wazuh.dashboard-1"):
        if name not in running: issues.append("NOT_RUNNING:"+name)
    try:
        req=urllib.request.Request("https://127.0.0.1:8443/")
        with urllib.request.urlopen(req,context=ssl._create_unverified_context(),timeout=8) as r: pass
    except urllib.error.HTTPError as e:
        if e.code not in (302,401,403): issues.append("DASHBOARD_HTTP_"+str(e.code))
    except Exception: issues.append("DASHBOARD_UNREACHABLE")
    a=cmd(["docker","exec","runtime-wazuh.manager-1","/var/ossec/bin/agent_control","-l"])
    if a.returncode!=0 or "netcup-wordpress-vienna" not in a.stdout or not any("netcup-wordpress-vienna" in line and "Active" in line for line in a.stdout.splitlines()):
        issues.append("NETCUP_AGENT_NOT_ACTIVE")
    print("WAZUH_HEALTH", "PASS" if not issues else "FAIL",*issues)
    return 0 if not issues else 2
if __name__=="__main__":sys.exit(main())
