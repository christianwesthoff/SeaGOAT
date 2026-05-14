from __future__ import annotations

from typing import Any

from seagoat.mcp_tools.grep import run_grep_tool
from seagoat.mcp_tools.read_file import run_read_file_tool
from seagoat.mcp_tools.research import (
    _build_grouped_results,
    _build_suggested_reads,
    _extract_evidence,
    _extract_line_range,
    expand_queries,
    extract_identifier_tokens,
)
from seagoat.mcp_tools.search import run_search_tool, validate_repo_path
from seagoat.mcp_tools.status import run_server_status_tool

DEFAULT_MAX_RESULTS_PER_QUERY = 5
DEFAULT_CONTEXT_ABOVE = 1
DEFAULT_CONTEXT_BELOW = 1
DEFAULT_MAX_FILES_TO_READ = 8
ALLOWED_REASONING_PLANS = {"query", "answer", "investigate"}
ALLOWED_READ_STRATEGIES = {"auto", "suggest-only"}
DEFINITION_PREFIXES = (
    "class ",
    "module ",
    "def ",
    "function ",
    "interface ",
    "struct ",
)


def _validate_reasoning_plan(reasoning_plan: str) -> str:
    if reasoning_plan not in ALLOWED_REASONING_PLANS:
        allowed = ", ".join(sorted(ALLOWED_REASONING_PLANS))
        raise ValueError(f"reasoning_plan must be one of: {allowed}")
    return reasoning_plan


def _validate_read_strategy(read_strategy: str) -> str:
    if read_strategy not in ALLOWED_READ_STRATEGIES:
        allowed = ", ".join(sorted(ALLOWED_READ_STRATEGIES))
        raise ValueError(f"read_strategy must be one of: {allowed}")
    return read_strategy


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


