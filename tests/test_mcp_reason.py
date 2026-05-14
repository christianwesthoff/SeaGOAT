import pytest

from seagoat.mcp_tools.reason import run_reason_tool


def search_result(path, *, full_path=None, lines=None):
    result = {
        "path": path,
        "blocks": [
            {
                "lines": lines
                or [
                    {"line": 20, "lineText": "class ExportWorker"},
                    {"line": 21, "lineText": "  queue_as :exports"},
                ]
            }
        ],
    }
    if full_path is not None:
        result["fullPath"] = full_path
    return result


def patch_search(mocker, responses):
    def fake_run_search_tool(**kwargs):
        query = kwargs["query"]
        response = responses.get(query, [])
        if isinstance(response, Exception):
            raise response
        return {"results": response}

    return mocker.patch(
        "seagoat.mcp_tools.reason.run_search_tool",
        side_effect=fake_run_search_tool,
    )


def patch_server_status(mocker, *, running=True, repo_path="/repo"):
    summary = (
        f"SeaGOAT server is running for '{repo_path}'."
        if running
        else f"No SeaGOAT server is running for '{repo_path}'."
    )
    return mocker.patch(
        "seagoat.mcp_tools.reason.run_server_status_tool",
        return_value={
            "summary": summary,
            "repo_path": str(repo_path),
            "running": running,
            "server_address": "http://localhost:1234" if running else None,
            "start_command": f"seagoat-server start {repo_path}",
        },
    )


def grep_result(path, *, full_path=None, line=12, text="class ExportWorker"):
    result = {
        "file_path": path,
        "line": line,
        "text": text,
    }
    if full_path is not None:
        result["full_path"] = full_path
    return result


def patch_grep(mocker, responses):
    def fake_run_grep_tool(**kwargs):
        pattern = kwargs["pattern"]
        return {"results": responses.get(pattern, [])}

    return mocker.patch(
        "seagoat.mcp_tools.reason.run_grep_tool",
        side_effect=fake_run_grep_tool,
    )


def test_run_reason_tool_rejects_invalid_reasoning_plan(tmp_path):
    with pytest.raises(ValueError, match="reasoning_plan must be one of"):
        run_reason_tool(
            question="Where is ExportWorker queued?",
            repo_path=str(tmp_path),
            reasoning_plan="unknown",
        )


def test_run_reason_tool_query_plan_returns_structured_evidence(tmp_path, mocker):
    patch_server_status(mocker, repo_path=tmp_path)
    patch_grep(
        mocker,
        {
            "ExportWorker": [
                grep_result(
                    "app/jobs/export_worker.rb",
                    full_path=f"{tmp_path}/app/jobs/export_worker.rb",
                    line=6,
                    text="class ExportWorker",
                )
            ]
        },
    )
    patch_search(
        mocker,
        {
            "Where is ExportWorker queued?": [
                search_result(
                    "app/jobs/export_worker.rb",
                    full_path=f"{tmp_path}/app/jobs/export_worker.rb",
                    lines=[
                        {"line": 6, "lineText": "class ExportWorker"},
                        {"line": 7, "lineText": "  queue_as :exports"},
                    ],
                )
            ]
        },
    )

    result = run_reason_tool(
        question="Where is ExportWorker queued?",
        repo_path=str(tmp_path),
        reasoning_plan="query",
    )

    assert result["reasoning_plan"] == "query"
    assert result["plan"] == {
        "subqueries": [
            "Where is ExportWorker queued?",
            "ExportWorker",
            "queued",
            "ExportWorker queued",
        ],
        "exact_queries": ["ExportWorker"],
        "semantic_search_enabled": True,
        "read_strategy": "suggest-only",
    }
    assert result["reads_performed"] == []
    assert result["findings"] == []
    assert result["evidence"][0]["file_path"] == "app/jobs/export_worker.rb"
    assert result["evidence"][0]["matched_queries"] == [
        "Where is ExportWorker queued?",
        "exact:ExportWorker",
    ]
    assert result["suggested_next_reads"][0]["file_path"] == "app/jobs/export_worker.rb"


