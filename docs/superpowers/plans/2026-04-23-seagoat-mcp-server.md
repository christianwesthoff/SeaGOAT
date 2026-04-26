# SeaGOAT Native MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native local stdio MCP server to SeaGOAT, exposed as `seagoat mcp-server`, with one `search` tool that queries an already-running SeaGOAT repo server and returns structured results for Codex.

**Architecture:** Refactor the current single-command `seagoat` CLI into a compatibility-preserving Click group that still accepts `seagoat "query"` while also supporting the `mcp-server` subcommand. Implement the MCP surface with the official Python SDK (`FastMCP`) as a thin layer over a shared SeaGOAT query service so the CLI and MCP server use the same structured search behavior.

**Tech Stack:** Python 3.11+, Click, Flask/Waitress, requests, orjson, pytest, official MCP Python SDK (`mcp`)

---

## Planned File Structure

- Modify: `pyproject.toml`
  Add the `mcp` dependency and repoint the `seagoat` / `gt` console scripts at the new group entry point.

- Modify: `seagoat/cli.py`
  Convert the current single command into a group that preserves query behavior and adds the `mcp-server` subcommand.

- Create: `seagoat/query_service.py`
  Hold reusable Python functions for resolving repo/server information, executing structured queries, and shaping shared search results.

- Create: `seagoat/mcp_server.py`
  Define the `FastMCP` server, register the tool(s), and expose a `main()` entry point used by the CLI subcommand.

- Create: `seagoat/mcp_tools/__init__.py`
  Package marker for MCP tools.

- Create: `seagoat/mcp_tools/search.py`
  Implement the `search` MCP tool and deterministic response summary.

- Modify: `tests/test_cli.py`
  Cover the refactored CLI behavior and `mcp-server` command wiring.

- Create: `tests/test_mcp_server.py`
  Add unit and integration tests for MCP tool execution over stdio.

- Modify: `README.md`
  Document native MCP support and Codex registration.

- Modify: `docs/usage.md`
  Document the CLI surface including `seagoat mcp-server`.

- Create: `docs/mcp.md`
  Add focused setup and troubleshooting documentation for the MCP server.

- Modify: `mkdocs.yml`
  Add the MCP documentation page to the docs nav.

### Task 1: Extract a Shared Query Service

**Files:**
- Create: `seagoat/query_service.py`
- Modify: `seagoat/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test for the extracted query flow**

Add a unit-style test in `tests/test_cli.py` that proves the shared query helper returns normalized paths and forwards the expected request payload. Append a test like this near the existing CLI request-forwarding coverage:

```python
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
    assert result["results"][0]["fullPath"] == str(Path(repo.working_dir) / "file2.py")
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_cli.py::test_search_repo_returns_normalized_results -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'seagoat.query_service'`.

- [ ] **Step 3: Write the minimal shared query implementation**

Create `seagoat/query_service.py` with reusable functions for resolving the server, executing the HTTP query, and normalizing returned results:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import requests

from seagoat.utils.server import get_server_info


def rewrite_full_paths_to_use_local_path(repo_path: str | Path, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repo = Path(repo_path).expanduser().resolve()
    return [
        {
            **result,
            "fullPath": str((repo / result["path"]).resolve()),
        }
        for result in results
    ]


def remove_results_from_unavailable_files(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [result for result in results if Path(result["fullPath"]).exists()]


def query_lines(
    *,
    server_address: str,
    query: str,
    max_results: int | None,
    context_above: int,
    context_below: int,
) -> dict[str, Any]:
    response = requests.post(
        f"{server_address}/lines/query",
        json={
            "queryText": query,
            "limitClue": max_results,
            "contextAbove": context_above,
            "contextBelow": context_below,
        },
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return orjson.loads(response.text)


def search_repo(
    *,
    query: str,
    repo_path: str | Path,
    max_results: int | None,
    context_above: int,
    context_below: int,
) -> dict[str, Any]:
    normalized_repo_path = str(Path(repo_path).expanduser().resolve())
    server_info = get_server_info(normalized_repo_path)
    server_address = server_info["address"]
    response_data = query_lines(
        server_address=server_address,
        query=query,
        max_results=max_results,
        context_above=context_above,
        context_below=context_below,
    )
    results = rewrite_full_paths_to_use_local_path(
        normalized_repo_path, response_data["results"]
    )
    results = remove_results_from_unavailable_files(results)
    return {
        "repo_path": normalized_repo_path,
        "server_address": server_address,
        "results": results,
        "version": response_data["version"],
    }
```

