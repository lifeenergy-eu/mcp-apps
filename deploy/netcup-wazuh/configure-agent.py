#!/usr/bin/env python3
"""Configure operational Wazuh agent log and targeted WordPress FIM sources on Netcup.
Idempotent. Preserves original Wazuh configuration with a root-only timestamped backup.
This runtime operation is independent of Brain execution or deploy.
"""
from __future__ import annotations
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

FILE = Path("/var/ossec/etc/ossec.conf")
PHP_LOG = Path("/var/log/php8.3-fpm.log")
SITE_ROOT = Path("/srv/wordpress/sites")
FIM_START = "<!-- P620-WAZUH-NETCUP-FIM-START -->"
FIM_END = "<!-- P620-WAZUH-NETCUP-FIM-END -->"
LOG_START = "<!-- P620-WAZUH-NETCUP-PHP-START -->"
LOG_END = "<!-- P620-WAZUH-NETCUP-PHP-END -->"

def main():
    if os.geteuid() != 0: raise SystemExit("ROOT_REQUIRED")
    cfg = FILE.read_text(encoding="utf-8")
    files = sorted(x for x in SITE_ROOT.glob("*/public_html/wp-config.php") if x.is_file())
    if not files: raise SystemExit("NO_WORDPRESS_CONFIG_FILES_FOUND")
    fim = "\n  " + FIM_START + "\n" + "".join(
        f'  <directories check_all="yes" realtime="yes" report_changes="no">{p}</directories>\n'
        for p in files
    ) + "  " + FIM_END + "\n"
    logfile = (
        "\n  " + LOG_START + "\n"
        '  <localfile>\n    <log_format>syslog</log_format>\n'
        f'    <location>{PHP_LOG}</location>\n  </localfile>\n'
        "  " + LOG_END + "\n"
    )
    if FIM_START not in cfg:
        cfg, count = re.subn(r"(?m)^  </syscheck>", lambda m: fim + m.group(0), cfg, count=1)
        if count != 1: raise SystemExit("FIM_INSERTION_POINT_MISSING")
    if PHP_LOG.is_file() and LOG_START not in cfg:
        cfg, count = re.subn(r"(?m)^</ossec_config>\s*$", lambda m: logfile + m.group(0), cfg, count=1)
        if count != 1: raise SystemExit("LOG_INSERTION_POINT_MISSING")
    # Wazuh supports multiple top-level <ossec_config> blocks; wrap for XML validation.\n    ET.fromstring("<wazuh-config-root>" + cfg + "</wazuh-config-root>")
    before = FILE.read_text(encoding="utf-8")
    if before == cfg:
        print("ALREADY_CONFIGURED; WP_CONFIG_FIM_FILES",len(files))
        return
    out = Path("/var/backups") / ("wazuh-netcup-agent-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".xml")
    shutil.copy2(FILE, out)
    os.chmod(out, 0o600)
    original_mode = FILE.stat().st_mode & 0o777
    tmp = FILE.with_name(".ossec.conf.p620-wazuh.tmp")
    tmp.write_text(cfg, encoding="utf-8")
    os.chmod(tmp, original_mode)
    os.replace(tmp, FILE)
    print("CONFIG_VALID; WP_CONFIG_FIM_FILES",len(files),"PHP_LOG_ENABLED",PHP_LOG.is_file())
    print("BACKUP",str(out))

if __name__ == "__main__":
    main()
