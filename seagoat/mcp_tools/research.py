from __future__ import annotations

import re
from typing import Any

from seagoat.mcp_tools.search import run_search_tool, validate_repo_path

DEFAULT_MAX_RESULTS_PER_QUERY = 5
MAX_SNIPPETS_PER_FILE = 3
MAX_SUGGESTED_READS = 10
MAX_EXPANDED_QUERIES = 8
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_:/.-]+")
STOP_WORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "any",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "how",
    "into",
    "need",
    "our",
    "please",
    "should",
    "that",
    "the",
    "their",
    "them",
    "this",
    "through",
    "what",
    "when",
    "where",
    "with",
    "would",
}


def expand_queries(question: str) -> list[str]:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must not be empty")

    queries = [normalized_question]
    tokens = [
        token
        for token in TOKEN_PATTERN.findall(normalized_question)
        if len(token) >= 3 and token.lower() not in STOP_WORDS
    ]

    queries.extend(tokens)
    queries.extend(
        f"{left} {right}"
        for left, right in zip(tokens, tokens[1:], strict=False)
        if left.lower() != right.lower()
    )

    return list(dict.fromkeys(queries))[:MAX_EXPANDED_QUERIES]


def _result_file_path(result: dict[str, Any]) -> str | None:
    file_path = result.get("file_path") or result.get("path")
    if file_path is None:
        return None
    return str(file_path)


def _result_full_path(result: dict[str, Any]) -> str | None:
    full_path = result.get("full_path") or result.get("fullPath")
    if full_path is None:
        return None
    return str(full_path)


def _extract_line_range(result: dict[str, Any]) -> tuple[int, int] | None:
    blocks = result.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            lines = block.get("lines") if isinstance(block, dict) else None
            if not isinstance(lines, list):
                continue

            line_numbers = [
                line["line"]
                for line in lines
                if isinstance(line, dict) and isinstance(line.get("line"), int)
            ]
            if line_numbers:
                return min(line_numbers), max(line_numbers)

    start_line = result.get("start_line")
    end_line = result.get("end_line")
    if isinstance(start_line, int) and isinstance(end_line, int):
        return start_line, end_line

    line = result.get("line")
    if isinstance(line, int):
        return line, line

    return None


def _extract_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = result.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            lines = block.get("lines") if isinstance(block, dict) else None
            if not isinstance(lines, list):
                continue

            evidence = []
            for line in lines:
                if not isinstance(line, dict) or not isinstance(line.get("line"), int):
                    continue

                text = (
                    line.get("lineText")
                    or line.get("text")
                    or line.get("content")
                    or ""
                )
                evidence.append({"line": line["line"], "text": str(text)})

            if evidence:
                return evidence

    line = result.get("line")
    if isinstance(line, int):
        return [{"line": line, "text": str(result.get("text", ""))}]

    return []


def _build_grouped_results(
    results_by_query: list[tuple[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    for query, results in results_by_query:
        for result in results:
            file_path = _result_file_path(result)
            if file_path is None:
                continue

            group = groups.setdefault(
                file_path,
                {
                    "file_path": file_path,
                    "matched_queries": [],
                    "result_count": 0,
                    "snippets": [],
                },
            )

            full_path = _result_full_path(result)
            if full_path is not None and "full_path" not in group:
                group["full_path"] = full_path

            if query not in group["matched_queries"]:
                group["matched_queries"].append(query)
            group["result_count"] += 1
            if len(group["snippets"]) < MAX_SNIPPETS_PER_FILE:
                group["snippets"].append(result)

    return list(groups.values())


def _build_suggested_reads(
    results_by_query: list[tuple[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    suggested_reads = []
    seen_ranges = set()

    for query, results in results_by_query:
        for result in results:
            if len(suggested_reads) >= MAX_SUGGESTED_READS:
                return suggested_reads

            file_path = _result_file_path(result)
            line_range = _extract_line_range(result)
            if file_path is None or line_range is None:
                continue

            start_line, end_line = line_range
            read_key = (file_path, start_line, end_line)
            if read_key in seen_ranges:
                continue

            seen_ranges.add(read_key)
            suggested_reads.append(
                {
                    "file_path": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "reason": f"Verify {query} match in {file_path}.",
                    "evidence": {
                        "query": query,
                        "lines": _extract_evidence(result),
                    },
                }
            )

    return suggested_reads


def run_research_tool(
    *,
    question: str,
    repo_path: str,
    max_results_per_query: int | None = None,
    include_performance: bool = False,
) -> dict[str, Any]:
    queries = expand_queries(question)
    normalized_repo_path = validate_repo_path(repo_path)
    bounded_max_results = (
        DEFAULT_MAX_RESULTS_PER_QUERY
        if max_results_per_query is None
        else max_results_per_query
    )
    if bounded_max_results < 1:
        raise ValueError("max_results_per_query must be greater than or equal to 1")

    query_summaries = []
    results_by_query = []

    for query in queries:
        try:
            search_result = run_search_tool(
                query=query,
                repo_path=normalized_repo_path,
                max_results=bounded_max_results,
                context_above=1,
                context_below=1,
                include_performance=include_performance,
            )
        except RuntimeError as exc:
            query_summaries.append(
                {
                    "query": query,
                    "result_count": 0,
                    "error": str(exc),
                }
            )
            continue

        results = search_result.get("results", [])
        query_summaries.append(
            {
                "query": query,
                "result_count": len(results),
            }
        )
        results_by_query.append((query, results))

    grouped_results = _build_grouped_results(results_by_query)
    suggested_reads = _build_suggested_reads(results_by_query)
    file_count = len(grouped_results)
    query_count = len(queries)

    return {
        "summary": (
            f"SeaGOAT researched '{queries[0]}' across {query_count} queries "
            f"and found matches in {file_count} files."
        ),
        "repo_path": normalized_repo_path,
        "question": queries[0],
        "queries": query_summaries,
        "grouped_results": grouped_results,
        "suggested_reads": suggested_reads,
    }
