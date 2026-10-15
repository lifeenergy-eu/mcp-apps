#!/usr/bin/env python3
"""P620 Wazuh Telegram alert transport, root-only credentials."""
import json,os,re,urllib.request,urllib.error
from pathlib import Path
CFG=Path("/opt/p620-wazuh/secrets/telegram.json")
def status():
    if not CFG.is_file(): return "NOT_CONFIGURED"
    if CFG.stat().st_mode & 0o077: return "UNSAFE_PERMISSIONS"
    try:
        c=json.loads(CFG.read_text())
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}",str(c.get("bot_token",""))): return "INVALID_BOT_TOKEN"
        if not re.fullmatch(r"-?[0-9]+",str(c.get("chat_id",""))): return "INVALID_CHAT_ID"
        return "READY"
    except (OSError,ValueError):return "INVALID_CONFIG"
def send(kind,body):
    st=status()
    if st!="READY":return st
    c=json.loads(CFG.read_text())
    payload=json.dumps({"chat_id":str(c["chat_id"]),"text":("[P620 WAZUH] "+kind+"\n"+body)[:3900],"disable_web_page_preview":True}).encode()
    url="https://api.telegram.org/bot"+c["bot_token"]+"/sendMessage"
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=payload,headers={"Content-Type":"application/json"},method="POST"),timeout=18) as r:
            j=json.load(r)
            return "ACCEPTED_200" if j.get("ok") else "UNCONFIRMED"
    except urllib.error.HTTPError as e:return "HTTP_"+str(e.code)
    except Exception as e:return "ERROR_"+type(e).__name__
if __name__=="__main__":
    print("TELEGRAM_STATUS",status())
