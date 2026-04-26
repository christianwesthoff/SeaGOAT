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


def test_run_grep_tool_rejects_empty_pattern(tmp_path):
    with pytest.raises(ValueError, match="pattern must not be empty"):
        run_grep_tool(repo_path=str(tmp_path), pattern="   ")


def test_run_grep_tool_raises_useful_error_for_invalid_regex(tmp_path):
    with pytest.raises(RuntimeError, match="Invalid grep regex pattern"):
        run_grep_tool(repo_path=str(tmp_path), pattern="[", regex=True)
