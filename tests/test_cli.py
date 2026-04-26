import os
import shutil
import tempfile
from pathlib import Path
from typing import List

import orjson
import pytest
import requests
from click.testing import CliRunner

from seagoat import __version__
from seagoat.cli import cli, seagoat, warn_if_update_available
from seagoat.utils.cli_display import is_bat_installed
from seagoat.utils.server import update_server_info
from tests.conftest import MagicMock


@pytest.fixture
def real_bat():
    return


@pytest.fixture
def lots_of_fake_results(mocker):
    mock_results = {
        "results": [
            {
                "blocks": [
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 9,
                                "lineText": "* feat: only display full code blocks in result ([`e2767f9`](https://github.com/kantord/SeaGOAT/commit/e2767f98ece3023e01ec4a6d95cd14701b11f842))",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 24,
                                "lineText": "* refactor: group continuous lines into blocks ([`6a15673`](https://github.com/kantord/SeaGOAT/commit/6a15673e27bf906f8aca4e7eb000a8e24ba56acf))",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                ],
                "fullPath": "/home/kantord/repos/SeaGOAT/CHANGELOG.md",
                "path": "CHANGELOG.md",
            },
            {
                "blocks": [
                    {
                        "lineTypeCount": {"result": 2},
                        "lines": [
                            {
                                "line": 240,
                                "lineText": '                    print("Server responded with a 500 error:")',
                                "resultTypes": ["result"],
                            },
                            {
                                "line": 241,
                                "lineText": "                    print(response.text)",
                                "resultTypes": ["result"],
                            },
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 2},
                        "lines": [
                            {
                                "line": 283,
                                "lineText": "    def _mock_results(results_template):",
                                "resultTypes": ["result"],
                            },
                            {
                                "line": 284,
                                "lineText": "        results = []",
                                "resultTypes": ["result"],
                            },
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 2},
                        "lines": [
                            {
                                "line": 287,
                                "lineText": "        for filename, lines in results_template:",
                                "resultTypes": ["result"],
                            },
                            {
                                "line": 288,
                                "lineText": "            for i, line_text in enumerate(lines):",
                                "resultTypes": ["result"],
                            },
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 291,
                                "lineText": "        for filename, lines in fake_files.items():",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 295,
                                "lineText": "                lines_sorted_by_line_number = sorted(lines.items(), key=lambda x: x[0])",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 297,
                                "lineText": "                    [line for _, line in lines_sorted_by_line_number]",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 2},
                        "lines": [
                            {
                                "line": 301,
                                "lineText": "        for filename, lines in results_template:",
                                "resultTypes": ["result"],
                            },
                            {
                                "line": 302,
                                "lineText": "            result = {",
                                "resultTypes": ["result"],
                            },
                        ],
                    },
                ],
                "fullPath": "/home/kantord/repos/SeaGOAT/tests/conftest.py",
                "path": "tests/conftest.py",
            },
            {
                "blocks": [
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 43,
                                "lineText": '        results = current_app.extensions["task_queue"].enqueue_high_prio(',
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 51,
                                "lineText": "        for result in results:",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 53,
                                "lineText": "                result.add_context_lines(-int(context_above))",
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                    {
                        "lineTypeCount": {"result": 1},
                        "lines": [
                            {
                                "line": 56,
                                "lineText": '            "results": [result.to_json(query) for result in results],',
                                "resultTypes": ["result"],
                            }
                        ],
                    },
                ],
                "fullPath": "/home/kantord/repos/SeaGOAT/seagoat/server.py",
                "path": "seagoat/server.py",
            },
        ],
        "version": "0.18.0",
    }

    mock_response = MagicMock()
    mock_response.text = orjson.dumps(mock_results)
    mocker.patch("requests.post", return_value=mock_response)

    return mock_results


