import pytest

from seagoat.mcp_tools.grep import run_grep_tool


def test_run_grep_tool_searches_literal_text(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text(
        "alpha needle\n"
        "regex-looking n.*dle\n"
        "Needle upper\n",
        encoding="utf-8",
    )

    result = run_grep_tool(
        repo_path=str(tmp_path),
        pattern="n.*dle",
        case_sensitive=True,
    )

    assert result == {
        "summary": f"SeaGOAT grep searched '{tmp_path}' for 'n.*dle' and returned 1 result.",
        "repo_path": str(tmp_path),
        "pattern": "n.*dle",
        "result_count": 1,
        "max_results": 50,
        "truncated": False,
        "results": [
            {
                "file_path": "notes.txt",
                "full_path": str(file_path),
                "line": 2,
                "text": "regex-looking n.*dle",
            }
        ],
    }


def test_run_grep_tool_marks_truncated_when_more_matches_exist(tmp_path):
    file_path = tmp_path / "matches.txt"
    file_path.write_text("hit one\nhit two\nhit three\n", encoding="utf-8")

    result = run_grep_tool(
        repo_path=str(tmp_path),
        pattern="hit",
        max_results=2,
    )

    assert result["result_count"] == 2
    assert result["max_results"] == 2
    assert result["truncated"] is True
    assert result["results"] == [
        {
            "file_path": "matches.txt",
            "full_path": str(file_path),
            "line": 1,
            "text": "hit one",
        },
        {
            "file_path": "matches.txt",
            "full_path": str(file_path),
            "line": 2,
            "text": "hit two",
        },
    ]


def test_run_grep_tool_handles_colons_in_file_paths(tmp_path):
    file_path = tmp_path / "a:b.txt"
    file_path.write_text("needle in colon path\n", encoding="utf-8")

    result = run_grep_tool(repo_path=str(tmp_path), pattern="needle")

    assert result["results"] == [
        {
            "file_path": "a:b.txt",
            "full_path": str(file_path),
            "line": 1,
            "text": "needle in colon path",
        }
    ]


def test_run_grep_tool_handles_patterns_that_start_with_dash(tmp_path):
    file_path = tmp_path / "flags.txt"
    file_path.write_text("literal --needle flag\n", encoding="utf-8")

    result = run_grep_tool(repo_path=str(tmp_path), pattern="--needle")

    assert result["results"] == [
        {
            "file_path": "flags.txt",
            "full_path": str(file_path),
            "line": 1,
            "text": "literal --needle flag",
        }
    ]


def test_run_grep_tool_limits_search_to_path_glob(tmp_path):
    app_file = tmp_path / "app" / "models" / "broker.rb"
    spec_file = tmp_path / "spec" / "models" / "broker_spec.rb"
    app_file.parent.mkdir(parents=True)
    spec_file.parent.mkdir(parents=True)
    app_file.write_text("needle in app\n", encoding="utf-8")
    spec_file.write_text("needle in spec\n", encoding="utf-8")

    result = run_grep_tool(
        repo_path=str(tmp_path),
        pattern="needle",
        path_glob="app/**/*.rb",
    )

    assert result["path_glob"] == "app/**/*.rb"
    assert result["result_count"] == 1
    assert result["results"] == [
        {
            "file_path": "app/models/broker.rb",
            "full_path": str(app_file),
            "line": 1,
            "text": "needle in app",
        }
    ]


def test_run_grep_tool_searches_current_directory_explicitly(tmp_path, mocker):
    mocked_run_rg = mocker.patch(
        "seagoat.mcp_tools.grep._run_rg_bounded",
        return_value=([], 1, "", False),
    )

    run_grep_tool(repo_path=str(tmp_path), pattern="needle")

    command = mocked_run_rg.call_args.args[0]
    assert command[-3:] == ["--", "needle", "."]


def test_run_grep_tool_marks_partial_when_timeout_expires(tmp_path, mocker):
    file_path = tmp_path / "matches.txt"
    file_path.write_text("hit one\nhit two\n", encoding="utf-8")

    mocker.patch("seagoat.mcp_tools.grep.time.monotonic", side_effect=[0.0, 2.0])

    result = run_grep_tool(
        repo_path=str(tmp_path),
        pattern="hit",
        timeout_seconds=1.0,
    )

    assert result["partial"] is True
    assert result["timed_out"] is True
    assert result["results"] == [
        {
            "file_path": "matches.txt",
            "full_path": str(file_path),
            "line": 1,
            "text": "hit one",
        }
    ]


def test_run_grep_tool_rejects_empty_pattern(tmp_path):
    with pytest.raises(ValueError, match="pattern must not be empty"):
        run_grep_tool(repo_path=str(tmp_path), pattern="   ")


def test_run_grep_tool_raises_useful_error_for_invalid_regex(tmp_path):
    with pytest.raises(RuntimeError, match="Invalid grep regex pattern"):
        run_grep_tool(repo_path=str(tmp_path), pattern="[", regex=True)
