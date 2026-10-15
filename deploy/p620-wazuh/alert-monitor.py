#!/usr/bin/env python3
"""P620 Wazuh alert notifier. Reuses existing P620 ForwardEmail transport.
No credentials or message bodies exposed in command output.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.request
ROOT=Path("/opt/p620-wazuh")
STATE=ROOT/"alerts-state.json"
LIB=Path("/home/p620/infrastructure/control-center/monitor.py")
CFG=Path("/home/p620/infrastructure/control-center/config.json")
def read_json(p,default):
    try:return json.loads(p.read_text())
    except (OSError,ValueError):return default
def write_json(p,value):
    temp=p.with_suffix(".new")
    temp.write_text(json.dumps(value,indent=2)+"\n")
    os.chmod(temp,0o600)
    temp.replace(p)
def email(subject,body):
    spec=importlib.util.spec_from_file_location("existing_p620_monitor",LIB)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg=json.loads(CFG.read_text())
    return mod.email(cfg,subject,body)
def high_severity():
    secrets=json.loads((ROOT/"secrets/credentials.json").read_text())
    ip=subprocess.check_output(
        ["docker","inspect","-f","{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}","runtime-wazuh.indexer-1"],
        text=True,timeout=10).strip()
    credential=base64.b64encode(("admin:"+secrets["admin"]).encode()).decode()
    query={"size":0,"query":{"bool":{"filter":[
        {"range":{"rule.level":{"gte":12}}},
        {"range":{"timestamp":{"gte":"now-15m"}}}
    ]}},"aggs":{"top_rules":{"terms":{"field":"rule.id","size":8}}}}
    request=urllib.request.Request(
        f"https://{ip}:9200/wazuh-alerts-*/_search",
        data=json.dumps(query).encode(),method="POST",
        headers={"Content-Type":"application/json","Authorization":"Basic "+credential})
    with urllib.request.urlopen(request,timeout=15,context=ssl._create_unverified_context()) as response:
        result=json.load(response)
    hits=result.get("hits",{}).get("total",{}).get("value",0)
    ids=[str(x.get("key")) for x in result.get("aggregations",{}).get("top_rules",{}).get("buckets",[])]
    return hits,ids
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--test-email",action="store_true")
    args=ap.parse_args()
    if args.test_email:
        r=email("[P620 WAZUH] TEST","P620 Wazuh alert delivery test. If you received this, inbox delivery is verified by you.")
        print("EMAIL_TEST_RESULT",r)
        return 0 if r.startswith("ACCEPTED_") else 2
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    state=read_json(STATE,{})
    issues=[]
    p=subprocess.run(["/usr/bin/python3",str(ROOT/"check-health.py")],capture_output=True,text=True,timeout=35)
    if p.returncode!=0:issues.append(p.stdout.strip()[:180] or "HEALTH_CHECK_FAILED")
    try:total,rules=high_severity()
    except Exception as e:
        total,rules=0,[]
        issues.append("INDEXER_ALERT_QUERY_FAILED:"+type(e).__name__)
    faulty=bool(issues)
    prior=bool(state.get("health_problem"))
    events=[]
    last=float(state.get("last_failure_email_unix",0))
    import time
    if faulty and (not prior or time.time()-last > 4*3600):
        status=email("[P620 WAZUH] HEALTH ALERT","Detected at "+now+"\n"+ "\n".join(issues))
        events.append("HEALTH:"+status)
        if status.startswith("ACCEPTED_"):state["last_failure_email_unix"]=time.time()
    elif not faulty and prior:
        status=email("[P620 WAZUH] RECOVERY","Wazuh health checks recovered at "+now)
        events.append("RECOVERY:"+status)
    state["health_problem"]=faulty
    # Send at most once per 1 hour while severe recent alerts continue.
    last_alert=float(state.get("last_security_email_unix",0))
    if total>0 and time.time()-last_alert >= 3600:
        status=email("[P620 WAZUH] HIGH SEVERITY ALERTS","Time: "+now+"\nSevere last 15min: "+str(total)+"\nRule IDs: "+", ".join(rules))
        events.append("SECURITY:"+status)
        if status.startswith("ACCEPTED_"):state["last_security_email_unix"]=time.time()
    state["checked_at_utc"]=now
    state["recent_severe_count"]=total
    state["health_issues"]=issues
    state["last_email_events"]=events
    write_json(STATE,state)
    print("WAZUH_ALERT_MONITOR", "FAIL" if faulty else "PASS","severe_last_15m",total,"email_events",events)
    return 2 if faulty else 0
if __name__=="__main__":
    sys.exit(main())
