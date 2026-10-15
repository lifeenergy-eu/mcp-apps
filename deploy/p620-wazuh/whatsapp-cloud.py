#!/usr/bin/env python3
"""Wazuh WhatsApp Cloud API sender. Approved utility template only; fail closed."""
import argparse,json,os,re,sys,urllib.request,urllib.error
from pathlib import Path
CFG=Path("/opt/p620-wazuh/secrets/whatsapp-cloud.json")
def status():
    if not CFG.is_file():return "NOT_CONFIGURED"
    try:
        a=json.loads(CFG.read_text())
        if CFG.stat().st_mode & 0o077:return "UNSAFE_FILE_PERMISSIONS"
        for x in ("access_token","phone_number_id","recipient","template_name","template_language","graph_version"):
            if not isinstance(a.get(x),str) or not a[x].strip():return "INCOMPLETE_"+x.upper()
        if not re.fullmatch(r"v\d+\.\d+",a["graph_version"]):return "INVALID_GRAPH_VERSION"
        if not re.fullmatch(r"\d{7,15}",a["recipient"]):return "INVALID_RECIPIENT"
        return "READY"
    except (ValueError,OSError):return "INVALID_CONFIG"
def send(kind,message):
    st=status()
    if st!="READY":return st
    c=json.loads(CFG.read_text())
    # Approved Meta template must have two BODY parameters: incident category and short detail.
    payload={"messaging_product":"whatsapp","to":c["recipient"],"type":"template","template":{
      "name":c["template_name"],"language":{"code":c["template_language"]},
      "components":[{"type":"body","parameters":[
        {"type":"text","text":kind[:70]},
        {"type":"text","text":message[:550]}
      ]}]}}
    uri="https://graph.facebook.com/"+c["graph_version"]+"/"+c["phone_number_id"]+"/messages"
    req=urllib.request.Request(uri,data=json.dumps(payload).encode(),headers={
      "Authorization":"Bearer "+c["access_token"],"Content-Type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=18) as r:
            v=json.load(r)
            return "ACCEPTED_"+str(r.status) if v.get("messages") else "UNCONFIRMED_RESPONSE"
    except urllib.error.HTTPError as e:return "HTTP_"+str(e.code)
    except Exception as e:return "ERROR_"+type(e).__name__
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--status",action="store_true")
    p.add_argument("--test",action="store_true")
    a=p.parse_args()
    if a.test:print("WHATSAPP_TEST",send("Test","P620 Wazuh test security alert"))
    else:print("WHATSAPP_STATUS",status())