@pytest.fixture(name="get_request_args_from_cli_call")
def get_request_args_from_cli_call_(mock_server_factory, mocker, runner, repo):
    def _run_cli(cli_args: List[str]):
        mock_server_factory(
            [
                ["hello.txt", ["foo", "bar", "baz"]],
                ["foobar.py", ["def hello():", "    print('world')"]],
                ["foobar2.py", ["def hola():", "    print('mundo')"]],
                ["foobar3.py", ["def bonjour():", "    print('monde')"]],
                ["foobar.fake", ["fn hello()", "    echo('world')"]],
                ["foobar2.fake", ["fn hola()", "    echo('mundo')"]],
                ["foobar3.fake", ["fn bonjour()", "    echo('monde')"]],
            ],
            manually_mock_request=True,
        )

        request_args = {}

        def fake_requests(*args, **kwargs):
            mock_response = mocker.Mock()
            mock_response.text = orjson.dumps(
                {"results": [], "version": __version__}
            )

            request_args["url"] = args[0]
            request_args["json"] = kwargs.get("json", {})

            return mock_response

        mocked_requests_post = mocker.patch(
            "seagoat.query_service.requests.post", side_effect=fake_requests
        )
        mocker.patch(
            "seagoat.query_service.get_server_info",
            return_value={"address": "http://localhost:31337"},
        )
        query = "JavaScript"
        result = runner.invoke(
            seagoat,
            [query, repo.working_dir, "--no-color", *cli_args],
        )
        assert result.exit_code == 0
        mocked_requests_post.assert_called_once()

        return request_args

    return _run_cli


@pytest.fixture(name="mock_response")
def mock_response_(mocker):
    def _mock_response(json_data, status_code=200):
        mock_resp = mocker.Mock(spec=requests.Response)
        mock_resp.status_code = status_code
        mock_resp.text = orjson.dumps(json_data)
        return mock_resp

    return _mock_response


@pytest.fixture
def mock_accuracy_warning(mocker):
    def _noop(*args, **kwargs):
        pass

    mocker.patch("seagoat.cli.display_accuracy_warning", _noop)


@pytest.fixture
def mock_query_server(mocker):
    def _mocked_query_server(*args, **kwargs):
        return []

    mocker.patch("seagoat.cli.query_server", _mocked_query_server)


@pytest.mark.usefixtures("mock_query_server")
@pytest.mark.parametrize("accuracy_percentage", [50, 75, 99, 100])
def test_seagoat_warns_on_incomplete_accuracy(
    accuracy_percentage,
    runner_with_error,
    mocker,
    mock_response,
):
    mock_status_response = {
        "stats": {
            "chunks": {"analyzed": 100, "unanalyzed": 0},
            "queue": {"size": 0},
            "accuracy": {"percentage": accuracy_percentage},
        },
        "version": __version__,
    }

    mocker.patch("requests.get", return_value=mock_response(mock_status_response))
    mocker.patch("seagoat.cli.get_server_info", return_value={"address": ""})

    query = "some random query"
    result = runner_with_error.invoke(seagoat, [query, "--no-color"])

    if accuracy_percentage < 100:
        assert (
            "Warning: SeaGOAT is still analyzing your repository. "
            + f"The results displayed have an estimated accuracy of {accuracy_percentage}%"
            in result.stderr
        )
    else:
        assert "Warning" not in result.stderr


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize("max_length", [1, 2, 10])
def test_forwards_limit_clue_to_server(max_length, get_request_args_from_cli_call):
    request_args = get_request_args_from_cli_call(["--max-results", str(max_length)])
    assert request_args["json"]["limitClue"] == max_length


@pytest.mark.usefixtures("mock_accuracy_warning")
def test_forwards_performance_to_server(get_request_args_from_cli_call):
    request_args = get_request_args_from_cli_call(["--performance"])

    assert request_args["json"]["includePerformance"] is True