Update `seagoat/cli.py` to import and use the new shared helpers instead of the current in-file implementations.

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
pytest tests/test_cli.py::test_search_repo_returns_normalized_results -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py seagoat/query_service.py seagoat/cli.py
git commit -m "refactor: extract shared query service"
```

### Task 2: Refactor the CLI to Support `seagoat mcp-server`

**Files:**
- Modify: `pyproject.toml`
- Modify: `seagoat/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI compatibility tests**

Add the following tests to `tests/test_cli.py`:

```python
def test_mcp_server_subcommand_is_listed(runner):
    from seagoat.cli import cli

    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "mcp-server" in result.output


def test_seagoat_query_invocation_still_works(runner, mocker, repo):
    from seagoat.cli import cli

    mocker.patch("seagoat.cli.run_search_command", return_value=0)

    result = runner.invoke(cli, ["JavaScript", repo.working_dir, "--no-color"])

    assert result.exit_code == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/test_cli.py::test_mcp_server_subcommand_is_listed tests/test_cli.py::test_seagoat_query_invocation_still_works -v
```

Expected: FAIL because `cli` and `run_search_command` do not exist yet.

- [ ] **Step 3: Implement the Click group and compatibility routing**

Update `seagoat/cli.py` to introduce a group entry point that defaults unknown commands to the existing search flow:

```python
class SeaGOATGroup(click.Group):
    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = ["search", *args]
        return super().resolve_command(ctx, args)


@click.group(cls=SeaGOATGroup)
@click.version_option(version=__version__, prog_name="seagoat")
def cli():
    """SeaGOAT command line interface."""


def run_search_command(
    query,
    repo_path,
    no_color,
    max_results,
    context_above,
    context_below,
    context,
    vimgrep,
    reverse,
    generative,
):
    config = get_config_values(Path(repo_path))
    spinner = Halo(text="Generating response...", spinner="dots", stream=sys.stderr)
    spinner.start()
    try:
        if context is not None:
            context_above = context
            context_below = context

        resolved_server_address = (
            config["client"]["host"]
            if config["client"]["host"] is not None
            else None
        )
        if resolved_server_address is None:
            search_data = search_repo(
                query=query,
                repo_path=repo_path,
                max_results=max_results,
                context_above=context_above if context_above is not None else 3,
                context_below=context_below if context_below is not None else 3,
            )
            server_address = search_data["server_address"]
            results = search_data["results"]
        else:
            response_data = query_lines(
                server_address=resolved_server_address,
                query=query,
                max_results=max_results,
                context_above=context_above if context_above is not None else 3,
                context_below=context_below if context_below is not None else 3,
            )
            server_address = resolved_server_address
            results = rewrite_full_paths_to_use_local_path(repo_path, response_data["results"])
            results = remove_results_from_unavailable_files(results)

        if reverse or generative:
            results = reversed(results)
        if generative:
            results = enhance_results(query, results, spinner)

        spinner.succeed()
        color_enabled = os.isatty(0) and not no_color and not vimgrep
        display_results(results, max_results, color_enabled, vimgrep)
        display_accuracy_warning(server_address)
        return 0
    except (requests.exceptions.ConnectionError, requests.exceptions.RequestException, ServerDoesNotExist):
        spinner.fail()
        click.echo(
            f"The SeaGOAT server is not running. Please start the server using the following command: seagoat-server start {repo_path}",
            err=True,
        )
        return ExitCode.SERVER_NOT_RUNNING


@cli.command(name="search")
@click.argument("query")
@click.argument("repo_path", required=False, default=os.getcwd())
@click.option("--no-color", is_flag=True)
@click.option("--vimgrep", is_flag=True)
@click.option("-l", "--max-results", type=int, default=None)
@click.option("-B", "--context-above", type=int, default=None)
@click.option("-A", "--context-below", type=int, default=None)
@click.option("-C", "--context", type=int, default=None)
@click.option("-r", "--reverse", is_flag=True, default=False)
@click.option("-g", "--generative", is_flag=True, default=False)
def search(query, repo_path, no_color, max_results, context_above, context_below, context, vimgrep, reverse, generative):
    raise SystemExit(
        run_search_command(
            query,
            repo_path,
            no_color,
            max_results,
            context_above,
            context_below,
            context,
            vimgrep,
            reverse,
            generative,
        )
    )
```

