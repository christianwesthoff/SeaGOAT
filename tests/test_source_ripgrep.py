from pathlib import Path

from seagoat.repository import Repository
from seagoat.sources.ripgrep import initialize
from tests.test_ripgrep import pytest


@pytest.fixture(name="initialize_source")
def _initialize_source():
    def _initalize(repo):
        path = repo.working_dir
        my_repo = Repository(path)
        my_repo.analyze_files()
        source = initialize(my_repo)

        source["cache_repo"]()

        return source["fetch"]

    return _initalize


def test_fetch_and_initialize(repo, initialize_source):
    contents = """
234
hello foo bar baz
hello foo bar baz 23

234234
345 adaf
2345234523452345235
2345
"""
    repo.add_file_change_commit(
        file_name="file1.txt",
        contents=contents,
        author=repo.actors["John Doe"],
        commit_message="Initial commit for text file",
    )

    fetch = initialize_source(repo)
    fetched_results = fetch("[0-9]{2,10}", limit=400)

    assert len(fetched_results) == 1
    file = next(iter(fetched_results))
    assert file.gitfile.path == "file1.txt"
    assert set(line for line in file.lines) == {2, 4, 6, 7, 8, 9}


def test_whitespace_is_used_as_or_operator(repo, initialize_source):
    contents = """
234
hello foo bar baz
hello foo bar baz 23

234234
345 adaf
2345234523452345235
2345
baz
bar
b3
"""
    repo.add_file_change_commit(
        file_name="file1.txt",
        contents=contents,
        author=repo.actors["John Doe"],
        commit_message="Initial commit for text file",
    )

    fetch = initialize_source(repo)
    fetched_results = fetch("[0-9]{2,10} baz bar b[0-9]", limit=100)

    assert len(fetched_results) == 1
    result = next(iter(fetched_results))
    assert result.gitfile.path == "file1.txt"
    assert set(line for line in result.lines) == {
        2,
        3,
        4,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
    }


def test_fetch_does_not_build_full_cache_when_cache_is_not_initialized(repo, mocker):
    repo.add_file_change_commit(
        file_name="file1.txt",
        contents="hello direct ripgrep",
        author=repo.actors["John Doe"],
        commit_message="Initial commit for text file",
    )
    repository = Repository(repo.working_dir)
    repository.analyze_files()
    source = initialize(repository)
    mocked_analyze_files = mocker.patch.object(repository, "analyze_files")
    mocked_rebuild = mocker.patch(
        "seagoat.sources.ripgrep.RipGrepCache.rebuild",
        side_effect=AssertionError("fetch should not build the full ripgrep cache"),
    )

    fetched_results = source["fetch"]("direct", limit=10)

    assert mocked_rebuild.call_count == 0
    mocked_analyze_files.assert_not_called()
    assert [result.gitfile.path for result in fetched_results] == ["file1.txt"]


def test_cache_repo_can_pause_before_building_full_cache(repo, mocker):
    repo.add_file_change_commit(
        file_name="file1.txt",
        contents="hello direct ripgrep",
        author=repo.actors["John Doe"],
        commit_message="Initial commit for text file",
    )
    repository = Repository(repo.working_dir)
    repository.analyze_files()
    source = initialize(repository)
    mocked_check_output = mocker.patch("seagoat.sources.ripgrep.subprocess.check_output")
    gitfile = mocker.Mock()
    gitfile.path = "file1.txt"
    gitfile.absolute_path = Path(repo.working_dir) / "file1.txt"
    gitfile.lines = {1: "hello direct ripgrep"}
    mocker.patch.object(repository, "get_file", return_value=gitfile)
    process = mocker.Mock()
    process.stdout = iter(["file1.txt:1:hello direct ripgrep\n"])
    process.wait.return_value = 0
    popen = mocker.patch("seagoat.sources.ripgrep.subprocess.Popen")
    popen.return_value.__enter__.return_value = process

    assert source["cache_repo"](should_continue=lambda: False) is False
    fetched_results = source["fetch"]("direct", limit=10)

    assert [result.gitfile.path for result in fetched_results] == ["file1.txt"]
    mocked_check_output.assert_not_called()


def test_uncached_fetch_stops_ripgrep_after_enough_candidate_files(repo, mocker):
    for index in range(3):
        repo.add_file_change_commit(
            file_name=f"file{index}.txt",
            contents=f"hello direct ripgrep {index}",
            author=repo.actors["John Doe"],
            commit_message=f"Initial commit for text file {index}",
        )
    repository = Repository(repo.working_dir)
    repository.analyze_files()
    source = initialize(repository)
    mocked_analyze_files = mocker.patch.object(repository, "analyze_files")
    gitfiles = {}
    for index in range(3):
        gitfile = mocker.Mock()
        gitfile.path = f"file{index}.txt"
        gitfile.absolute_path = Path(repo.working_dir) / f"file{index}.txt"
        gitfile.lines = {1: f"hello direct ripgrep {index}"}
        gitfiles[gitfile.path] = gitfile
    mocker.patch.object(repository, "get_file", side_effect=lambda path: gitfiles[path])
    process = mocker.Mock()
    process.stdout = iter([
        "file0.txt:1:hello direct ripgrep 0\n",
        "file1.txt:1:hello direct ripgrep 1\n",
        "file2.txt:1:hello direct ripgrep 2\n",
    ])
    process.wait.return_value = 0
    popen = mocker.patch("seagoat.sources.ripgrep.subprocess.Popen")
    popen.return_value.__enter__.return_value = process

    fetched_results = source["fetch"]("direct", limit=2)

    assert [result.gitfile.path for result in fetched_results] == [
        "file0.txt",
        "file1.txt",
    ]
    mocked_analyze_files.assert_not_called()
    process.terminate.assert_called_once_with()