@pytest.mark.usefixtures("mock_accuracy_warning")
def test_displays_performance_when_requested(
    mock_server_factory, mocker, repo, runner
):
    mock_server_factory(
        [["hello.txt", ["foo"]]],
        manually_mock_request=True,
    )
    mocker.patch(
        "seagoat.query_service.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )
    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [],
            "version": __version__,
            "performance": {
                "queueWaitMilliseconds": 1.2,
                "serializationMilliseconds": 3.4,
                "totalMilliseconds": 56.7,
                "engine": {
                    "totalMilliseconds": 52.1,
                    "sources": {
                        "chroma": 40.0,
                        "ripgrep": 10.0,
                    },
                    "contextMilliseconds": 1.0,
                    "formatMilliseconds": 1.1,
                },
            },
        }
    )
    mock_response.raise_for_status.return_value = None
    mocker.patch("seagoat.query_service.requests.post", return_value=mock_response)

    result = runner.invoke(
        seagoat,
        ["JavaScript", repo.working_dir, "--no-color", "--performance"],
    )

    assert result.exit_code == 0
    assert "Performance:" in result.output
    assert "total: 56.7 ms" in result.output
    assert "chroma: 40.0 ms" in result.output
    assert "ripgrep: 10.0 ms" in result.output


@pytest.mark.usefixtures("server", "mock_accuracy_warning")
def test_integration_test_without_color(snapshot, repo, mocker, runner, temporary_cd):
    mocker.patch("os.isatty", return_value=True)
    query = "JavaScript"
    with temporary_cd(repo.working_dir):
        result = runner.invoke(seagoat, [query, ".", "--no-color"])

    assert str(result.output) == snapshot
    assert result.exit_code == 0


@pytest.mark.usefixtures("server", "mock_accuracy_warning")
def test_integration_test_vimgrep_mode(snapshot, repo, mocker, runner, temporary_cd):
    mocker.patch("os.isatty", return_value=True)
    query = "JavaScript"
    with temporary_cd(repo.working_dir):
        result = runner.invoke(seagoat, [query, ".", "--vimgrep"])

    assert str(result.output) == snapshot
    assert result.exit_code == 0


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize(
    "max_length, command_option, expected_length",
    [
        (20, "-l", 20),
        (0, "-l", 3),
        (1, "--max-results", 3),
        (3, "--max-results", 3),
        (4, "--max-results", 5),
        (6, "-l", 7),
        (2, "-l", 3),
    ],
)
def test_limit_output_length(
    repo,
    max_length,
    command_option,
    mock_server_factory,
    runner,
    expected_length,
):
    mock_server_factory(
        [
            ["hello.txt", ["foo", "bar", "baz"]],
            ["foobar.py", ["def hello():", "    print('world')"]],
            ["foobar2.py", ["def hola():", "    print('mundo')"]],
            ["foobar3.py", ["def bonjour():", "    print('monde')"]],
            ["foobar.fake", ["fn hello()", "    echo('world')"]],
            ["foobar2.fake", ["fn hola()", "    echo('mundo')"]],
            ["foobar3.fake", ["fn bonjour()", "    echo('monde')"]],
        ]
    )
    query = "JavaScript"
    result = runner.invoke(
        seagoat,
        [
            query,
            repo.working_dir,
            "--no-color",
            command_option,
            str(max_length),
        ],
    )

    assert len(result.output.splitlines()) == min(expected_length, 15)
    assert result.output.splitlines() == result.output.splitlines()[:expected_length]
    assert result.exit_code == 0


def test_search_repo_returns_normalized_results(mocker, repo):
    from seagoat.query_service import search_repo

    mocker.patch(
        "seagoat.query_service.get_server_info",
        return_value={
            "host": "localhost",
            "port": 31337,
            "pid": 123,
            "address": "http://localhost:31337",
        },
    )

    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [
                {
                    "path": "file2.py",
                    "fullPath": "/tmp/will-be-rewritten/file2.py",
                    "score": 0.42,
                    "blocks": [],
                }
            ],
            "version": __version__,
        }
    )
    mock_response.raise_for_status.return_value = None
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    result = search_repo(
        query="Python",
        repo_path=repo.working_dir,
        max_results=7,
        context_above=2,
        context_below=4,
    )

    assert result["server_address"] == "http://localhost:31337"
    assert result["results"][0]["path"] == "file2.py"
    assert result["results"][0]["fullPath"] == str(
        Path(repo.working_dir).resolve() / "file2.py"
    )
    mocked_post.assert_called_once_with(
        "http://localhost:31337/lines/query",
        json={
            "queryText": "Python",
            "limitClue": 7,
            "contextAbove": 2,
            "contextBelow": 4,
        },
        headers={"Content-Type": "application/json"},
    )


