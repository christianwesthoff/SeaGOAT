<!-- markdownlint-disable MD046 -->
# SeaGOAT MCP Integration

SeaGOAT includes a native MCP server that Codex and other MCP clients can
launch locally with `seagoat mcp-server`.

## Start the SeaGOAT repo server

The MCP server expects a SeaGOAT repo server to already be running for the
target repository:

```bash
seagoat-server start /path/to/your/repo
```

## Register SeaGOAT with Codex

Use the following command to register the MCP server with Codex:

```bash
codex mcp add seagoat -- seagoat mcp-server
```

## Available tool

SeaGOAT currently exposes a single MCP tool:

- `search(query, repo_path, max_results, context_above, context_below)`

## Troubleshooting

If Codex reports that no SeaGOAT server is running for a repository, start one
first with:

```bash
seagoat-server start /path/to/your/repo
```

If the command itself is unavailable, confirm that `seagoat` is installed and
that your shell can resolve it before registering the MCP server.
