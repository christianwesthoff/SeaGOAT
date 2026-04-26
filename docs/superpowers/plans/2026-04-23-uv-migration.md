# SeaGOAT uv Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert SeaGOAT from Poetry-managed packaging and workflows to a uv-native project with standard PEP 621 metadata, `uv.lock`, uv-based docs, and uv-based CI.

**Architecture:** Replace Poetry-specific metadata in `pyproject.toml` with standard `[project]`, `[project.scripts]`, and `[dependency-groups]`, then regenerate the lockfile with uv and remove Poetry lock/config files. Update docs and workflows to use `uv sync` and `uv run`, while preserving SeaGOAT runtime behavior and CLI entry points.

**Tech Stack:** Python packaging (PEP 621), uv, GitHub Actions, pytest, semantic-release

---

### Task 1: Convert Packaging Metadata

**Files:**
- Modify: `pyproject.toml`
- Delete: `poetry.toml`
- Delete: `poetry.lock`
- Create: `uv.lock`

- [ ] Replace Poetry metadata with `[project]`, `[project.scripts]`, and `[dependency-groups]`.
- [ ] Switch the build backend away from `poetry-core`.
- [ ] Update semantic-release to version `project.version` and stop building with Poetry.
- [ ] Remove Poetry lock/config files.
- [ ] Generate `uv.lock` with uv.

### Task 2: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/developer.md`

- [ ] Replace Poetry setup instructions with uv setup instructions.
- [ ] Replace `poetry run ...` examples with `uv run ...`.
- [ ] Keep end-user CLI and MCP usage unchanged where packaging is irrelevant.

### Task 3: Update CI Workflows

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `.github/workflows/lint.yml`
- Modify: `.github/workflows/docs.yml`

- [ ] Replace Poetry installation with uv installation.
- [ ] Replace dependency installation with `uv sync`.
- [ ] Replace command execution with `uv run ...`.
- [ ] Preserve the existing macOS special-case if still needed.

### Task 4: Verify uv Workflow

**Files:**
- Verify only

- [ ] Run `uv sync` from the repo root.
- [ ] Verify `uv run seagoat --help`.
- [ ] Verify `uv run gt --help`.
- [ ] Verify `uv run seagoat-server --help`.
- [ ] Run `uv run pytest tests/test_cli.py tests/test_server.py tests/test_mcp_server.py -q`.