def test_search_repo_uses_explicit_server_address(mocker, repo):
    from seagoat.query_service import search_repo

    mocked_get_server_info = mocker.patch("seagoat.query_service.get_server_info")

    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [
                {
                    "path": "missing.py",
                    "fullPath": "/tmp/will-be-rewritten/missing.py",
                    "score": 0.42,
                    "blocks": [],
                }
            ],
            "version": __version__,
        }
    )
    mock_response.raise_for_status.return_value = None
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    result = search_repo(
        query="Python",
        repo_path=repo.working_dir,
        server_address="http://remote-host:31337",
        max_results=7,
        context_above=2,
        context_below=4,
    )

    mocked_get_server_info.assert_not_called()
    assert result["server_address"] == "http://remote-host:31337"
    assert result["results"][0]["path"] == "missing.py"
    assert result["results"][0]["fullPath"] == str(
        Path(repo.working_dir).resolve() / "missing.py"
    )
    mocked_post.assert_called_once_with(
        "http://remote-host:31337/lines/query",
        json={
            "queryText": "Python",
            "limitClue": 7,
            "contextAbove": 2,
            "contextBelow": 4,
        },
        headers={"Content-Type": "application/json"},
    )


def test_search_repo_forwards_request_timeout(mocker, repo):
    from seagoat.query_service import search_repo

    mocker.patch(
        "seagoat.query_service.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )

    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps({"results": [], "version": __version__})
    mock_response.raise_for_status.return_value = None
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    search_repo(
        query="Python",
        repo_path=repo.working_dir,
        max_results=7,
        context_above=2,
        context_below=4,
        request_timeout=12,
    )

    mocked_post.assert_called_once_with(
        "http://localhost:31337/lines/query",
        json={
            "queryText": "Python",
            "limitClue": 7,
            "contextAbove": 2,
            "contextBelow": 4,
        },
        headers={"Content-Type": "application/json"},
        timeout=12,
    )


def test_search_repo_forwards_include_performance(mocker, repo):
    from seagoat.query_service import search_repo

    mocker.patch(
        "seagoat.query_service.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )

    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [],
            "version": __version__,
            "performance": {"totalMilliseconds": 12.3},
        }
    )
    mock_response.raise_for_status.return_value = None
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    result = search_repo(
        query="Python",
        repo_path=repo.working_dir,
        max_results=7,
        context_above=2,
        context_below=4,
        include_performance=True,
    )

    assert result["performance"] == {"totalMilliseconds": 12.3}
    mocked_post.assert_called_once_with(
        "http://localhost:31337/lines/query",
        json={
            "queryText": "Python",
            "limitClue": 7,
            "contextAbove": 2,
            "contextBelow": 4,
            "includePerformance": True,
        },
        headers={"Content-Type": "application/json"},
    )


def test_search_repo_accepts_payload_without_version(mocker, repo):
    from seagoat.query_service import search_repo

    mocker.patch(
        "seagoat.query_service.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )

    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [
                {
                    "path": "file2.py",
                    "fullPath": "/tmp/will-be-rewritten/file2.py",
                    "score": 0.42,
                    "blocks": [],
                }
            ]
        }
    )
    mock_response.raise_for_status.return_value = None
    mocker.patch("seagoat.query_service.requests.post", return_value=mock_response)

    result = search_repo(
        query="Python",
        repo_path=repo.working_dir,
        max_results=7,
        context_above=2,
        context_below=4,
    )

    assert result["version"] is None
    assert result["results"][0]["path"] == "file2.py"