Update `pyproject.toml` to point both scripts at the group entry point:

```toml
[tool.poetry.scripts]
gt = "seagoat.cli:cli"
seagoat = "seagoat.cli:cli"
seagoat-server = "seagoat.server:server"
```

- [ ] **Step 4: Run the focused CLI tests**

Run:

```bash
pytest tests/test_cli.py::test_mcp_server_subcommand_is_listed tests/test_cli.py::test_seagoat_query_invocation_still_works tests/test_cli.py::test_documentation_present tests/test_cli.py::test_version_option -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml seagoat/cli.py tests/test_cli.py
git commit -m "feat: add CLI support for mcp-server"
```

### Task 3: Implement the Native MCP Server and Search Tool

**Files:**
- Create: `seagoat/mcp_server.py`
- Create: `seagoat/mcp_tools/__init__.py`
- Create: `seagoat/mcp_tools/search.py`
- Modify: `seagoat/cli.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing MCP tool tests**

Create `tests/test_mcp_server.py` with unit coverage for summary shaping and validation:

```python
from pathlib import Path

import pytest

from seagoat.mcp_tools.search import build_summary, validate_repo_path


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

    assert summary == "SeaGOAT searched '/tmp/repo' for 'round numbers' and returned 3 results."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
pytest tests/test_mcp_server.py::test_validate_repo_path_rejects_missing_directory tests/test_mcp_server.py::test_build_summary_uses_query_repo_and_result_count -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'seagoat.mcp_tools'`.

- [ ] **Step 3: Implement the MCP server and `search` tool**

Create `seagoat/mcp_tools/search.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from seagoat.query_service import search_repo
from seagoat.utils.server import ServerDoesNotExist


def validate_repo_path(repo_path: str) -> str:
    path = Path(repo_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"repo_path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {path}")
    return str(path)


def build_summary(*, query: str, repo_path: str, result_count: int) -> str:
    noun = "result" if result_count == 1 else "results"
    return f"SeaGOAT searched '{repo_path}' for '{query}' and returned {result_count} {noun}."


def run_search_tool(
    *,
    query: str,
    repo_path: str,
    max_results: int | None = None,
    context_above: int | None = None,
    context_below: int | None = None,
) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query must not be empty")

    normalized_repo_path = validate_repo_path(repo_path)
    try:
        search_data = search_repo(
            query=query.strip(),
            repo_path=normalized_repo_path,
            max_results=max_results,
            context_above=3 if context_above is None else context_above,
            context_below=3 if context_below is None else context_below,
        )
    except ServerDoesNotExist as exc:
        raise RuntimeError(
            f"No SeaGOAT server is running for '{normalized_repo_path}'. Start it with: seagoat-server start {normalized_repo_path}"
        ) from exc

    return {
        "summary": build_summary(
            query=query.strip(),
            repo_path=normalized_repo_path,
            result_count=len(search_data["results"]),
        ),
        "repo_path": normalized_repo_path,
        "server_address": search_data["server_address"],
        "result_count": len(search_data["results"]),
        "results": search_data["results"],
    }
