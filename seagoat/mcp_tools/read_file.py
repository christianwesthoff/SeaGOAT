from __future__ import annotations

from pathlib import Path
from typing import Any

from seagoat.mcp_tools.search import validate_repo_path
from seagoat.utils.file_reader import read_file_with_correct_encoding

MAX_READ_LINES = 200


def resolve_file_path(repo_path: str, file_path: str) -> Path:
    repo = Path(validate_repo_path(repo_path))
    requested_path = Path(file_path).expanduser()
    full_path = (
        requested_path.resolve()
        if requested_path.is_absolute()
        else (repo / requested_path).resolve()
    )

    if repo not in [full_path, *full_path.parents]:
        raise ValueError("file_path must stay inside repo_path")
    if not full_path.exists():
        raise FileNotFoundError(f"file_path does not exist: {full_path}")
    if not full_path.is_file():
        raise IsADirectoryError(f"file_path is not a file: {full_path}")

    return full_path


def build_read_summary(*, full_path: Path, start_line: int, end_line: int) -> str:
    return f"SeaGOAT read lines {start_line}-{end_line} from '{full_path}'."


def run_read_file_tool(
    *,
    repo_path: str,
    file_path: str,
    start_line: int = 1,
    end_line: int | None = None,
) -> dict[str, Any]:
    if start_line < 1:
        raise ValueError("start_line must be greater than or equal to 1")
    if end_line is not None and end_line < start_line:
        raise ValueError("end_line must be greater than or equal to start_line")

    normalized_repo_path = validate_repo_path(repo_path)
    full_path = resolve_file_path(normalized_repo_path, file_path)
    relative_path = full_path.relative_to(normalized_repo_path).as_posix()
    file_lines = read_file_with_correct_encoding(str(full_path)).splitlines()
    if start_line > len(file_lines):
        raise ValueError("start_line must not exceed total file lines")

    requested_end_line = end_line if end_line is not None else len(file_lines)
    bounded_end_line = min(requested_end_line, start_line + MAX_READ_LINES - 1)
    actual_end_line = min(bounded_end_line, len(file_lines))
    selected_lines = [
        {"line": line_number, "text": file_lines[line_number - 1]}
        for line_number in range(start_line, actual_end_line + 1)
    ]

    return {
        "summary": build_read_summary(
            full_path=full_path,
            start_line=start_line,
            end_line=actual_end_line,
        ),
        "repo_path": normalized_repo_path,
        "file_path": relative_path,
        "full_path": str(full_path),
        "start_line": start_line,
        "end_line": actual_end_line,
        "total_lines": len(file_lines),
        "truncated": requested_end_line > bounded_end_line,
        "lines": selected_lines,
    }