def test_version_option(runner):
    result = runner.invoke(seagoat, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"seagoat, version {__version__}"


def test_mcp_server_subcommand_is_listed(runner):
    result = runner.invoke(seagoat, ["--help"])

    assert result.exit_code == 0
    assert "mcp-server" in result.output
    assert "Usage: seagoat [OPTIONS] QUERY [REPO_PATH]" in result.output
    assert "--version" in result.output
    assert "--no-color" in result.output
    assert "COMMAND [ARGS]" not in result.output


def test_mcp_server_subcommand_help_is_available(runner):
    result = runner.invoke(cli, ["mcp-server", "--help"])

    assert result.exit_code == 0
    assert "Usage: seagoat mcp-server [OPTIONS]" in result.output


def test_mcp_server_subcommand_imports_real_module_and_calls_main(runner, mocker):
    mocked_main = mocker.patch("seagoat.mcp_server.main", return_value=0)

    result = runner.invoke(cli, ["mcp-server"])

    assert result.exit_code == 0
    mocked_main.assert_called_once_with()


def test_seagoat_query_invocation_still_works(runner, mocker, repo):
    mocked_run_search_command = mocker.patch(
        "seagoat.cli.run_search_command", return_value=0
    )

    result = runner.invoke(cli, ["JavaScript", repo.working_dir, "--no-color"])

    assert result.exit_code == 0
    mocked_run_search_command.assert_called_once_with(
        "JavaScript",
        repo.working_dir,
        True,
        None,
        None,
        None,
        None,
        False,
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    "repo_path",
    [
        ("/path/to/repo1"),
        ("/another/path/to/repo2"),
    ],
)
def test_server_is_not_running_error(mocker, repo_path, snapshot, mock_halo):
    update_server_info(
        repo_path,
        {
            "host": "localhost",
            "port": 345435,
            "pid": 234234,
            "address": "http://example.com",
        },
    )
    runner = CliRunner()

    mocker.patch("os.isatty", return_value=True)
    query = "JavaScript"
    result = runner.invoke(seagoat, [query, repo_path])

    assert result.exit_code == 3
    assert str(result.output) == snapshot


def test_documentation_present(runner):
    result = runner.invoke(seagoat, ["--help"])
    assert result.exit_code == 0
    assert "Options:" in result.output
    assert "Query your codebase for your QUERY" in result.output
    assert "Usage: seagoat [OPTIONS] QUERY [REPO_PATH]" in result.output
    assert "--version" in result.output


def test_readme_mentions_mcp_support():
    contents = Path("README.md").read_text(encoding="utf-8")

    assert "seagoat mcp-server" in contents
    assert "codex mcp add seagoat -- seagoat mcp-server" in contents


def test_mcp_docs_page_is_listed_and_documents_codex_stdio_setup():
    mkdocs_contents = Path("mkdocs.yml").read_text(encoding="utf-8")
    docs_contents = Path("docs/mcp.md").read_text(encoding="utf-8")
    usage_contents = Path("docs/usage.md").read_text(encoding="utf-8")

    assert "MCP Integration: mcp.md" in mkdocs_contents
    assert "codex mcp add seagoat -- seagoat mcp-server" in docs_contents
    assert "seagoat-server start /path/to/your/repo" in docs_contents
    assert "seagoat` also exposes the `mcp-server` subcommand" in usage_contents


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize("context_above", [1, 2, 10])
def test_forwards_context_above_to_server(
    context_above, get_request_args_from_cli_call
):
    request_args1 = get_request_args_from_cli_call(
        ["--context-above", str(context_above)]
    )
    assert request_args1["json"]["contextAbove"] == context_above

    request_args2 = get_request_args_from_cli_call([f"-B{context_above}"])
    assert request_args2["json"]["contextAbove"] == context_above


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize("context_below", [1, 2, 10])
def test_forwards_context_below_to_server(
    context_below, get_request_args_from_cli_call
):
    request_args1 = get_request_args_from_cli_call(
        ["--context-below", str(context_below)]
    )
    assert request_args1["json"]["contextBelow"] == context_below

    request_args2 = get_request_args_from_cli_call([f"-A{context_below}"])
    assert request_args2["json"]["contextBelow"] == context_below


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize("context", [0, 1, 2, 10])
def test_forwards_context_to_server(context, get_request_args_from_cli_call):
    request_args1 = get_request_args_from_cli_call(["--context", str(context)])
    assert request_args1["json"]["contextAbove"] == context
    assert request_args1["json"]["contextBelow"] == context

    request_args2 = get_request_args_from_cli_call([f"-C{context}"])
    assert request_args2["json"]["contextAbove"] == context
    assert request_args2["json"]["contextBelow"] == context


@pytest.mark.usefixtures("mock_accuracy_warning")
def test_limit_does_not_apply_to_context_lines(repo, mock_server_factory, runner):
    mock_server_factory(
        [
            ["hello.txt", ["foo", "a context line", "baz"]],
            ["foobar.py", ["def hello():", "    print('world')"]],
            [
                "foobar2.py",
                [
                    "def hola():",
                    "    print('mundo') # I am a context line",
                    "# screaming: context!",
                ],
            ],
            ["foobar3.py", ["def bonjour():", "    print('monde')"]],
            [
                "foobar.fake",
                [
                    "fn hello()",
                    "    echo('world') // I am also a context line",
                ],
            ],
            ["foobar2.fake", ["fn hola()", "    echo('mundo')"]],
            [
                "foobar3.fake",
                [
                    "fn bonjour()",
                    "    echo('monde') /* I am too a context line */",
                ],
            ],
        ]
    )
    query = "JavaScript"
    result = runner.invoke(
        seagoat,
        [query, repo.working_dir, "--no-color", "-l5", "--context=3"],
    )

    assert len(result.output.splitlines()) > 5
    assert result.exit_code == 0


@pytest.mark.usefixtures("mock_accuracy_warning")
def test_context_lines_at_the_end_are_included(repo, mock_server_factory, runner):
    mock_server_factory(
        [
            [
                "hello.py",
                [
                    "foo()",
                    "# a context line",
                    "baz()",
                    "# another context line",
                    "# 3rd context line",
                ],
            ],
        ]
    )
    query = "JavaScript"
    result = runner.invoke(
        seagoat,
        [query, repo.working_dir, "--no-color", "-l2", "--context=3"],
    )

    assert len(result.output.splitlines()) == 5
    assert result.exit_code == 0


@pytest.mark.usefixtures("mock_accuracy_warning")
def test_context_lines_are_not_included_from_other_files_when_limit_exceeded(
    repo, mock_server_factory, runner
):
    mock_server_factory(
        [
            [
                "hello.py",
                [
                    "foo()",
                    "# a context line",
                    "baz()",
                    "# another context line",
                    "# 3rd context line",
                ],
            ],
            [
                "hello2.py",
                [
                    "# a context line",
                    "baz()",
                    "# another context line",
                    "# 3rd context line",
                ],
            ],
        ]
    )
    query = "JavaScript"
    result = runner.invoke(
        seagoat,
        [query, repo.working_dir, "--no-color", "-l2", "--context=3"],
    )

    assert len(result.output.splitlines()) == 5
    assert result.exit_code == 0


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize("args", [(), ("--reverse",)], ids=["default", "reversed"])
def test_reverse_ordering(
    repo, mock_server_factory, runner, snapshot, args: tuple[str, ...]
):
    mock_server_factory(
        [
            ["hello.txt", ["foo", "a context line", "baz"]],
            ["foobar.py", ["def hello():", "    print('world')"]],
        ]
    )
    query = "JavaScript"
    result = runner.invoke(
        seagoat,
        [query, repo.working_dir, "--no-color", *args],
    )

    assert str(result.output) == snapshot
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "error_message, error_code",
    [("File Not Found on Server", 500), ("Database Connection Failed", 503)],
)
def test_server_error_handling(
    repo,
    mocker,
    error_message,
    error_code,
    runner_with_error,
):
    mocker.patch(
        "seagoat.cli.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )
    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "code": error_code,
            "error": {
                "type": "Internal Server Error",
                "message": error_message,
            },
        }
    )
    mocker.patch("seagoat.query_service.requests.post", return_value=mock_response)

    query = "JavaScript"
    result = runner_with_error.invoke(
        seagoat, [query, repo.working_dir, "--no-color", "-l2", "--context=3"]
    )

    assert result.exit_code == 4
    assert error_message in result.stderr


