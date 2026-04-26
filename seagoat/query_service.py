from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import requests

from seagoat.utils.server import get_server_info


def query_lines(
    *,
    server_address: str,
    query: str,
    max_results: int | None,
    context_above: int,
    context_below: int,
    request_timeout: float | None = None,
) -> dict[str, Any]:
    request_kwargs: dict[str, Any] = {
        "json": {
            "queryText": query,
            "limitClue": max_results,
            "contextAbove": context_above,
            "contextBelow": context_below,
        },
        "headers": {"Content-Type": "application/json"},
    }
    if request_timeout is not None:
        request_kwargs["timeout"] = request_timeout

    response = requests.post(f"{server_address}/lines/query", **request_kwargs)

    response_data = orjson.loads(response.text)

    if "error" in response_data:
        raise RuntimeError(response_data["error"]["message"])

    response.raise_for_status()

    return response_data


def rewrite_full_paths_to_use_local_path(
    repo_path: str | Path, results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    normalized_repo_path = Path(repo_path).expanduser().resolve()
    return [
        {
            **result,
            "fullPath": str((normalized_repo_path / result["path"]).resolve()),
        }
        for result in results
    ]


def remove_results_from_unavailable_files(
    results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [result for result in results if Path(result["fullPath"]).exists()]


def search_repo(
    *,
    query: str,
    repo_path: str | Path,
    max_results: int | None,
    context_above: int,
    context_below: int,
    server_address: str | None = None,
    request_timeout: float | None = None,
) -> dict[str, Any]:
    normalized_repo_path = str(Path(repo_path).expanduser().resolve())
    resolved_server_address = server_address
    if resolved_server_address is None:
        server_info = get_server_info(normalized_repo_path)
        resolved_server_address = server_info["address"]

    response_data = query_lines(
        server_address=resolved_server_address,
        query=query,
        max_results=max_results,
        context_above=context_above,
        context_below=context_below,
        request_timeout=request_timeout,
    )
    results = rewrite_full_paths_to_use_local_path(
        normalized_repo_path, response_data["results"]
    )
    return {
        "repo_path": normalized_repo_path,
        "server_address": resolved_server_address,
        "results": results,
        "version": response_data.get("version"),
    }
