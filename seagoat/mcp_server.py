from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from seagoat.mcp_tools.grep import run_grep_tool
from seagoat.mcp_tools.read_file import run_read_file_tool
from seagoat.mcp_tools.reason import run_reason_tool
from seagoat.mcp_tools.research import run_research_tool
from seagoat.mcp_tools.search import run_search_tool
from seagoat.mcp_tools.status import run_server_status_tool

mcp = FastMCP("SeaGOAT")


class SearchToolResult(BaseModel):
    summary: str
    repo_path: str
    server_address: str
    result_count: int
    results: list[dict[str, Any]]
    performance: dict[str, Any] | None = None


class FileLine(BaseModel):
    line: int
    text: str


class ReadFileToolResult(BaseModel):
    summary: str
    repo_path: str
    file_path: str
    full_path: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    lines: list[FileLine]


class GrepToolResult(BaseModel):
    summary: str
    repo_path: str
    pattern: str
    result_count: int
    max_results: int
    truncated: bool
    results: list[dict[str, Any]]
    path_glob: str | None = None
    timeout_seconds: float | None = None
    timed_out: bool | None = None
    partial: bool | None = None


class ResearchToolResult(BaseModel):
    summary: str
    repo_path: str
    question: str
    queries: list[dict[str, Any]]
    grouped_results: list[dict[str, Any]]
    suggested_reads: list[dict[str, Any]]
    path_glob: str | None = None


class ReasonToolResult(BaseModel):
    summary: str
    repo_path: str
    question: str
    reasoning_plan: str
    plan: dict[str, Any]
    queries: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    reads_performed: list[dict[str, Any]]
    suggested_next_reads: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    confidence: str
    path_glob: str | None = None


class ServerStatusToolResult(BaseModel):
    summary: str
    repo_path: str
    running: bool
    server_address: str | None
    start_command: str


def _format_legacy_search_results(result: SearchToolResult) -> str:
    if not result.results:
        return "No results found."

    output_lines: list[str] = []
    for search_result in result.results:
        output_lines.append(f"File: {search_result['path']}\n")
        for block in search_result.get("blocks", []):
            for line in block.get("lines", []):
                output_lines.append(
                    f"{line['line']}: {line.get('lineText', line.get('text', ''))}\n"
                )
            output_lines.append("\n")
    return "".join(output_lines).rstrip()


@mcp.tool()
def search(
    query: str,
    repo_path: str,
    max_results: int | None = None,
    context_above: int | None = None,
    context_below: int | None = None,
    include_performance: bool = False,
) -> SearchToolResult:
    return SearchToolResult.model_validate(
        run_search_tool(
            query=query,
            repo_path=repo_path,
            max_results=max_results,
            context_above=context_above,
            context_below=context_below,
            include_performance=include_performance,
        )
    )


@mcp.tool()
def search_code(
    query: str,
    limit: int = 10,
    repo_path: str = "",
    context_above: int = 3,
    context_below: int = 3,
) -> str:
    try:
        result = SearchToolResult.model_validate(
            run_search_tool(
                query=query,
                repo_path=repo_path,
                max_results=limit,
                context_above=context_above,
                context_below=context_below,
            )
        )
    except (FileNotFoundError, NotADirectoryError, RuntimeError, ValueError) as exc:
        return f"Error: {exc}"
    return _format_legacy_search_results(result)


@mcp.tool()
def read_file(
    repo_path: str,
    file_path: str,
    start_line: int = 1,
    end_line: int | None = None,
) -> ReadFileToolResult:
    return ReadFileToolResult.model_validate(
        run_read_file_tool(
            repo_path=repo_path,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        )
    )


@mcp.tool()
def grep(
    repo_path: str,
    pattern: str,
    max_results: int | None = None,
    case_sensitive: bool = False,
    regex: bool = False,
    path_glob: str | None = None,
    timeout_seconds: float | None = None,
) -> GrepToolResult:
    return GrepToolResult.model_validate(
        run_grep_tool(
            repo_path=repo_path,
            pattern=pattern,
            max_results=max_results,
            case_sensitive=case_sensitive,
            regex=regex,
            path_glob=path_glob,
            timeout_seconds=timeout_seconds,
        )
    )


@mcp.tool()
def research(
    question: str,
    repo_path: str,
    max_results_per_query: int | None = None,
    include_performance: bool = False,
    path_glob: str | None = None,
) -> ResearchToolResult:
    return ResearchToolResult.model_validate(
        run_research_tool(
            question=question,
            repo_path=repo_path,
            max_results_per_query=max_results_per_query,
            include_performance=include_performance,
            path_glob=path_glob,
        )
    )


@mcp.tool()
def reason(
    question: str,
    repo_path: str,
    reasoning_plan: str = "query",
    path_glob: str | None = None,
    max_results_per_query: int | None = None,
    read_strategy: str = "auto",
    max_files_to_read: int = 8,
    context_above: int = 1,
    context_below: int = 1,
    include_performance: bool = False,
) -> ReasonToolResult:
    return ReasonToolResult.model_validate(
        run_reason_tool(
            question=question,
            repo_path=repo_path,
            reasoning_plan=reasoning_plan,
            path_glob=path_glob,
            max_results_per_query=max_results_per_query,
            read_strategy=read_strategy,
            max_files_to_read=max_files_to_read,
            context_above=context_above,
            context_below=context_below,
            include_performance=include_performance,
        )
    )


@mcp.tool()
def server_status(repo_path: str) -> ServerStatusToolResult:
    return ServerStatusToolResult.model_validate(
        run_server_status_tool(repo_path=repo_path)
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
