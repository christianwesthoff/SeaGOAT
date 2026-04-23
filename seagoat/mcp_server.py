from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from seagoat.mcp_tools.search import run_search_tool

mcp = FastMCP("SeaGOAT")


@mcp.tool()
def search(
    query: str,
    repo_path: str,
    max_results: int | None = None,
    context_above: int | None = None,
    context_below: int | None = None,
) -> dict:
    return run_search_tool(
        query=query,
        repo_path=repo_path,
        max_results=max_results,
        context_above=context_above,
        context_below=context_below,
    )


def main() -> None:
    mcp.run()