def test_bat_installed(mocker):
    mock_run = mocker.patch("seagoat.utils.cli_display.subprocess.run")
    mock_run.return_value.returncode = 0
    assert is_bat_installed() is True


def test_bat_not_installed_1(mocker):
    mocker.patch(
        "seagoat.utils.cli_display.subprocess.run",
        side_effect=FileNotFoundError,
    )
    assert is_bat_installed() is False


def test_bat_not_installed_2(mocker):
    mock_run = mocker.patch("seagoat.utils.cli_display.subprocess.run")
    mock_run.return_value.returncode = 1
    assert is_bat_installed() is False


@pytest.mark.parametrize("newer_version", ["4243.3424.2", "99992.0.0"])
def test_warn_if_update_available_shows_warning(
    mocker, capsys, mock_response, newer_version
):
    mock_version_response = {"info": {"version": newer_version}}

    mocker.patch("requests.get", return_value=mock_response(mock_version_response))

    warn_if_update_available()
    captured = capsys.readouterr()

    assert (
        f"Warning: An updated version {newer_version} of SeaGOAT is available. You have {__version__}."
        in captured.err
    )


def test_warn_if_update_available_no_warning(mocker, capsys, mock_response):
    same_version = __version__
    mock_version_response = {"info": {"version": same_version}}

    mocker.patch("requests.get", return_value=mock_response(mock_version_response))

    warn_if_update_available()
    captured = capsys.readouterr()

    assert "Warning" not in captured.err


