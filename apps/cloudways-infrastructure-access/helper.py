#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent.parent / "packages", HERE / "packages"):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break

if os.environ.get("MCP_TARGET_CLASS") == "NETCUP_SELF_MANAGED_ROOT_SERVER":
    from infrastructure_read_policy.netcup_helper import netcup_helper_main
    if __name__ == "__main__":
        raise SystemExit(netcup_helper_main())
else:
    from infrastructure_read_policy.cloudways_helper import helper_main
    if __name__ == "__main__":
        raise SystemExit(helper_main())
