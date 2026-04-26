from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from seagoat.query_service import search_repo
from seagoat.utils.server import ServerDoesNotExist

DEFAULT_MCP_MAX_RESULTS = 20
DEFAULT_MCP_CONTEXT_ABOVE = 1
DEFAULT_MCP_CONTEXT_BELOW = 1
DEFAULT_MCP_REQUEST_TIMEOUT_SECONDS = 20


def validate_repo_path(repo_path: str) -> str:
    path = Path(repo_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"repo_path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {path}")
    return str(path)


def build_summary(*, query: str, repo_path: str, result_count: int) -> str:
    noun = "result" if result_count == 1 else "results"
    return (
        f"SeaGOAT searched '{repo_path}' for '{query}' and returned "
        f"{result_count} {noun}."
    )


def run_search_tool(
    *,
    query: str,
    repo_path: str,
    max_results: int | None = None,
    context_above: int | None = None,
    context_below: int | None = None,
    include_performance: bool = False,
) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")

    normalized_repo_path = validate_repo_path(repo_path)

    try:
        search_kwargs = {
            "query": normalized_query,
            "repo_path": normalized_repo_path,
            "max_results": DEFAULT_MCP_MAX_RESULTS
            if max_results is None
            else max_results,
            "context_above": DEFAULT_MCP_CONTEXT_ABOVE
            if context_above is None
            else context_above,
            "context_below": DEFAULT_MCP_CONTEXT_BELOW
            if context_below is None
            else context_below,
            "request_timeout": DEFAULT_MCP_REQUEST_TIMEOUT_SECONDS,
        }
        if include_performance:
            search_kwargs["include_performance"] = True

        search_data = search_repo(**search_kwargs)
    except ServerDoesNotExist as exc:
        raise RuntimeError(
            "No SeaGOAT server is running for "
            f"'{normalized_repo_path}'. Start it with: "
            f"seagoat-server start {normalized_repo_path}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "SeaGOAT search timed out after "
            f"{DEFAULT_MCP_REQUEST_TIMEOUT_SECONDS} seconds for "
            f"'{normalized_repo_path}' while searching for '{normalized_query}'. "
            "Try a narrower query or lower max_results."
        ) from exc

    result_count = len(search_data["results"])
    result = {
        "summary": build_summary(
            query=normalized_query,
            repo_path=normalized_repo_path,
            result_count=result_count,
        ),
        "repo_path": normalized_repo_path,
        "server_address": search_data["server_address"],
        "result_count": result_count,
        "results": search_data["results"],
    }
    if "performance" in search_data:
        result["performance"] = search_data["performance"]
    return result