def test_warn_if_update_available_no_warning_for_older_pypi_version(
    mocker, capsys, mock_response
):
    mock_version_response = {"info": {"version": "0.54.17"}}

    mocker.patch("requests.get", return_value=mock_response(mock_version_response))

    warn_if_update_available()
    captured = capsys.readouterr()

    assert "Warning" not in captured.err


@pytest.mark.usefixtures(
    "server",
    "mock_accuracy_warning",
    "bat_available",
    "mock_warn_if_update_available",
)
def test_integration_test_no_results(snapshot, repo, mocker, runner):
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("seagoat.utils.cli_display.display_blocks_with_bat", return_value=True)
    query = "a_string_we_are_sure_does_not_exist_in_any_file_12345"
    result = runner.invoke(seagoat, [query, repo.working_dir])
    assert str(result.output) == snapshot
    assert result.exit_code == 0


def test_query_server_error_payload_returns_server_error(repo, mocker):
    runner = CliRunner()

    mocker.patch(
        "seagoat.cli.get_server_info",
        return_value={"address": "http://localhost:31337"},
    )
    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "error": {
                "type": "Internal Server Error",
                "message": "Database Connection Failed",
            }
        }
    )
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    result = runner.invoke(seagoat, ["JavaScript", repo.working_dir])

    assert result.exit_code == 4
    assert "Database Connection Failed" in result.output
    mocked_post.assert_called_once()


@pytest.mark.usefixtures("mock_accuracy_warning")
@pytest.mark.parametrize(
    "remote_host",
    ["http://example.com/potato", "https://ejemplo.es/nose/seagoat"],
)
def test_configure_remote_server_address(
    remote_host, get_request_args_from_cli_call, create_config_file
):
    create_config_file({"client": {"host": remote_host}})
    request_args = get_request_args_from_cli_call([])
    assert request_args["url"].startswith(remote_host)


