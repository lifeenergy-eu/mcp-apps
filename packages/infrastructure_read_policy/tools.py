from __future__ import annotations

from typing import Any, Callable

from .client import FixedHelperClient

RO = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
TOOL_NAMES = (
    "connector_health",
    "system_info",
    "disk_usage",
    "service_status",
    "journal_read",
    "process_list",
    "socket_list",
    "file_read",
    "file_stat",
    "dir_list",
    "file_find",
    "hash_file",
    "git_read",
    "sqlite_read_only",
)


def install_read_only_tools(
    mcp: Any,
    helper: FixedHelperClient,
    health_factory: Callable[[], dict[str, Any]],
    default_git_repo: str = "",
    target_id: str = "",
) -> None:
    @mcp.tool(annotations=RO)
    def connector_health() -> dict[str, Any]:
        """Return connector version and enforced security posture."""
        return health_factory()

    @mcp.tool(annotations=RO)
    def system_info() -> dict[str, Any]:
        """Read OS, uptime, memory and CPU diagnostics."""
        return helper.call("SYSTEM_INFO")

    @mcp.tool(annotations=RO)
    def disk_usage() -> dict[str, Any]:
        """Read bounded filesystem usage."""
        return helper.call("DISK_USAGE")

    @mcp.tool(annotations=RO)
    def service_status(units: list[str]) -> dict[str, Any]:
        """Read status for allowlisted service units only."""
        return helper.call("SERVICE_STATUS", units=units)

    @mcp.tool(annotations=RO)
    def journal_read(units: list[str], lines: int = 300, since: str = "", until: str = "") -> dict[str, Any]:
        """Read bounded journal output for allowlisted service units only."""
        return helper.call("JOURNAL_READ", units=units, lines=lines, since=since, until=until)

    @mcp.tool(annotations=RO)
    def process_list() -> dict[str, Any]:
        """Read process metadata without process arguments or environment."""
        return helper.call("PROCESS_LIST")

    @mcp.tool(annotations=RO)
    def socket_list() -> dict[str, Any]:
        """Read listening TCP/UDP sockets."""
        return helper.call("SOCKET_LIST")

    @mcp.tool(annotations=RO)
    def file_read(path: str, limit: int = 65536, offset: int = 0) -> dict[str, Any]:
        """Read bounded text from an allowlisted non-sensitive path."""
        return helper.call("FILE_READ", path=path, limit=limit, offset=offset)

    @mcp.tool(annotations=RO)
    def file_stat(path: str) -> dict[str, Any]:
        """Read metadata for an allowlisted non-sensitive path."""
        return helper.call("FILE_STAT", path=path)

    @mcp.tool(annotations=RO)
    def dir_list(path: str, limit: int = 200) -> dict[str, Any]:
        """List an allowlisted directory without following escaping symlinks."""
        return helper.call("DIR_LIST", path=path, limit=limit)

    @mcp.tool(annotations=RO)
    def file_find(path: str, name_contains: str, limit: int = 100) -> dict[str, Any]:
        """Find paths by bounded name substring under an allowlisted root."""
        return helper.call("FILE_FIND", path=path, name_contains=name_contains, limit=limit)

    @mcp.tool(annotations=RO)
    def hash_file(path: str) -> dict[str, Any]:
        """Return SHA-256 and size for an allowlisted file."""
        return helper.call("HASH_FILE", path=path)

    @mcp.tool(annotations=RO)
    def git_read(repo: str = default_git_repo, op: str = "status", limit: int = 20) -> dict[str, Any]:
        """Read bounded Git state from an explicitly allowlisted repository."""
        return helper.call("GIT_READ", repo=repo, op=op, limit=limit)

    @mcp.tool(annotations=RO)
    def sqlite_read_only(path: str, query: str, limit: int = 200) -> dict[str, Any]:
        """Execute one bounded read-only SQLite statement on an allowlisted database."""
        return helper.call("SQLITE_READ_ONLY", path=path, query=query, limit=limit)

    if target_id == "SERVER-CLOUDWAYS-MAGENTO":
        @mcp.tool(annotations=RO)
        def project_brain_relay_health(max_events: int = 10) -> dict[str, Any]:
            """Read fixed redacted dispatcher liveness independently of relay."""
            return helper.call("PROJECT_BRAIN_RELAY_HEALTH", max_events=max_events)