```

Create `seagoat/mcp_server.py`:

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from seagoat.mcp_tools.search import run_search_tool

mcp = FastMCP("SeaGOAT")


@mcp.tool()
def search(
    query: str,
    repo_path: str,
    max_results: int | None = None,
    context_above: int | None = None,
    context_below: int | None = None,
) -> dict:
    return run_search_tool(
        query=query,
        repo_path=repo_path,
        max_results=max_results,
        context_above=context_above,
        context_below=context_below,
    )


def main() -> None:
    mcp.run()
```

Add the CLI subcommand in `seagoat/cli.py`:

```python
@cli.command(name="mcp-server")
def mcp_server_command():
    """Start the SeaGOAT MCP server over stdio."""
    from seagoat.mcp_server import main

    main()
```

Add the dependency in `pyproject.toml`:

```toml
[tool.poetry.dependencies]
mcp = "^1.0.0"
```

- [ ] **Step 4: Run the unit tests**

Run:

```bash
pytest tests/test_mcp_server.py::test_validate_repo_path_rejects_missing_directory tests/test_mcp_server.py::test_build_summary_uses_query_repo_and_result_count -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml seagoat/cli.py seagoat/mcp_server.py seagoat/mcp_tools/__init__.py seagoat/mcp_tools/search.py tests/test_mcp_server.py
git commit -m "feat: add native SeaGOAT MCP server"
```

### Task 4: Verify MCP over STDIO End-to-End

**Files:**
- Modify: `tests/test_mcp_server.py`
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing stdio integration test**

Extend `tests/test_mcp_server.py` with a real stdio client/server test using the official MCP Python SDK:

```python
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_search_tool_over_stdio(server, repo):
    async def run_test():
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "seagoat.mcp_server"],
            env={**os.environ, "PYTHONPATH": os.getcwd()},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "search",
                    {
                        "query": "Markdown",
                        "repo_path": repo.working_dir,
                        "max_results": 5,
                    },
                )
                structured = result.structuredContent
                assert structured["repo_path"] == repo.working_dir
                assert structured["result_count"] > 0
                assert structured["summary"].startswith("SeaGOAT searched")

    asyncio.run(run_test())
```

- [ ] **Step 2: Run the integration test to verify it fails**

Run:

```bash
pytest tests/test_mcp_server.py::test_search_tool_over_stdio -v
```

Expected: FAIL because the dependency or MCP server wiring is incomplete, or because the MCP server cannot yet initialize correctly.

- [ ] **Step 3: Fix initialization and CLI smoke coverage**

If the test fails on initialization, make the following targeted adjustments:

```python
def test_mcp_server_subcommand_help(runner):
    from seagoat.cli import cli

    result = runner.invoke(cli, ["mcp-server", "--help"])

    assert result.exit_code == 0
    assert "Start the SeaGOAT MCP server over stdio." in result.output
```

If the stdio server needs explicit initialization metadata or transport settings, update `seagoat/mcp_server.py` to the minimum working `FastMCP` configuration rather than adding custom transport code.

- [ ] **Step 4: Run the full MCP test file**

Run:

```bash
pytest tests/test_mcp_server.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_mcp_server.py seagoat/mcp_server.py seagoat/cli.py
git commit -m "test: cover SeaGOAT MCP stdio flow"
```

### Task 5: Document Codex Setup and SeaGOAT MCP Usage

**Files:**
- Modify: `README.md`
- Modify: `docs/usage.md`
- Create: `docs/mcp.md`
- Modify: `mkdocs.yml`

- [ ] **Step 1: Write the failing documentation checks**

Add simple content assertions to guard the docs additions in `tests/test_cli.py`:

