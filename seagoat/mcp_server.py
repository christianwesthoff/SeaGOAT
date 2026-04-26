from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from seagoat.mcp_tools.grep import run_grep_tool
from seagoat.mcp_tools.read_file import run_read_file_tool
from seagoat.mcp_tools.research import run_research_tool
from seagoat.mcp_tools.search import run_search_tool

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


class ResearchToolResult(BaseModel):
    summary: str
    repo_path: str
    question: str
    queries: list[dict[str, Any]]
    grouped_results: list[dict[str, Any]]
    suggested_reads: list[dict[str, Any]]


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
) -> GrepToolResult:
    return GrepToolResult.model_validate(
        run_grep_tool(
            repo_path=repo_path,
            pattern=pattern,
            max_results=max_results,
            case_sensitive=case_sensitive,
            regex=regex,
        )
    )


@mcp.tool()
def research(
    question: str,
    repo_path: str,
    max_results_per_query: int | None = None,
    include_performance: bool = False,
) -> ResearchToolResult:
    return ResearchToolResult.model_validate(
        run_research_tool(
            question=question,
            repo_path=repo_path,
            max_results_per_query=max_results_per_query,
            include_performance=include_performance,
        )
    )


def main() -> None:
    mcp.run()
