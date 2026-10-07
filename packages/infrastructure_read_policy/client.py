from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class HelperClientError(RuntimeError):
    pass


class FixedHelperClient:
    """Invoke one fixed host helper. No caller-selected command, argv prefix or shell."""

    def __init__(self, helper: str, mode: str = "direct", timeout: int = 40) -> None:
        path = Path(helper)
        if not path.is_absolute():
            raise HelperClientError("MCP_READ_HELPER_ABSOLUTE_PATH_REQUIRED")
        self.helper = str(path)
        if mode not in {"direct", "python3_direct", "sudo_noninteractive"}:
            raise HelperClientError("MCP_READ_HELPER_MODE_INVALID")
        self.mode = mode
        self.timeout = min(max(int(timeout), 1), 120)

    @classmethod
    def from_environment(
        cls,
        default_helper: str,
        default_mode: str = "direct",
        default_timeout: int = 40,
    ) -> "FixedHelperClient":
        helper = os.environ.get("MCP_READ_HELPER", "").strip() or default_helper
        mode = os.environ.get("MCP_READ_HELPER_MODE", "").strip() or default_mode
        timeout = int(os.environ.get("MCP_READ_HELPER_TIMEOUT", str(default_timeout)))
        return cls(helper=helper, mode=mode, timeout=timeout)

    def _argv(self) -> list[str]:
        if self.mode == "direct":
            return [self.helper]
        if self.mode == "python3_direct":
            return ["/usr/bin/python3", self.helper]
        return ["/usr/bin/sudo", "-n", self.helper]

    def call(self, action: str, **params: Any) -> dict[str, Any]:
        if not action or not action.replace("_", "").isalnum():
            raise HelperClientError("MCP_READ_HELPER_ACTION_INVALID")
        proc = subprocess.run(
            self._argv(),
            input=json.dumps({"action": action, **params}, separators=(",", ":")),
            capture_output=True,
            text=True,
            timeout=self.timeout,
            shell=False,
            env=os.environ.copy(),
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            raise HelperClientError("MCP_READ_HELPER_EMPTY_RESPONSE")
        try:
            body = json.loads(raw)
        except Exception as exc:
            raise HelperClientError("MCP_READ_HELPER_INVALID_RESPONSE") from exc
        if proc.returncode != 0 or body.get("status") != "PASS":
            raise HelperClientError(str(body.get("code") or "MCP_READ_HELPER_FAILED"))
        if body.get("read_only") is not True:
            raise HelperClientError("MCP_READ_HELPER_POLICY_INVARIANT_FAILED")
        if body.get("mutation") not in (None, False):
            raise HelperClientError("MCP_READ_HELPER_POLICY_INVARIANT_FAILED")
        if body.get("secret_values_emitted") not in (None, False):
            raise HelperClientError("MCP_READ_HELPER_POLICY_INVARIANT_FAILED")
        return body
