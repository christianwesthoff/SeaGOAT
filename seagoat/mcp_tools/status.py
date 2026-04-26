from __future__ import annotations

from typing import Any

from seagoat.mcp_tools.search import validate_repo_path
from seagoat.utils.server import get_server_info, is_server_running


def run_server_status_tool(*, repo_path: str) -> dict[str, Any]:
    normalized_repo_path = validate_repo_path(repo_path)
    start_command = f"seagoat-server start {normalized_repo_path}"

    if not is_server_running(normalized_repo_path):
        return {
            "summary": f"No SeaGOAT server is running for '{normalized_repo_path}'.",
            "repo_path": normalized_repo_path,
            "running": False,
            "server_address": None,
            "start_command": start_command,
        }

    server_info = get_server_info(normalized_repo_path)
    return {
        "summary": f"SeaGOAT server is running for '{normalized_repo_path}'.",
        "repo_path": normalized_repo_path,
        "running": True,
        "server_address": server_info["address"],
        "start_command": start_command,
    }