@pytest.mark.usefixtures("mock_accuracy_warning", "bat_available")
@pytest.mark.parametrize(
    "remote_host",
    ["http://example.com/potato", "https://ejemplo.es/nose/seagoat"],
)
def test_connecting_to_remote_server(
    remote_host,
    repo,
    mocker,
    runner,
    temporary_cd,
    create_config_file,
    bat_calls,
):
    """
    When the user requests data from a remote server,
    the display logic should not rely on full path
    as the full path might be different on the remote server
    than locally

    Also the same files might not always exist.

    This test also tests that results are correctly displayed with bat
    """

    create_config_file({"client": {"host": remote_host}})
    mocker.patch("os.isatty", return_value=True)
    query = "JavaScript"
    repo.add_file_change_commit(
        file_name="example_remote.txt",
        contents="""JavaScript is an amazing programming language""",
        author=repo.actors["John Doe"],
        commit_message="Add remote-path data",
    )
    mock_response = mocker.Mock()
    mock_response.text = orjson.dumps(
        {
            "results": [
                {
                    "path": "example_remote.txt",
                    "fullPath": "/remote/server/repo/example_remote.txt",
                    "blocks": [
                        {
                            "lineTypeCount": {"result": 1, "context": 0},
                            "lines": [
                                {
                                    "line": 1,
                                    "lineText": "JavaScript is an amazing programming language",
                                    "resultTypes": ["result"],
                                }
                            ],
                        }
                    ],
                },
                {
                    "path": "missing_remote.txt",
                    "fullPath": "/remote/server/repo/missing_remote.txt",
                    "blocks": [
                        {
                            "lineTypeCount": {"result": 1, "context": 0},
                            "lines": [
                                {
                                    "line": 1,
                                    "lineText": "This remote file is missing locally",
                                    "resultTypes": ["result"],
                                }
                            ],
                        }
                    ],
                },
            ],
            "version": __version__,
        }
    )
    mock_response.raise_for_status.return_value = None
    mocked_post = mocker.patch(
        "seagoat.query_service.requests.post", return_value=mock_response
    )

    with tempfile.TemporaryDirectory() as tmpdirname:
        shutil.copytree(
            repo.working_dir,
            os.path.join(tmpdirname, "repo_copy"),
            dirs_exist_ok=True,
        )
        with temporary_cd(os.path.join(tmpdirname, "repo_copy")):
            result = runner.invoke(seagoat, [query, "."])

    assert result.exit_code == 0
    mocked_post.assert_called_once()
    assert mocked_post.call_args.args[0].startswith(remote_host)

    assert any("repo_copy/example_remote.txt" in call for call in bat_calls)
    assert all("missing_remote.txt" not in call for call in bat_calls)


def test_server_does_not_exist_error(runner_with_error, mocker, repo):
    mocker.patch(
        "seagoat.cli.requests.get",
        side_effect=requests.exceptions.ConnectionError,
    )
    query = "JavaScript"
    result = runner_with_error.invoke(seagoat, [query, repo.working_dir])

    assert result.exit_code == 3
    assert "The SeaGOAT server is not running" in result.stderr


@pytest.mark.usefixtures("mock_query_server")
def test_no_network_to_update(runner_with_error, mocker, mock_response, repo):
    mocked_response = {
        "stats": {
            "chunks": {"analyzed": 100, "unanalyzed": 0},
            "queue": {"size": 0},
            "accuracy": {"percentage": 100},
        },
        "version": __version__,
    }

    mocker.patch("requests.get", return_value=mock_response(mocked_response))
    mocker.patch("seagoat.cli.get_server_info", return_value={"address": ""})
    mocker.patch(
        "seagoat.cli.warn_if_update_available",
        side_effect=requests.exceptions.ConnectionError,
    )
    result = runner_with_error.invoke(seagoat, ["search", repo.working_dir])

    assert result.exit_code == 0
    assert "Could not check for updates" in result.stderr


@pytest.mark.usefixtures("server", "mock_accuracy_warning")
def test_does_not_crash_with_slash_in_request(
    snapshot, repo, mocker, runner, temporary_cd
):
    mocker.patch("os.isatty", return_value=True)
    query = "JavaScript/TypeScript"

    with temporary_cd(repo.working_dir):
        result = runner.invoke(seagoat, [query, ".", "--no-color"])

    assert result.exit_code == 0
