import pytest

from seagoat.mcp_tools.research import run_research_tool


def search_result(path, *, full_path=None, lines=None):
    result = {
        "path": path,
        "blocks": [
            {
                "lines": lines
                or [
                    {"line": 20, "lineText": "class ExportWorker"},
                    {"line": 21, "lineText": "  def perform"},
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
        "seagoat.mcp_tools.research.run_search_tool",
        side_effect=fake_run_search_tool,
    )


def test_run_research_tool_rejects_empty_question(tmp_path):
    with pytest.raises(ValueError, match="question must not be empty"):
        run_research_tool(question="   ", repo_path=str(tmp_path))


def test_run_research_tool_expands_queries_transparently(tmp_path, mocker):
    mocked_search = patch_search(mocker, {})

    result = run_research_tool(
        question="How is publishing exported to portal?",
        repo_path=str(tmp_path),
    )

    queries = [query["query"] for query in result["queries"]]
    assert queries == [
        "How is publishing exported to portal?",
        "publishing",
        "exported",
        "portal",
        "publishing exported",
        "exported portal",
    ]
    assert [call.kwargs["query"] for call in mocked_search.call_args_list] == queries
    assert {
        "max_results": 5,
        "context_above": 1,
        "context_below": 1,
        "include_performance": False,
    }.items() <= mocked_search.call_args.kwargs.items()


def test_run_research_tool_groups_results_by_file(tmp_path, mocker):
    patch_search(
        mocker,
        {
            "publishing worker queue": [
                search_result(
                    "app/workers/property_export_worker.rb",
                    full_path=f"{tmp_path}/app/workers/property_export_worker.rb",
                )
            ],
            "worker": [
                search_result("app/workers/property_export_worker.rb")
            ],
            "queue": [search_result("config/sidekiq.yml")],
        },
    )

    result = run_research_tool(
        question="publishing worker queue",
        repo_path=str(tmp_path),
        max_results_per_query=2,
    )

    grouped_results = result["grouped_results"]
    assert grouped_results[0]["file_path"] == "app/workers/property_export_worker.rb"
    assert grouped_results[0]["full_path"] == (
        f"{tmp_path}/app/workers/property_export_worker.rb"
    )
    assert grouped_results[0]["matched_queries"] == [
        "publishing worker queue",
        "worker",
    ]
    assert grouped_results[0]["result_count"] == 2
    assert len(grouped_results[0]["snippets"]) == 2
    assert grouped_results[1]["file_path"] == "config/sidekiq.yml"


def test_run_research_tool_suggests_bounded_reads_from_result_blocks(
    tmp_path, mocker
):
    patch_search(
        mocker,
        {
            "lead email tests": [
                search_result(
                    f"app/services/leadfisher/{index}.rb",
                    lines=[
                        {"line": index * 10, "lineText": "match"},
                        {"line": index * 10 + 1, "lineText": "context"},
                    ],
                )
                for index in range(1, 13)
            ]
        },
    )

    result = run_research_tool(
        question="lead email tests",
        repo_path=str(tmp_path),
    )

    assert len(result["suggested_reads"]) == 10
    assert result["suggested_reads"][0] == {
        "file_path": "app/services/leadfisher/1.rb",
        "start_line": 10,
        "end_line": 11,
        "reason": "Verify lead email tests match in app/services/leadfisher/1.rb.",
        "evidence": {
            "query": "lead email tests",
            "lines": [
                {"line": 10, "text": "match"},
                {"line": 11, "text": "context"},
            ],
        },
    }


def test_run_research_tool_rejects_invalid_max_results_per_query(tmp_path):
    with pytest.raises(
        ValueError,
        match="max_results_per_query must be greater than or equal to 1",
    ):
        run_research_tool(
            question="frontend worker",
            repo_path=str(tmp_path),
            max_results_per_query=0,
        )


def test_run_research_tool_keeps_query_errors_with_partial_results(
    tmp_path, mocker
):
    patch_search(
        mocker,
        {
            "frontend worker": [search_result("app/javascript/button_controller.ts")],
            "worker": RuntimeError("server not ready"),
        },
    )

    result = run_research_tool(
        question="frontend worker",
        repo_path=str(tmp_path),
    )

    worker_query = next(query for query in result["queries"] if query["query"] == "worker")
    assert worker_query == {
        "query": "worker",
        "result_count": 0,
        "error": "server not ready",
    }
    assert result["grouped_results"][0]["file_path"] == (
        "app/javascript/button_controller.ts"
    )
