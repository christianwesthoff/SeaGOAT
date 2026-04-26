# MCP Fast Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SeaGOAT MCP searches more useful for Codex on large repositories by using small MCP-only defaults, keeping the repo server responsive during slow queries, and returning clear timeout errors to MCP clients.

**Architecture:** Keep the CLI query defaults unchanged. Apply the fast defaults inside `seagoat.mcp_tools.search.run_search_tool`, which is the shared MCP tool boundary, so Codex calls with omitted options request fewer results and less context. Start Waitress with a small thread pool so `/status` and other lightweight requests can still respond while one large query is processing. Thread an optional request timeout through the query service and use it only from the MCP tool.

**Tech Stack:** Python, FastMCP, pytest.

---

### Task 1: Add MCP Search Defaults

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `seagoat/mcp_tools/search.py`

- [ ] **Step 1: Write the failing test**

Update `test_run_search_tool_forwards_default_context_values` so it expects `max_results=20`, `context_above=1`, and `context_below=1` when the MCP caller omits those values.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `uv run pytest tests/test_mcp_server.py::test_run_search_tool_forwards_default_context_values -q`

Expected: FAIL because `run_search_tool` still forwards `max_results=None`, `context_above=3`, and `context_below=3`.

- [ ] **Step 3: Implement the minimal code**

Add constants in `seagoat/mcp_tools/search.py`:

```python
DEFAULT_MCP_MAX_RESULTS = 20
DEFAULT_MCP_CONTEXT_ABOVE = 1
DEFAULT_MCP_CONTEXT_BELOW = 1
```

Use those constants when `max_results`, `context_above`, or `context_below` are `None`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_mcp_server.py -q`

Expected: PASS.

- [ ] **Step 5: Run a live sanity check if the propstack server is running**

Run: `uv run seagoat-server status /Users/cwesthoff/Source/propstack --json`

If it is running, call `run_search_tool` without explicit `max_results` and confirm the request completes or reports a clear server-side latency issue.

### Task 2: Keep Server Status Responsive During Slow Queries

**Files:**
- Modify: `tests/test_server.py`
- Modify: `seagoat/server.py`

- [ ] **Step 1: Write the failing test**

Add a unit test that patches `seagoat.server.serve`, calls `start_server` with a custom port, and asserts Waitress receives `threads=4`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `uv run pytest tests/test_server.py::test_start_server_uses_thread_pool_for_responsiveness -q`

Expected: FAIL because `start_server` currently passes `threads=1`.

- [ ] **Step 3: Implement the minimal code**

Add a named constant in `seagoat/server.py`:

```python
SERVER_THREADS = 4
```

Pass `threads=SERVER_THREADS` to `serve(...)`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_server.py::test_start_server_uses_thread_pool_for_responsiveness tests/test_mcp_server.py -q`

Expected: PASS.

### Task 3: Add MCP Timeout Guard

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_cli.py`
- Modify: `seagoat/mcp_tools/search.py`
- Modify: `seagoat/query_service.py`

- [ ] **Step 1: Write failing tests**

Update the MCP default forwarding test so `run_search_tool` passes `request_timeout=20` to `search_repo`.

Add an MCP test where `search_repo` raises `requests.exceptions.Timeout` and assert `run_search_tool` raises a `RuntimeError` that names the timed-out query and repository.

Add a query service test that calls `search_repo(..., request_timeout=12)` and asserts `requests.post` receives `timeout=12`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `uv run pytest tests/test_mcp_server.py::test_run_search_tool_forwards_mcp_default_values tests/test_mcp_server.py::test_run_search_tool_translates_timeout_to_runtime_error tests/test_cli.py::test_search_repo_forwards_request_timeout -q`

Expected: FAIL because the timeout parameter does not exist yet.

- [ ] **Step 3: Implement the minimal code**

Add `DEFAULT_MCP_REQUEST_TIMEOUT_SECONDS = 20` in `seagoat/mcp_tools/search.py`.

Add optional `request_timeout: float | None = None` parameters to `query_lines` and `search_repo` in `seagoat/query_service.py`. Only pass `timeout=request_timeout` to `requests.post` when the value is not `None`.

Pass `request_timeout=DEFAULT_MCP_REQUEST_TIMEOUT_SECONDS` from `run_search_tool`.

Catch `requests.exceptions.Timeout` in `run_search_tool` and raise a concise `RuntimeError`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest tests/test_mcp_server.py tests/test_cli.py::test_search_repo_forwards_request_timeout -q`

Expected: PASS.
