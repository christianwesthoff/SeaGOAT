import pytest

from seagoat.cli import cli
from seagoat.mcp_tools.search import build_summary, run_search_tool, validate_repo_path
from seagoat.utils.server import ServerDoesNotExist


def test_validate_repo_path_rejects_missing_directory(tmp_path):
    missing = tmp_path / "missing-repo"

    with pytest.raises(FileNotFoundError):
        validate_repo_path(str(missing))


def test_build_summary_uses_query_repo_and_result_count():
    summary = build_summary(
        query="round numbers",
        repo_path="/tmp/repo",
        result_count=3,
    )

    assert (
        summary
        == "SeaGOAT searched '/tmp/repo' for 'round numbers' and returned 3 results."
    )


def test_validate_repo_path_rejects_file_path(tmp_path):
    file_path = tmp_path / "repo.txt"
    file_path.write_text("not a directory")

    with pytest.raises(NotADirectoryError):
        validate_repo_path(str(file_path))


def test_run_search_tool_rejects_empty_query(tmp_path):
    with pytest.raises(ValueError, match="query must not be empty"):
        run_search_tool(query="   ", repo_path=str(tmp_path))


def test_run_search_tool_translates_missing_server_to_runtime_error(
    tmp_path, mocker
):
    mocker.patch(
        "seagoat.mcp_tools.search.search_repo",
        side_effect=ServerDoesNotExist(),
    )

    with pytest.raises(
        RuntimeError,
        match=f"No SeaGOAT server is running for '{tmp_path}'. Start it with: seagoat-server start {tmp_path}",
    ):
        run_search_tool(query="Markdown", repo_path=str(tmp_path))


def test_run_search_tool_forwards_default_context_values(tmp_path, mocker):
    mocked_search_repo = mocker.patch(
        "seagoat.mcp_tools.search.search_repo",
        return_value={
            "server_address": "http://localhost:31337",
            "results": [{"path": "file1.md"}],
        },
    )

    result = run_search_tool(query="  Markdown  ", repo_path=str(tmp_path))

    mocked_search_repo.assert_called_once_with(
        query="Markdown",
        repo_path=str(tmp_path),
        max_results=None,
        context_above=3,
        context_below=3,
    )
    assert result["summary"] == (
        f"SeaGOAT searched '{tmp_path}' for 'Markdown' and returned 1 result."
    )
    assert result["repo_path"] == str(tmp_path)
    assert result["server_address"] == "http://localhost:31337"
    assert result["result_count"] == 1
    assert result["results"] == [{"path": "file1.md"}]


def test_mcp_server_subcommand_imports_real_module_and_calls_main(runner, mocker):
    mocked_main = mocker.patch("seagoat.mcp_server.main", return_value=0)

    result = runner.invoke(cli, ["mcp-server"])

    assert result.exit_code == 0
    mocked_main.assert_called_once_with()