def _build_query_summaries(
    *,
    queries: list[str],
    exact_queries: list[str],
    repo_path: str,
    max_results_per_query: int,
    include_performance: bool,
    path_glob: str | None,
) -> tuple[list[dict[str, Any]], list[tuple[str, list[dict[str, Any]]]], bool]:
    query_summaries = []
    results_by_query = []
    server_status = run_server_status_tool(repo_path=repo_path)
    semantic_search_enabled = server_status["running"] and path_glob is None

    if path_glob is not None:
        skip_reason = "Semantic search skipped because path_glob scopes exact research only."
        for query in queries:
            query_summaries.append(
                {
                    "query": query,
                    "result_count": 0,
                    "skipped": True,
                    "reason": skip_reason,
                }
            )
    elif server_status["running"]:
        for query in queries:
            try:
                search_result = run_search_tool(
                    query=query,
                    repo_path=repo_path,
                    max_results=max_results_per_query,
                    context_above=DEFAULT_CONTEXT_ABOVE,
                    context_below=DEFAULT_CONTEXT_BELOW,
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
    else:
        skip_reason = server_status["summary"]
        for query in queries:
            query_summaries.append(
                {
                    "query": query,
                    "result_count": 0,
                    "skipped": True,
                    "reason": skip_reason,
                }
            )

    for exact_query in exact_queries:
        query_label = f"exact:{exact_query}"
        try:
            grep_result = run_grep_tool(
                repo_path=repo_path,
                pattern=exact_query,
                max_results=max_results_per_query,
                path_glob=path_glob,
            )
        except RuntimeError as exc:
            query_summaries.append(
                {
                    "query": query_label,
                    "result_count": 0,
                    "error": str(exc),
                }
            )
            continue

        results = grep_result.get("results", [])
        query_summaries.append(
            {
                "query": query_label,
                "result_count": len(results),
            }
        )
        results_by_query.append((query_label, results))

    return query_summaries, results_by_query, semantic_search_enabled


def _build_reason_evidence(
    grouped_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence = []
    for group in grouped_results:
        snippets = []
        for snippet in group.get("snippets", []):
            line_range = _extract_line_range(snippet)
            evidence_lines = _extract_evidence(snippet)
            if line_range is None or not evidence_lines:
                continue
            snippets.append(
                {
                    "start_line": line_range[0],
                    "end_line": line_range[1],
                    "lines": evidence_lines,
                }
            )

        matched_queries = group.get("matched_queries", [])
        reason = "Matched SeaGOAT reasoning queries."
        if matched_queries:
            reason = f"Matched {len(matched_queries)} queries: {', '.join(matched_queries)}."

        item = {
            "file_path": group["file_path"],
            "matched_queries": matched_queries,
            "result_count": group.get("result_count", 0),
            "why_it_matters": reason,
            "snippets": snippets,
        }
        if "full_path" in group:
            item["full_path"] = group["full_path"]
        evidence.append(item)

    return evidence


def _keyword_variants(token: str) -> set[str]:
    variants = {token.lower()}
    if len(token) > 4:
        variants.add(token[:-1].lower())
    if token.endswith("ed") and len(token) > 4:
        variants.add(token[:-2].lower())
        variants.add(token[:-1].lower())
    if token.endswith("ing") and len(token) > 5:
        variants.add(token[:-3].lower())
    return {variant for variant in variants if len(variant) >= 3}


def _extract_findings(
    *,
    question: str,
    exact_queries: list[str],
    read_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keywords = []
    for token in question.replace("?", " ").split():
        normalized = token.strip(".,;:!?()[]{}\"'")
        if len(normalized) >= 4:
            keywords.extend(_keyword_variants(normalized))

    findings = []
    for read_result in read_results:
        scored_lines = []
        for line in read_result["lines"]:
            text = line["text"].strip()
            lower_text = text.lower()
            score = 0
            for identifier in exact_queries:
                if identifier.lower() in lower_text:
                    score += 1
            for keyword in keywords:
                if keyword in lower_text:
                    score += 2
            if lower_text.startswith(DEFINITION_PREFIXES):
                score -= 2
            if score > 0:
                scored_lines.append((score, line["line"], text))

        if not scored_lines:
            continue

        scored_lines.sort(key=lambda item: (-item[0], item[1]))
        _, line_number, claim = scored_lines[0]
        findings.append(
            {
                "kind": "answer_candidate",
                "file_path": read_result["file_path"],
                "line": line_number,
                "claim": claim,
            }
        )

    return findings


def _build_reads(
    *,
    repo_path: str,
    suggested_reads: list[dict[str, Any]],
    reasoning_plan: str,
    read_strategy: str,
    max_files_to_read: int,
    context_above: int,
    context_below: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if read_strategy != "auto":
        return [], suggested_reads

    if reasoning_plan == "query":
        return [], suggested_reads

    files_to_read = 1 if reasoning_plan == "answer" else max_files_to_read
    read_results = []
    reads_performed = []
    read_keys = set()

    for suggestion in suggested_reads:
        if len(read_results) >= files_to_read:
            break
        read_key = suggestion["file_path"]
        if read_key in read_keys:
            continue
        read_keys.add(read_key)
        read_result = run_read_file_tool(
            repo_path=repo_path,
            file_path=suggestion["file_path"],
            start_line=max(1, suggestion["start_line"] - context_above),
            end_line=suggestion["end_line"] + context_below,
        )
        read_results.append(read_result)
        reads_performed.append(
            {
                "file_path": read_result["file_path"],
                "start_line": read_result["start_line"],
                "end_line": read_result["end_line"],
            }
        )

    remaining_suggestions = [
        suggestion
        for suggestion in suggested_reads
        if suggestion["file_path"] not in read_keys
    ]
    return read_results, remaining_suggestions


def _confidence_for(
    *, reasoning_plan: str, evidence_count: int, read_count: int, finding_count: int
) -> str:
    if reasoning_plan == "investigate" and read_count >= 2 and finding_count >= 2:
        return "high"
    if read_count >= 1 and finding_count >= 1:
        return "medium"
    if evidence_count >= 1:
        return "low"
    return "low"


def run_reason_tool(
    *,
    question: str,
    repo_path: str,
    reasoning_plan: str = "query",
    path_glob: str | None = None,
    max_results_per_query: int | None = None,
    read_strategy: str = "auto",
    max_files_to_read: int = DEFAULT_MAX_FILES_TO_READ,
    context_above: int = DEFAULT_CONTEXT_ABOVE,
    context_below: int = DEFAULT_CONTEXT_BELOW,
    include_performance: bool = False,
) -> dict[str, Any]:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must not be empty")

    normalized_repo_path = validate_repo_path(repo_path)
    validated_reasoning_plan = _validate_reasoning_plan(reasoning_plan)
    validated_read_strategy = _validate_read_strategy(read_strategy)
    if max_files_to_read < 1:
        raise ValueError("max_files_to_read must be greater than or equal to 1")
    if context_above < 0 or context_below < 0:
        raise ValueError("context_above and context_below must be greater than or equal to 0")

    queries = expand_queries(normalized_question)
    exact_queries = extract_identifier_tokens(normalized_question)
    bounded_max_results = (
        DEFAULT_MAX_RESULTS_PER_QUERY
        if max_results_per_query is None
        else max_results_per_query
    )
    if bounded_max_results < 1:
        raise ValueError("max_results_per_query must be greater than or equal to 1")

    query_summaries, results_by_query, semantic_search_enabled = _build_query_summaries(
        queries=queries,
        exact_queries=exact_queries,
        repo_path=normalized_repo_path,
        max_results_per_query=bounded_max_results,
        include_performance=include_performance,
        path_glob=path_glob,
    )
    grouped_results = _build_grouped_results(results_by_query)
    suggested_reads = _build_suggested_reads(results_by_query)
    evidence = _build_reason_evidence(grouped_results)

    effective_read_strategy = (
        "suggest-only"
        if validated_reasoning_plan == "query"
        else validated_read_strategy
    )
    read_results, suggested_next_reads = _build_reads(
        repo_path=normalized_repo_path,
        suggested_reads=suggested_reads,
        reasoning_plan=validated_reasoning_plan,
        read_strategy=effective_read_strategy,
        max_files_to_read=max_files_to_read,
        context_above=context_above,
        context_below=context_below,
    )
    findings = _extract_findings(
        question=normalized_question,
        exact_queries=exact_queries,
        read_results=read_results,
    )

    result = {
        "summary": (
            f"SeaGOAT reasoned about '{normalized_question}' with "
            f"{len(query_summaries)} queries, {len(evidence)} evidence files, "
            f"and {len(read_results)} file reads."
        ),
        "repo_path": normalized_repo_path,
        "question": normalized_question,
        "reasoning_plan": validated_reasoning_plan,
        "plan": {
            "subqueries": queries,
            "exact_queries": exact_queries,
            "semantic_search_enabled": semantic_search_enabled,
            "read_strategy": effective_read_strategy,
        },
        "queries": query_summaries,
        "evidence": evidence,
        "reads_performed": [
            {
                "file_path": read_result["file_path"],
                "start_line": read_result["start_line"],
                "end_line": read_result["end_line"],
            }
            for read_result in read_results
        ],
        "suggested_next_reads": suggested_next_reads,
        "findings": findings,
        "confidence": _confidence_for(
            reasoning_plan=validated_reasoning_plan,
            evidence_count=len(evidence),
            read_count=len(read_results),
            finding_count=len(findings),
        ),
    }
    if path_glob is not None:
        result["path_glob"] = path_glob
    return result
