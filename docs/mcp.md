<!-- markdownlint-disable MD046 -->
# SeaGOAT MCP Integration

SeaGOAT includes a native MCP server that Codex, Claude Desktop, and other MCP
clients can launch locally with `seagoat mcp-server` or the dedicated
`seagoat-mcp` entrypoint.

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

## Register SeaGOAT with Claude Desktop

Add SeaGOAT to your `claude_desktop_config.json` file.

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

If SeaGOAT is on your `PATH`, point Claude Desktop at `seagoat-mcp`:

```json
{
  "mcpServers": {
    "seagoat": {
      "command": "seagoat-mcp",
      "args": []
    }
  }
}
```

If needed, you can also point directly to the installed executable path.

## Available tools

SeaGOAT currently exposes these MCP tools:

- `server_status(repo_path)`
- `search(query, repo_path, max_results, context_above, context_below)`
- `search_code(query, limit, repo_path, context_above, context_below)`
- `read_file(repo_path, file_path, start_line, end_line)`
- `grep(repo_path, pattern, max_results, case_sensitive, regex, path_glob, timeout_seconds)`
- `research(question, repo_path, max_results_per_query, include_performance, path_glob)`

## Recommended workflow

Use SeaGOAT MCP as a research loop:

1. Use `server_status` first to check whether indexed semantic search is
   available for the target repo.
2. Use `research` when the repo server is running. Pass `path_glob` when you
   want fast exact research scoped to a package, directory, or file type. Scoped
   research skips unscoped semantic search and uses exact matches instead.
3. Use `grep` for literal symbols, error text, and filenames. Scope searches
   with `path_glob` and set `timeout_seconds` so large repositories can return
   useful partial results quickly.
4. Use `read_file` to inspect the relevant files and line ranges directly.
5. Answer with citations to the repository file paths that support the result.

## Troubleshooting

If Codex reports that no SeaGOAT server is running for a repository, start one
first with:

```bash
seagoat-server start /path/to/your/repo
```

If the command itself is unavailable, confirm that `seagoat` is installed and
that your shell can resolve it before registering the MCP server.
