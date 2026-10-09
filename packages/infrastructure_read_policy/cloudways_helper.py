from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

SECRET_NAME_RE = re.compile(r"(?i)(password|passwd|secret|token|credential|api[_-]?key|authorization)")
SECRET_VALUE_PATTERNS = [
    re.compile(r"(?i)\b(authorization)\s*:\s*bearer\s+[A-Za-z0-9._~+/\-=]+"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|db[_-]?(?:password|pass))\s*[:=]\s*[^\s,;]+"),
]
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")
SAFE_GIT_OPS = {"status", "log", "head", "branch"}
SAFE_PRAGMAS = {
    "table_info", "index_info", "index_list", "foreign_key_list",
    "database_list", "schema_version", "page_count", "freelist_count",
}
MAX_HELPER_OUTPUT = 2_000_000


class PolicyError(RuntimeError):
    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _env_json_list(name: str) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise PolicyError(f"{name}_INVALID_JSON") from exc
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise PolicyError(f"{name}_INVALID")
    return [v.strip() for v in value]


def _real_existing(path: str) -> str:
    try:
        return os.path.realpath(path, strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise PolicyError("PATH_NOT_FOUND") from exc


def _within(path: str, roots: list[str]) -> bool:
    for root in roots:
        try:
            if os.path.commonpath([path, root]) == root:
                return True
        except ValueError:
            continue
    return False


def _sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    parts = [p for p in normalized.split("/") if p]
    if ".ssh" in parts:
        return True
    if any(p in {".env", "wp-config.php", "auth.json", "authorized_keys"} for p in parts):
        return True
    if normalized.endswith("/app/etc/local.xml") or normalized.endswith("/app/etc/env.php"):
        return True
    if any(p.endswith((".pem", ".key", ".p12", ".pfx")) for p in parts):
        return True
    if any(SECRET_NAME_RE.search(p) for p in parts):
        return True
    return False


def redact_text(text: str) -> str:
    out = text
    for pattern in SECRET_VALUE_PATTERNS:
        out = pattern.sub(lambda m: m.group(1) + "=[REDACTED]", out)
    out = PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY_HEADER]", out)
    return out


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_NAME_RE.search(str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = redact_value(item)
        return out
    return value


class RuntimePolicy:
    def __init__(self) -> None:
        self.target_id = os.environ.get("MCP_TARGET_ID", "").strip()
        self.profile_id = os.environ.get("MCP_PROFILE_ID", "").strip()
        if not self.target_id or not self.profile_id:
            raise PolicyError("TARGET_PROFILE_IDENTITY_MISSING")
        self.allowed_roots = [_real_existing(v) for v in _env_json_list("MCP_ALLOWED_ROOTS_JSON")]
        self.allowed_git_roots = [_real_existing(v) for v in _env_json_list("MCP_ALLOWED_GIT_ROOTS_JSON")]
        self.allowed_services = set(_env_json_list("MCP_ALLOWED_SERVICES_JSON"))
        self.allowed_sqlite = [_real_existing(v) for v in _env_json_list("MCP_ALLOWED_SQLITE_PATHS_JSON")]
        if not self.allowed_roots:
            raise PolicyError("ALLOWED_ROOTS_EMPTY")
        for path in self.allowed_roots + self.allowed_git_roots + self.allowed_sqlite:
            if _sensitive_path(path):
                raise PolicyError("SENSITIVE_ALLOWLIST_ENTRY_FORBIDDEN")
        self.max_file_bytes = min(max(int(os.environ.get("MCP_MAX_FILE_BYTES", "65536")), 1), 1_048_576)
        self.max_find_results = min(max(int(os.environ.get("MCP_MAX_FIND_RESULTS", "200")), 1), 2000)

    def allowed_path(self, path: str, require_file: bool | None = None) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise PolicyError("PATH_ABSOLUTE_REQUIRED")
        real = _real_existing(path)
        if not _within(real, self.allowed_roots):
            raise PolicyError("PATH_OUTSIDE_ALLOWED_ROOTS")
        if _sensitive_path(real):
            raise PolicyError("SENSITIVE_PATH_DENIED")
        if require_file is True and not os.path.isfile(real):
            raise PolicyError("FILE_REQUIRED")
        if require_file is False and not os.path.isdir(real):
            raise PolicyError("DIRECTORY_REQUIRED")
        return real

    def git_root(self, repo: str) -> str:
        real = _real_existing(repo)
        if real not in self.allowed_git_roots:
            raise PolicyError("GIT_ROOT_NOT_ALLOWLISTED")
        if _sensitive_path(real):
            raise PolicyError("SENSITIVE_PATH_DENIED")
        return real

    def sqlite_path(self, path: str) -> str:
        real = _real_existing(path)
        if real not in self.allowed_sqlite:
            raise PolicyError("SQLITE_PATH_NOT_ALLOWLISTED")
        if _sensitive_path(real):
            raise PolicyError("SENSITIVE_PATH_DENIED")
        return real

    def service(self, unit: str) -> str:
        if not isinstance(unit, str) or unit not in self.allowed_services:
            raise PolicyError("SERVICE_NOT_ALLOWLISTED")
        if not re.fullmatch(r"[A-Za-z0-9@_.:-]{1,128}", unit):
            raise PolicyError("SERVICE_NAME_INVALID")
        return unit


def _run(argv: list[str], timeout: int = 20, accepted: set[int] | None = None) -> dict[str, Any]:
    accepted = accepted or {0}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, shell=False, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C"})
    except FileNotFoundError as exc:
        raise PolicyError("HOST_CAPABILITY_UNAVAILABLE", {"executable": Path(argv[0]).name}) from exc
    except subprocess.TimeoutExpired as exc:
        raise PolicyError("HOST_COMMAND_TIMEOUT") from exc
    if proc.returncode not in accepted:
        raise PolicyError("HOST_COMMAND_FAILED", {"rc": proc.returncode, "command": Path(argv[0]).name})
    return {
        "rc": proc.returncode,
        "stdout": redact_text((proc.stdout or "")[:MAX_HELPER_OUTPUT]),
        "stderr": redact_text((proc.stderr or "")[:100_000]),
    }



def _unavailable_output(result: dict[str, Any]) -> bool:
    text = ((result.get("stdout") or "") + "\n" + (result.get("stderr") or "")).lower()
    return any(marker in text for marker in (
        "permission denied",
        "access denied",
        "not permitted",
        "failed to open journal",
        "no journal files were opened",
    ))

def _system_info(_: RuntimePolicy, __: dict[str, Any]) -> dict[str, Any]:
    uname = _run(["/usr/bin/uname", "-srm"])
    uptime = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
    mem = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            if k in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                mem[k] = v.strip()
    return {"uname": uname["stdout"].strip(), "uptime_seconds": float(uptime), "memory": mem, "cpu_logical": os.cpu_count()}


def _disk_usage(_: RuntimePolicy, __: dict[str, Any]) -> dict[str, Any]:
    return _run(["/bin/df", "-P", "-B1"])


def _service_status(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    units = params.get("units")
    if not isinstance(units, list) or not units or len(units) > 20:
        raise PolicyError("UNITS_INVALID")
    out = {}
    for raw in units:
        unit = policy.service(str(raw))
        result = _run([
            "/bin/systemctl", "show", unit, "--no-pager",
            "--property=Id,LoadState,ActiveState,SubState,UnitFileState,MainPID",
        ], accepted={0, 1, 3, 4})
        if _unavailable_output(result):
            raise PolicyError("HOST_CAPABILITY_UNAVAILABLE", {"capability": "service_status"})
        out[unit] = result
    return {"units": out}


def _journal_read(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    units = params.get("units")
    if not isinstance(units, list) or not units or len(units) > 8:
        raise PolicyError("UNITS_INVALID")
    lines = min(max(int(params.get("lines", 300)), 1), 1000)
    since = str(params.get("since") or "").strip()
    until = str(params.get("until") or "").strip()
    argv = ["/bin/journalctl", "--no-pager", "-n", str(lines), "-o", "short-iso"]
    for raw in units:
        argv.extend(["-u", policy.service(str(raw))])
    if since:
        if len(since) > 80:
            raise PolicyError("SINCE_INVALID")
        argv.extend(["--since", since])
    if until:
        if len(until) > 80:
            raise PolicyError("UNTIL_INVALID")
        argv.extend(["--until", until])
    result = _run(argv, timeout=30, accepted={0, 1})
    if _unavailable_output(result):
        raise PolicyError("HOST_CAPABILITY_UNAVAILABLE", {"capability": "journal_read"})
    return result


def _process_list(_: RuntimePolicy, __: dict[str, Any]) -> dict[str, Any]:
    return _run([
        "/bin/ps", "-eo",
        "pid=,ppid=,user=,comm=,%cpu=,%mem=,rss=,vsz=,etimes=",
        "--sort=-%cpu",
    ])


def _socket_list(_: RuntimePolicy, __: dict[str, Any]) -> dict[str, Any]:
    return _run(["/usr/bin/ss", "-lntuH"], accepted={0, 1})


def _file_read(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.allowed_path(str(params.get("path") or ""), require_file=True)
    limit = min(max(int(params.get("limit", policy.max_file_bytes)), 1), policy.max_file_bytes)
    offset = max(int(params.get("offset", 0)), 0)
    with open(path, "rb") as fh:
        fh.seek(offset)
        raw = fh.read(limit)
    text = raw.decode("utf-8", "replace")
    return {"path": path, "offset": offset, "bytes": len(raw), "content": redact_text(text), "truncated": len(raw) == limit}


def _file_stat(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.allowed_path(str(params.get("path") or ""))
    st = os.stat(path, follow_symlinks=False)
    return {
        "path": path,
        "mode_octal": oct(stat.S_IMODE(st.st_mode)),
        "size": st.st_size,
        "mtime_epoch": int(st.st_mtime),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "type": "directory" if stat.S_ISDIR(st.st_mode) else "file" if stat.S_ISREG(st.st_mode) else "other",
    }


def _dir_list(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.allowed_path(str(params.get("path") or ""), require_file=False)
    limit = min(max(int(params.get("limit", 200)), 1), 1000)
    rows = []
    with os.scandir(path) as it:
        for entry in it:
            candidate = os.path.join(path, entry.name)
            if _sensitive_path(candidate):
                continue
            try:
                real = os.path.realpath(candidate, strict=True)
            except OSError:
                continue
            if not _within(real, policy.allowed_roots):
                continue
            rows.append({
                "name": entry.name,
                "type": "symlink" if entry.is_symlink() else "directory" if entry.is_dir(follow_symlinks=False) else "file",
            })
            if len(rows) >= limit:
                break
    return {"path": path, "entries": sorted(rows, key=lambda x: x["name"])}


def _file_find(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.allowed_path(str(params.get("path") or ""), require_file=False)
    needle = str(params.get("name_contains") or "").strip()
    if not needle or len(needle) > 128 or SECRET_NAME_RE.search(needle):
        raise PolicyError("NAME_FILTER_INVALID")
    limit = min(max(int(params.get("limit", 100)), 1), policy.max_find_results)
    out: list[str] = []
    for current, dirs, files in os.walk(path, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if not _sensitive_path(os.path.join(current, d))]
        for name in dirs + files:
            if needle.lower() not in name.lower():
                continue
            candidate = os.path.join(current, name)
            if _sensitive_path(candidate):
                continue
            try:
                real = os.path.realpath(candidate, strict=True)
            except OSError:
                continue
            if _within(real, policy.allowed_roots):
                out.append(real)
                if len(out) >= limit:
                    return {"path": path, "matches": out, "truncated": True}
    return {"path": path, "matches": out, "truncated": False}


def _hash_file(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.allowed_path(str(params.get("path") or ""), require_file=True)
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return {"path": path, "sha256": h.hexdigest(), "size": size}


def _git_read(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    repo = policy.git_root(str(params.get("repo") or ""))
    op = str(params.get("op") or "status")
    if op not in SAFE_GIT_OPS:
        raise PolicyError("GIT_OPERATION_DENIED")
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    if op == "status":
        result = _run(["/usr/bin/git", "-C", repo, "status", "--short", "--untracked-files=normal"])
        lines = [x for x in result["stdout"].splitlines() if not _sensitive_path(x[3:].strip())][:limit]
        return {"repo": repo, "op": op, "lines": lines}
    if op == "log":
        result = _run(["/usr/bin/git", "-C", repo, "log", f"-n{limit}", "--pretty=format:%H%x09%ct%x09%s"])
        return {"repo": repo, "op": op, "lines": result["stdout"].splitlines()[:limit]}
    if op == "head":
        result = _run(["/usr/bin/git", "-C", repo, "rev-parse", "HEAD"])
        return {"repo": repo, "op": op, "head": result["stdout"].strip()}
    result = _run(["/usr/bin/git", "-C", repo, "branch", "--show-current"])
    return {"repo": repo, "op": op, "branch": result["stdout"].strip()}


def _validate_query(query: str) -> str:
    q = query.strip()
    if not q or len(q) > 20_000 or "\x00" in q:
        raise PolicyError("SQLITE_QUERY_INVALID")
    if SECRET_NAME_RE.search(q):
        raise PolicyError("SQLITE_SENSITIVE_COLUMN_QUERY_DENIED")
    if ";" in q.rstrip(";"):
        raise PolicyError("SQLITE_MULTISTATEMENT_DENIED")
    q = q.rstrip(";").strip()
    upper = q.upper()
    if upper.startswith(("SELECT ", "WITH ", "EXPLAIN ")):
        return q
    m = re.fullmatch(r"(?is)PRAGMA\s+([A-Za-z_]+)(?:\s*\(\s*[^;()]{0,256}\s*\))?", q)
    if m and m.group(1).lower() in SAFE_PRAGMAS:
        return q
    raise PolicyError("SQLITE_STATEMENT_DENIED")


def _sqlite_read_only(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    path = policy.sqlite_path(str(params.get("path") or ""))
    query = _validate_query(str(params.get("query") or ""))
    limit = min(max(int(params.get("limit", 200)), 1), 1000)
    uri = "file:" + Path(path).as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        cur = con.execute(query)
        columns = [d[0] for d in (cur.description or [])]
        rows = []
        for row in cur.fetchmany(limit + 1):
            rows.append(redact_value({columns[i]: row[i] for i in range(len(columns))}))
        truncated = len(rows) > limit
        return {"path": path, "columns": columns, "rows": rows[:limit], "truncated": truncated}
    finally:
        con.close()



# Target-local, fixed-file Read MCP observability. Not a relay execution route.
RELAY_OBSERVABILITY_ROOT = Path("/home/master/.project-brain/control-plane/relay/runtime")
_RELAY_ID_RE = re.compile(r'(?:operation_id["\x27]?\s*[:=]\s*["\x27]?|operation[ =]+)([A-Z][A-Z0-9_.-]{7,79})')
_RELAY_ERROR_RE = re.compile(r'\b(?:FAIL_CLOSED|BATCH_[A-Z0-9_]{4,64}|RELAY_[A-Z0-9_]{4,64}|GITHUB_[A-Z0-9_]{4,64}|RUN_CORE_[A-Z0-9_]{4,64}|SOURCE_[A-Z0-9_]{4,64}|INTAKE_[A-Z0-9_]{4,64}|OPERATION_[A-Z0-9_]{4,64})\b')
_RELAY_SECRET_WORDS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "CREDENTIAL", "AUTH")


def _relay_read_fixed(name: str, size: int, tail: bool = False):
    fixed = RELAY_OBSERVABILITY_ROOT / name
    if fixed.is_symlink():
        raise PolicyError("RELAY_DIAG_SYMLINK_DENIED")
    try:
        fd = os.open(fixed, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PolicyError("RELAY_DIAG_FILE_UNAVAILABLE") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PolicyError("RELAY_DIAG_NOT_REGULAR_FILE")
        if st.st_size > size and not tail:
            raise PolicyError("RELAY_DIAG_FILE_OVERSIZE")
        if tail:
            os.lseek(fd, max(0, st.st_size - size), os.SEEK_SET)
        return (os.read(fd, size), st)
    except OSError as exc:
        raise PolicyError("RELAY_DIAG_READ_FAILED") from exc
    finally:
        os.close(fd)


def _project_brain_relay_health(policy: RuntimePolicy, params: dict[str, Any]) -> dict[str, Any]:
    if policy.target_id != "SERVER-CLOUDWAYS-MAGENTO":
        raise PolicyError("RELAY_DIAG_TARGET_DENIED")
    if set(params) - {"action", "max_events"}:
        raise PolicyError("RELAY_DIAG_PARAMETERS_DENIED")
    limit = params.get("max_events", 10)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise PolicyError("RELAY_DIAG_LIMIT_DENIED")
    if RELAY_OBSERVABILITY_ROOT.is_symlink() or not RELAY_OBSERVABILITY_ROOT.is_dir():
        raise PolicyError("RELAY_DIAG_ROOT_UNAVAILABLE")
    heartbeat = _relay_read_fixed("dispatcher_heartbeat_epoch", 32)
    process = _relay_read_fixed("dispatcher_daemon.pid", 32)
    log = _relay_read_fixed("relay.log", 16384, True)
    age = None
    if heartbeat is not None and re.fullmatch(rb"[0-9]{1,15}", heartbeat[0].strip()):
        age = max(0, int(time.time()) - int(heartbeat[0].strip()))
    alive = False
    if process is not None and re.fullmatch(rb"[1-9][0-9]{0,9}", process[0].strip()):
        try:
            os.kill(int(process[0].strip()), 0)
            alive = True
        except PermissionError:
            alive = True
        except (ProcessLookupError, OverflowError, OSError):
            pass
    operations = []
    failures = []
    if log is not None:
        sample = log[0].decode("utf-8", "replace")
        operations = list(dict.fromkeys(_RELAY_ID_RE.findall(sample)))[-limit:]
        failures = list(dict.fromkeys(
            code for code in _RELAY_ERROR_RE.findall(sample)
            if not any(word in code for word in _RELAY_SECRET_WORDS)
        ))[-limit:]
    return {
        "heartbeat_age_seconds": age, "dispatcher_pid_alive": alive,
        "log_mtime_epoch": int(log[1].st_mtime) if log else None,
        "log_size_bytes": log[1].st_size if log else None,
        "recent_operation_ids_matching_uppercase_id_format": operations,
        "recent_fixed_failure_codes": failures,
        "raw_log_lines_returned": False,
        "diagnostic_transport": "DIRECT_READ_MCP_NO_RELAY",
    }


ACTIONS: dict[str, Callable[[RuntimePolicy, dict[str, Any]], dict[str, Any]]] = {
    "SYSTEM_INFO": _system_info,
    "DISK_USAGE": _disk_usage,
    "SERVICE_STATUS": _service_status,
    "JOURNAL_READ": _journal_read,
    "PROCESS_LIST": _process_list,
    "SOCKET_LIST": _socket_list,
    "FILE_READ": _file_read,
    "FILE_STAT": _file_stat,
    "DIR_LIST": _dir_list,
    "FILE_FIND": _file_find,
    "HASH_FILE": _hash_file,
    "GIT_READ": _git_read,
    "SQLITE_READ_ONLY": _sqlite_read_only,
    "PROJECT_BRAIN_RELAY_HEALTH": _project_brain_relay_health,
}


def execute_request(request: dict[str, Any]) -> dict[str, Any]:
    policy = RuntimePolicy()
    action = str(request.get("action") or "")
    if action not in ACTIONS:
        raise PolicyError("ACTION_DENIED")
    started = time.monotonic()
    result = ACTIONS[action](policy, request)
    return {
        "status": "PASS",
        "action": action,
        "target_id": policy.target_id,
        "profile_id": policy.profile_id,
        "result": redact_value(result),
        "read_only": True,
        "arbitrary_shell": False,
        "mutation": False,
        "secret_values_emitted": False,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def helper_main() -> int:
    try:
        raw = os.read(0, 1_000_000).decode("utf-8")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise PolicyError("REQUEST_INVALID")
        payload = execute_request(request)
        print(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        return 0
    except PolicyError as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "code": exc.code,
            "details": redact_value(exc.details),
            "read_only": True,
            "arbitrary_shell": False,
            "mutation": False,
            "secret_values_emitted": False,
        }, separators=(",", ":"), ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps({
            "status": "FAIL_CLOSED",
            "code": "HELPER_EXECUTION_FAILED",
            "details": {"type": type(exc).__name__},
            "read_only": True,
            "arbitrary_shell": False,
            "mutation": False,
            "secret_values_emitted": False,
        }, separators=(",", ":"), ensure_ascii=False))
        return 2
