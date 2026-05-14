import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from subprocess import Popen, TimeoutExpired

import pytest
import requests
import orjson
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from seagoat.cli import cli
from seagoat.mcp_tools.read_file import run_read_file_tool
from seagoat.mcp_tools.reason import run_reason_tool
from seagoat.mcp_tools.search import build_summary, run_search_tool, validate_repo_path
from seagoat.utils.server import ServerDoesNotExist, get_server_info
from seagoat.utils.wait import wait_for


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


def test_run_search_tool_translates_timeout_to_runtime_error(tmp_path, mocker):
    mocker.patch(
        "seagoat.mcp_tools.search.search_repo",
        side_effect=requests.exceptions.Timeout(),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "SeaGOAT search timed out after 20 seconds for "
            f"'{tmp_path}' while searching for 'Markdown'"
        ),
    ):
        run_search_tool(query="Markdown", repo_path=str(tmp_path))


def test_run_search_tool_forwards_mcp_default_values(tmp_path, mocker):
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
        max_results=20,
        context_above=1,
        context_below=1,
        request_timeout=20,
    )
    assert result["summary"] == (
        f"SeaGOAT searched '{tmp_path}' for 'Markdown' and returned 1 result."
    )
    assert result["repo_path"] == str(tmp_path)
    assert result["server_address"] == "http://localhost:31337"
    assert result["result_count"] == 1
    assert result["results"] == [{"path": "file1.md"}]


def test_run_search_tool_preserves_explicit_search_values(tmp_path, mocker):
    mocked_search_repo = mocker.patch(
        "seagoat.mcp_tools.search.search_repo",
        return_value={
            "server_address": "http://localhost:31337",
            "results": [],
        },
    )

    run_search_tool(
        query="Markdown",
        repo_path=str(tmp_path),
        max_results=7,
        context_above=2,
        context_below=4,
    )

    mocked_search_repo.assert_called_once_with(
        query="Markdown",
        repo_path=str(tmp_path),
        max_results=7,
        context_above=2,
        context_below=4,
        request_timeout=20,
    )


def test_run_search_tool_forwards_include_performance(tmp_path, mocker):
    mocked_search_repo = mocker.patch(
        "seagoat.mcp_tools.search.search_repo",
        return_value={
            "server_address": "http://localhost:31337",
            "results": [],
            "performance": {"totalMilliseconds": 12.3},
        },
    )

    result = run_search_tool(
        query="Markdown",
        repo_path=str(tmp_path),
        include_performance=True,
    )

    mocked_search_repo.assert_called_once_with(
        query="Markdown",
        repo_path=str(tmp_path),
        max_results=20,
        context_above=1,
        context_below=1,
        request_timeout=20,
        include_performance=True,
    )
    assert result["performance"] == {"totalMilliseconds": 12.3}


def test_run_read_file_tool_returns_bounded_line_range(tmp_path):
    file_path = tmp_path / "app" / "models" / "publishing.rb"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("first\nsecond\nthird\nfourth\n", encoding="utf-8")

    result = run_read_file_tool(
        repo_path=str(tmp_path),
        file_path="app/models/publishing.rb",
        start_line=2,
        end_line=3,
    )

    assert result == {
        "summary": (
            f"SeaGOAT read lines 2-3 from '{tmp_path}/app/models/publishing.rb'."
        ),
        "repo_path": str(tmp_path),
        "file_path": "app/models/publishing.rb",
        "full_path": str(file_path),
        "start_line": 2,
        "end_line": 3,
        "total_lines": 4,
        "truncated": False,
        "lines": [
            {"line": 2, "text": "second"},
            {"line": 3, "text": "third"},
        ],
    }


def test_run_read_file_tool_rejects_paths_outside_repo(tmp_path):
    outside_file = tmp_path.parent / "outside.rb"
    outside_file.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="file_path must stay inside repo_path"):
        run_read_file_tool(
            repo_path=str(tmp_path),
            file_path=str(outside_file),
        )


def test_run_read_file_tool_rejects_start_line_after_eof(tmp_path):
    file_path = tmp_path / "short.md"
    file_path.write_text("one\ntwo\n", encoding="utf-8")

    with pytest.raises(ValueError, match="start_line must not exceed total file lines"):
        run_read_file_tool(
            repo_path=str(tmp_path),
            file_path="short.md",
            start_line=3,
        )


def test_run_reason_tool_rejects_invalid_read_strategy(tmp_path):
    with pytest.raises(ValueError, match="read_strategy must be one of"):
        run_reason_tool(
            question="Where is ExportWorker queued?",
            repo_path=str(tmp_path),
            read_strategy="never",
        )


def test_mcp_server_subcommand_imports_real_module_and_calls_main(runner, mocker):
    mocked_main = mocker.patch("seagoat.mcp_server.main", return_value=0)

    result = runner.invoke(cli, ["mcp-server"])

    assert result.exit_code == 0
    mocked_main.assert_called_once_with()