```python
from pathlib import Path


def test_readme_mentions_mcp_support():
    contents = Path("README.md").read_text(encoding="utf-8")

    assert "seagoat mcp-server" in contents
    assert "codex mcp add seagoat --command seagoat --args mcp-server" in contents
```

- [ ] **Step 2: Run the doc check to verify it fails**

Run:

```bash
pytest tests/test_cli.py::test_readme_mentions_mcp_support -v
```

Expected: FAIL because the documentation has not been updated yet.

- [ ] **Step 3: Update README and docs**

Update `README.md` with a new section after the normal CLI usage:

````md
### Use SeaGOAT from Codex via MCP

SeaGOAT includes a native local MCP server for Codex and other MCP clients:

```bash
seagoat mcp-server
```

To register it with Codex:

```bash
codex mcp add seagoat --command seagoat --args mcp-server
```

SeaGOAT's MCP server expects a SeaGOAT repo server to already be running for the target repository:

```bash
seagoat-server start /path/to/your/repo
```
````

Create `docs/mcp.md` with setup, troubleshooting, and a short explanation of the `search` tool:

````md
# SeaGOAT MCP Integration

## Start the SeaGOAT repo server

```bash
seagoat-server start /path/to/your/repo
```

## Register SeaGOAT with Codex

```bash
codex mcp add seagoat --command seagoat --args mcp-server
```

## Available tool

- `search(query, repo_path, max_results, context_above, context_below)`

## Common failure

If Codex reports that no SeaGOAT server is running for a repository, start one first with:

```bash
seagoat-server start /path/to/your/repo
```
````

Update `docs/usage.md` with a short note that `seagoat` now also exposes the `mcp-server` subcommand, and add the new page to `mkdocs.yml`:

```yaml
nav:
    - Getting Started: index.md
    - Usage Reference: usage.md
    - MCP Integration: mcp.md
    - SeaGOAT Server: server.md
    - Configuring SeaGOAT: configuration.md
    - Developer Documentation: developer.md
```

- [ ] **Step 4: Run the focused docs checks**

Run:

```bash
pytest tests/test_cli.py::test_readme_mentions_mcp_support -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md docs/usage.md docs/mcp.md mkdocs.yml tests/test_cli.py
git commit -m "docs: add SeaGOAT MCP setup guide"
```

### Task 6: Final Verification

**Files:**
- Modify: none
- Test: `tests/test_cli.py`, `tests/test_mcp_server.py`, `tests/test_server.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
pytest tests/test_cli.py tests/test_mcp_server.py tests/test_server.py -v
```

Expected: PASS

- [ ] **Step 2: Run a manual MCP smoke test**

Start a repo server:

```bash
seagoat-server start /absolute/path/to/SeaGOAT
```

In a second shell, verify the MCP server process starts:

```bash
seagoat mcp-server
```

Then register with Codex:

```bash
codex mcp add seagoat --command seagoat --args mcp-server
```

Ask Codex to call the `search` tool against the SeaGOAT repo and verify the returned response includes:

```text
summary
repo_path
server_address
result_count
results
```

- [ ] **Step 3: Confirm spec coverage**

Check the implementation against `docs/superpowers/specs/2026-04-23-seagoat-mcp-design.md`:

```text
- Native local stdio MCP server: covered by Tasks 2-4
- `search` tool only: covered by Task 3
- Explicit `repo_path`: covered by Tasks 1 and 3
- Manual SeaGOAT server startup: covered by Tasks 3 and 5
- Structured response plus summary: covered by Task 3
- Codex registration docs: covered by Task 5
```

- [ ] **Step 4: Commit if verification required follow-up edits**

```bash
git add pyproject.toml seagoat/cli.py seagoat/query_service.py seagoat/mcp_server.py seagoat/mcp_tools/__init__.py seagoat/mcp_tools/search.py tests/test_cli.py tests/test_mcp_server.py README.md docs/usage.md docs/mcp.md mkdocs.yml
git commit -m "chore: finalize SeaGOAT MCP integration"
```