def test_run_reason_tool_answer_plan_reads_top_files_and_extracts_findings(
    tmp_path, mocker
):
    worker_path = tmp_path / "app" / "jobs" / "export_worker.rb"
    worker_path.parent.mkdir(parents=True)
    worker_path.write_text(
        "class ExportWorker\n  queue_as :exports\nend\n", encoding="utf-8"
    )
    patch_server_status(mocker, repo_path=tmp_path)
    patch_grep(
        mocker,
        {
            "ExportWorker": [
                grep_result(
                    "app/jobs/export_worker.rb",
                    full_path=str(worker_path),
                    line=1,
                    text="class ExportWorker",
                )
            ]
        },
    )
    patch_search(
        mocker,
        {
            "Where is ExportWorker queued?": [
                search_result(
                    "app/jobs/export_worker.rb",
                    full_path=str(worker_path),
                    lines=[
                        {"line": 1, "lineText": "class ExportWorker"},
                        {"line": 2, "lineText": "  queue_as :exports"},
                    ],
                )
            ]
        },
    )

    result = run_reason_tool(
        question="Where is ExportWorker queued?",
        repo_path=str(tmp_path),
        reasoning_plan="answer",
    )

    assert result["reads_performed"] == [
        {
            "file_path": "app/jobs/export_worker.rb",
            "start_line": 1,
            "end_line": 3,
        }
    ]
    assert result["findings"] == [
        {
            "kind": "answer_candidate",
            "file_path": "app/jobs/export_worker.rb",
            "line": 2,
            "claim": "queue_as :exports",
        }
    ]
    assert result["confidence"] == "medium"


def test_run_reason_tool_investigate_plan_reads_multiple_files_and_limits_reads(
    tmp_path, mocker
):
    worker_path = tmp_path / "app" / "jobs" / "export_worker.rb"
    service_path = tmp_path / "app" / "services" / "export_launcher.rb"
    worker_path.parent.mkdir(parents=True)
    service_path.parent.mkdir(parents=True)
    worker_path.write_text(
        "class ExportWorker\n  queue_as :exports\nend\n", encoding="utf-8"
    )
    service_path.write_text(
        "class ExportLauncher\n  def call\n    ExportWorker.perform_async\n  end\nend\n",
        encoding="utf-8",
    )
    patch_server_status(mocker, repo_path=tmp_path)
    patch_grep(
        mocker,
        {
            "ExportWorker": [
                grep_result(
                    "app/jobs/export_worker.rb",
                    full_path=str(worker_path),
                    line=1,
                    text="class ExportWorker",
                )
            ]
        },
    )
    patch_search(
        mocker,
        {
            "Where is ExportWorker queued?": [
                search_result(
                    "app/jobs/export_worker.rb",
                    full_path=str(worker_path),
                    lines=[
                        {"line": 1, "lineText": "class ExportWorker"},
                        {"line": 2, "lineText": "  queue_as :exports"},
                    ],
                )
            ],
            "ExportWorker": [
                search_result(
                    "app/services/export_launcher.rb",
                    full_path=str(service_path),
                    lines=[
                        {"line": 3, "lineText": "    ExportWorker.perform_async"},
                    ],
                )
            ],
        },
    )

    result = run_reason_tool(
        question="Where is ExportWorker queued?",
        repo_path=str(tmp_path),
        reasoning_plan="investigate",
        max_files_to_read=2,
    )

    assert result["reads_performed"] == [
        {
            "file_path": "app/jobs/export_worker.rb",
            "start_line": 1,
            "end_line": 3,
        },
        {
            "file_path": "app/services/export_launcher.rb",
            "start_line": 2,
            "end_line": 4,
        },
    ]
    assert result["suggested_next_reads"] == []
    assert result["findings"] == [
        {
            "kind": "answer_candidate",
            "file_path": "app/jobs/export_worker.rb",
            "line": 2,
            "claim": "queue_as :exports",
        },
        {
            "kind": "answer_candidate",
            "file_path": "app/services/export_launcher.rb",
            "line": 3,
            "claim": "ExportWorker.perform_async",
        },
    ]
    assert result["confidence"] == "high"
