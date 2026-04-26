<!-- markdownlint-disable MD046 -->
# SeaGOAT MCP Integration

SeaGOAT includes a native MCP server that Codex and other MCP clients can
launch locally with `seagoat mcp-server`.

## Start the SeaGOAT repo server

The `search` and `research` tools expect a SeaGOAT repo server to already be
running for the target repository because they use SeaGOAT's indexed semantic
search:

```bash
seagoat-server start /path/to/your/repo
```

File-oriented tools such as `read_file` operate on local repository files and
do not require indexed semantic search. Exact search with grep-style behavior
can follow the same local-file pattern when it is available through MCP.

## Register SeaGOAT with Codex

Use the following command to register the MCP server with Codex:

```bash
codex mcp add seagoat -- seagoat mcp-server
```

## Available tools

SeaGOAT currently exposes these MCP tools:

- `server_status(repo_path)`
- `search(query, repo_path, max_results, context_above, context_below)`
- `read_file(repo_path, file_path, start_line, end_line)`
- `grep(repo_path, pattern, max_results, case_sensitive, regex, path_glob, timeout_seconds)`
- `research(question, repo_path, max_results_per_query, include_performance)`

## Recommended workflow

Use SeaGOAT MCP as a research loop:

1. Use `server_status` to check whether indexed semantic search is available
   for the target repo.
2. Use `research` to expand the question into likely terms, symbols, and paths
   when the repo server is running.
3. Use `search` for semantic discovery when the SeaGOAT repo server is running.
4. Use `grep` for literal symbols, error text, and filenames that do not need
   semantic ranking.
   Scope large-repo searches with `path_glob` and set `timeout_seconds` when
   partial results are more useful than waiting for a full scan.
5. Use `read_file` to inspect the relevant files and line ranges directly.
6. Answer with citations to the repository file paths that support the result.

## Troubleshooting

If Codex reports that no SeaGOAT server is running for a repository, start one
first with:

```bash
seagoat-server start /path/to/your/repo
```

If the command itself is unavailable, confirm that `seagoat` is installed and
that your shell can resolve it before registering the MCP server.
