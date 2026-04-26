from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from seagoat.mcp_tools.search import validate_repo_path

DEFAULT_MCP_GREP_MAX_RESULTS = 50
DEFAULT_MCP_GREP_TIMEOUT_SECONDS = 10.0


def build_grep_summary(*, pattern: str, repo_path: str, result_count: int) -> str:
    noun = "result" if result_count == 1 else "results"
    return (
        f"SeaGOAT grep searched '{repo_path}' for '{pattern}' and returned "
        f"{result_count} {noun}."
    )


def _rg_text(value: dict[str, Any]) -> str:
    text = value.get("text")
    if isinstance(text, str):
        return text

    bytes_value = value.get("bytes")
    if isinstance(bytes_value, str):
        return bytes_value

    return ""


def _parse_rg_json_line(line: str, repo_path: str) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if event.get("type") != "match":
        return None

    data = event.get("data")
    if not isinstance(data, dict):
        return None

    path = data.get("path")
    lines = data.get("lines")
    line_number = data.get("line_number")
    if not isinstance(path, dict) or not isinstance(lines, dict):
        return None
    if not isinstance(line_number, int):
        return None

    file_path = _rg_text(path)
    if not file_path:
        return None
    if file_path.startswith("./"):
        file_path = file_path[2:]

    full_path = (Path(repo_path) / file_path).resolve()
    return {
        "file_path": file_path,
        "full_path": str(full_path),
        "line": line_number,
        "text": _rg_text(lines).rstrip("\n"),
    }


def _run_rg_bounded(
    command: list[str],
    repo_path: str,
    limit: int,
    timeout_seconds: float,
) -> tuple[list[str], int, str, bool]:
    process = subprocess.Popen(
        command,
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stdout_lines: list[str] = []
    match_count = 0
    timed_out = False
    start_time = time.monotonic()
    assert process.stdout is not None
    for line in process.stdout:
        stdout_lines.append(line)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = {}
        if event.get("type") == "match":
            match_count += 1
            if time.monotonic() - start_time >= timeout_seconds:
                timed_out = True
                process.terminate()
                break
        if match_count >= limit:
            process.terminate()
            break

    try:
        _, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate()

    return stdout_lines, process.returncode, stderr, timed_out


def run_grep_tool(
    *,
    repo_path: str,
    pattern: str,
    max_results: int | None = None,
    case_sensitive: bool = False,
    regex: bool = False,
    path_glob: str | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    normalized_pattern = pattern.strip()
    if not normalized_pattern:
        raise ValueError("pattern must not be empty")

    normalized_repo_path = validate_repo_path(repo_path)
    effective_max_results = (
        DEFAULT_MCP_GREP_MAX_RESULTS if max_results is None else max_results
    )
    if effective_max_results < 1:
        raise ValueError("max_results must be greater than or equal to 1")
    effective_timeout_seconds = (
        DEFAULT_MCP_GREP_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    )
    if effective_timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")

    command = [
        "rg",
        "--json",
        "--line-number",
        "--with-filename",
        "--no-heading",
        "--color",
        "never",
    ]
    if not regex:
        command.append("--fixed-strings")
    if not case_sensitive:
        command.append("--ignore-case")
    if path_glob is not None:
        command.extend(["--glob", path_glob])
    command.append("--")
    command.append(normalized_pattern)
    command.append(".")

    requested_results = effective_max_results + 1
    stdout_lines, return_code, stderr, timed_out = _run_rg_bounded(
        command,
        normalized_repo_path,
        requested_results,
        effective_timeout_seconds,
    )

    if return_code not in (0, 1, -15) and not timed_out:
        message = stderr.strip() or f"ripgrep exited with status {return_code}"
        if regex:
            raise RuntimeError(f"Invalid grep regex pattern '{normalized_pattern}': {message}")
        raise RuntimeError(f"ripgrep failed while searching for '{normalized_pattern}': {message}")

    parsed_results = [
        result
        for line in stdout_lines
        if (result := _parse_rg_json_line(line, normalized_repo_path)) is not None
    ]
    truncated = len(parsed_results) > effective_max_results
    results = parsed_results[:effective_max_results]
    result_count = len(results)
    output = {
        "summary": build_grep_summary(
            pattern=normalized_pattern,
            repo_path=normalized_repo_path,
            result_count=result_count,
        ),
        "repo_path": normalized_repo_path,
        "pattern": normalized_pattern,
        "result_count": result_count,
        "max_results": effective_max_results,
        "truncated": truncated,
        "results": results,
    }
    if path_glob is not None:
        output["path_glob"] = path_glob
    if timeout_seconds is not None:
        output["timeout_seconds"] = effective_timeout_seconds
        output["timed_out"] = timed_out
        output["partial"] = timed_out
    return output
