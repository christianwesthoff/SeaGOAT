# SeaGOAT Native MCP Server Design

## Goal

Add a first-class local MCP server to SeaGOAT so Codex and other MCP clients can query SeaGOAT through a stable stdio integration without relying on an external wrapper script.

## Problem Statement

SeaGOAT already provides:

- a background repository server started with `seagoat-server start <repo_path>`
- a user-facing CLI (`seagoat` / `gt`)
- an HTTP API for query execution

What it does not provide is a native MCP surface. Today, the practical workaround is a separate adapter that shells out to `gt`, but that creates a second product surface with weaker contracts, human-oriented output, and version drift risk.

SeaGOAT should instead expose MCP directly as part of the product.

## Scope

### In Scope for v1

- Add a native local stdio MCP server to SeaGOAT
- Expose one MCP tool: `search`
- Support the following tool inputs:
  - `query`
  - `repo_path`
  - optional `max_results`
  - optional `context_above`
  - optional `context_below`
- Reuse SeaGOAT's existing structured query path instead of shelling out to `gt`
- Require that the SeaGOAT repository server is already running for the target repo
- Return both:
  - a concise text summary for agent consumption
  - structured result data derived from SeaGOAT query results
- Document how Codex users register the server with `codex mcp add ...`

### Out of Scope for v1

- Auto-starting SeaGOAT repository servers
- Remote MCP transport
- Multiple MCP tools beyond `search`
- Replacing the existing CLI or HTTP API
- Codex plugin packaging

## CLI Surface

Expose the MCP entry point as:

```bash
seagoat mcp-server
```

Rationale:

- MCP is a client-facing integration surface, closer to `seagoat` / `gt` than to the operational lifecycle commands under `seagoat-server`
- It gives users a simple, product-level command to register in Codex
- It avoids positioning MCP as an implementation detail of the background repo server

`seagoat-server mcp` is intentionally rejected for v1.

## Architecture

SeaGOAT should implement a native local stdio MCP server as a first-class CLI surface. The MCP layer should not shell out to `gt`. It should call SeaGOAT's internal structured query path and return MCP tool results directly.

The initial version should remain narrow:

- one MCP tool: `search`
- local stdio only
- explicit `repo_path`
- manual SeaGOAT server startup
- structured response payload plus concise text summary

This creates one stable MCP contract, one install story, and one place to test and version the integration.

## Components

### `seagoat/mcp_server.py`

Responsibilities:

- host the stdio MCP server
- define the tool schema for `search`
- validate tool inputs
- translate internal exceptions into MCP-friendly tool errors

### `seagoat/mcp_tools/search.py`

Responsibilities:

- implement the `search` MCP tool
- resolve and normalize `repo_path`
- locate the running SeaGOAT repository server
- execute the underlying structured query
- build the MCP response payload

### Shared query/service layer

Responsibilities:

- provide a reusable Python entry point for "query this repo and return structured results"
- encapsulate server lookup and HTTP interaction where needed
- act as the shared source of truth for CLI and MCP behavior

If SeaGOAT does not already have a clean reusable function for this path, one should be extracted from lower-level query/server utilities and used by both the MCP layer and existing CLI paths where appropriate.

## Data Flow

1. Codex starts `seagoat mcp-server` over stdio.
2. Codex invokes `search(query, repo_path, max_results, context_above, context_below)`.
3. SeaGOAT validates and resolves `repo_path`.
4. SeaGOAT finds the running SeaGOAT repository server for that repo.
5. SeaGOAT executes the structured search using the same internal behavior SeaGOAT already relies on.
6. SeaGOAT returns:
   - a concise text summary for the agent
   - structured result data including file paths, scores, blocks, and lines

## Tool Contract

### Tool Name

`search`

### Inputs

- `query: string`
- `repo_path: string`
- `max_results: integer | null`
- `context_above: integer | null`
- `context_below: integer | null`

### Response Shape

The response should include:

- a concise summary string
- normalized repository path
- result count
- server address used for the query
- result objects containing relevant SeaGOAT fields such as:
  - `path`
  - `fullPath`
  - `score`
  - `blocks`

The summary should be deterministic and short: one or two sentences describing the query, target repo, and the number of results returned.

The MCP layer should preserve SeaGOAT's structured semantics rather than flattening results into plain text only.

## Error Handling

Error behavior should be explicit and actionable.

### Validation Errors

- invalid or missing `query`
- invalid `repo_path`
- non-directory `repo_path`

These should produce clear MCP tool errors without stack traces.

### Runtime Errors

- no running SeaGOAT repository server for the requested repo
- upstream HTTP request failure
- upstream timeout
- malformed upstream response

For v1, the MCP server should not attempt to auto-start background SeaGOAT servers. If the repo server is not running, the error should clearly instruct the user to run:

```bash
seagoat-server start <repo_path>
```

Errors should be bounded, readable, and suitable for agent use.

## Testing Strategy

### Unit Tests

- input validation for `search`
- repo path normalization
- response shaping and summary generation
- exception-to-error translation

### Integration Tests

- MCP tool invocation against a running test SeaGOAT repository server
- success path for a real query
- failure path when the repo server is not running
- failure path for invalid repo path

### CLI Smoke Tests

- `seagoat mcp-server` starts successfully as a stdio process
- the MCP server registers the `search` tool correctly

## Rollout Plan

### v1

- ship native stdio MCP support
- ship one `search` tool
- require manual background SeaGOAT server startup
- publish Codex setup docs

### v1.1

- improve summary quality and response ergonomics
- refine error messages based on real usage

### Later

- consider additional tools such as `server_status` or file-oriented search only if usage justifies them
- consider richer packaging or plugin distribution after the native MCP contract is stable

## Documentation Requirements

Documentation should cover:

- how to start the SeaGOAT repository server
- how to register the MCP server in Codex
- expected local-only behavior
- common failures and their remedies

Example Codex registration should look conceptually like:

```bash
codex mcp add seagoat --command seagoat --args mcp-server
```

The exact command should be verified against current Codex documentation when implementation begins.

## Tradeoffs

### Why native MCP inside SeaGOAT

- one install story
- one versioned integration surface
- no wrapper drift
- structured results instead of human-formatted CLI output
- easier long-term testing and documentation

### Why not a wrapper around `gt`

- output is optimized for humans, not MCP clients
- creates a second unofficial product surface
- more likely to drift from SeaGOAT internals over time

### Why not a Codex plugin first

- plugins are better as packaging on top of a stable native MCP server
- they do not solve the lack of a first-class SeaGOAT MCP contract

## Recommendation

Implement a native MCP server directly in SeaGOAT with the command `seagoat mcp-server`, starting with a single `search` tool and explicit manual dependency on a running SeaGOAT repository server.