@contextmanager
def running_seagoat_server(repo_path: str):
    original_home = os.environ.get("HOME")
    original_xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    process = None

    with tempfile.TemporaryDirectory() as temp_home:
        os.environ["HOME"] = temp_home
        os.environ["XDG_CACHE_HOME"] = temp_home

        try:
            process = Popen(
                [sys.executable, "-m", "seagoat.server", "start", repo_path],
                cwd=Path(__file__).resolve().parents[1],
                env=os.environ.copy(),
            )

            def server_info_exists():
                try:
                    get_server_info(repo_path)
                except ServerDoesNotExist:
                    return False
                return True

            wait_for(server_info_exists, timeout=5.0)
            server_address = get_server_info(repo_path)["address"]

            def server_is_ready():
                try:
                    return requests.get(f"{server_address}/status", timeout=5).ok
                except requests.RequestException:
                    return False

            wait_for(server_is_ready, timeout=10.0)

            yield server_address
        finally:
            if original_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = original_home
            if original_xdg_cache_home is None:
                os.environ.pop("XDG_CACHE_HOME", None)
            else:
                os.environ["XDG_CACHE_HOME"] = original_xdg_cache_home

            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def stdio_server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "seagoat.cli", "mcp-server"],
        env=os.environ.copy(),
        cwd=Path(__file__).resolve().parents[1],
    )


@pytest.mark.anyio
async def test_mcp_stdio_lists_tools_with_required_schemas():
    async with stdio_client(stdio_server_params()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()

    tools_by_name = {tool.name: tool for tool in tools.tools}
    assert {
        "search",
        "read_file",
        "grep",
        "research",
        "reason",
        "server_status",
    }.issubset(
        tools_by_name
    )
    assert set(tools_by_name["search"].inputSchema["required"]) == {
        "query",
        "repo_path",
    }
    assert set(tools_by_name["read_file"].inputSchema["required"]) == {
        "repo_path",
        "file_path",
    }
    assert set(tools_by_name["grep"].inputSchema["required"]) == {
        "repo_path",
        "pattern",
    }
    grep_properties = tools_by_name["grep"].inputSchema["properties"]
    assert "path_glob" in grep_properties
    assert "timeout_seconds" in grep_properties
    assert set(tools_by_name["research"].inputSchema["required"]) == {
        "question",
        "repo_path",
    }
    research_properties = tools_by_name["research"].inputSchema["properties"]
    assert "path_glob" in research_properties
    assert "max_results_per_query" in research_properties
    assert "include_performance" in research_properties
    assert "path_glob" in tools_by_name["research"].outputSchema["properties"]
    assert set(tools_by_name["reason"].inputSchema["required"]) == {
        "question",
        "repo_path",
    }
    reason_properties = tools_by_name["reason"].inputSchema["properties"]
    assert "reasoning_plan" in reason_properties
    assert "read_strategy" in reason_properties
    assert "max_files_to_read" in reason_properties
    assert "path_glob" in reason_properties
    assert set(tools_by_name["server_status"].inputSchema["required"]) == {
        "repo_path",
    }


@pytest.mark.anyio
@pytest.mark.skip(
    reason=(
        "Real stdio search starts a SeaGOAT server and can hang during "
        "Chroma/model cold-start; run manually when validating end-to-end search."
    )
)
async def test_search_tool_over_stdio(repo):
    with running_seagoat_server(repo.working_dir) as server:
        async with stdio_client(stdio_server_params()) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                result = await session.call_tool(
                    "search",
                    {
                        "query": "Markdown",
                        "repo_path": repo.working_dir,
                    },
                )

    assert result.isError is False
    assert result.structuredContent is not None
    assert len(result.content) == 1

    payload = orjson.loads(result.content[0].text)

    assert result.structuredContent["repo_path"] == str(
        Path(repo.working_dir).resolve()
    )
    assert result.structuredContent["server_address"] == server
    assert result.structuredContent["result_count"] >= 1
    assert result.structuredContent["summary"] == build_summary(
        query="Markdown",
        repo_path=str(Path(repo.working_dir).resolve()),
        result_count=result.structuredContent["result_count"],
    )
    assert payload == result.structuredContent


@pytest.mark.anyio
async def test_read_file_tool_over_stdio(repo):
    async with stdio_client(stdio_server_params()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                "read_file",
                {
                    "repo_path": repo.working_dir,
                    "file_path": "file1.md",
                    "start_line": 1,
                    "end_line": 2,
                },
            )

    assert result.isError is False
    assert result.structuredContent is not None
    assert result.structuredContent["file_path"] == "file1.md"
    assert result.structuredContent["start_line"] == 1
    assert result.structuredContent["end_line"] == 2
    assert [line["line"] for line in result.structuredContent["lines"]] == [1, 2]


@pytest.mark.anyio
async def test_search_tool_over_stdio_reports_missing_repo_server(repo):
    async with stdio_client(stdio_server_params()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                "search",
                {
                    "query": "Markdown",
                    "repo_path": repo.working_dir,
                },
            )

    assert result.isError is True
    assert result.structuredContent is None
    assert len(result.content) == 1
    assert "No SeaGOAT server is running for" in result.content[0].text
    assert "seagoat-server start" in result.content[0].text
