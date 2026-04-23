# SeaGOAT uv Migration Design

## Goal

Migrate SeaGOAT from a Poetry-managed project to a uv-native project. After the migration, SeaGOAT should use a standard PEP 621 `pyproject.toml`, a checked-in `uv.lock`, uv-based local development commands, and uv-based CI workflows. Poetry should no longer be required or documented.

## Scope

This migration covers:

- package metadata and dependency declaration
- lockfile and local environment workflow
- entry point preservation
- developer documentation
- GitHub Actions workflows
- release/build configuration that currently references Poetry

This migration does not change SeaGOAT runtime behavior or user-facing CLI semantics beyond installation and development workflow.

## Current State

SeaGOAT currently uses:

- `[tool.poetry]` metadata in `pyproject.toml`
- `[tool.poetry.dependencies]` and Poetry dependency groups
- `[tool.poetry.scripts]` for CLI entry points
- `poetry-core` as the build backend
- `poetry.lock` and `poetry.toml`
- documentation that teaches `poetry install` and `poetry run ...`
- CI workflows that install Poetry and run commands through Poetry
- semantic-release configuration that versions `tool.poetry.version` and builds with `poetry build`

This means the repository still treats Poetry as the authoritative package manager.

## Decision

SeaGOAT will move to a full uv-native workflow with a single authoritative toolchain:

- `pyproject.toml` will use standard `[project]` metadata
- runtime dependencies will live in `project.dependencies`
- development-only dependencies will move to `[dependency-groups]`
- CLI entry points will move to `[project.scripts]`
- `uv.lock` will be checked in
- local development will use `uv sync` and `uv run`
- CI will install and run through uv
- Poetry files and Poetry-specific configuration will be removed

There will be no long-term dual-tool support.

## Alternatives Considered

### 1. Full cutover to uv-native packaging

This is the selected approach.

Pros:

- one authoritative workflow
- standard PEP 621 metadata
- no ambiguity between Poetry and uv
- simpler docs and CI

Cons:

- larger one-time migration
- requires careful updates across packaging, docs, and automation

### 2. Staged cutover with temporary compatibility

Pros:

- lower short-term disruption
- allows a compatibility window for contributors

Cons:

- two competing workflows
- more repo churn
- higher chance of drift between lockfiles and docs

### 3. Operational uv support without metadata migration

Pros:

- smallest immediate change

Cons:

- not a real uv migration
- leaves Poetry metadata authoritative
- keeps the repo ambiguous

## Target Architecture

### Packaging

SeaGOAT will become a standard PEP 621 project:

- `[project]` will hold package metadata such as name, version, description, readme, license, authors, Python requirement, and runtime dependencies
- `[project.scripts]` will define:
  - `gt = "seagoat.cli:cli"`
  - `seagoat = "seagoat.cli:cli"`
  - `seagoat-server = "seagoat.server:server"`
- `[dependency-groups]` will replace Poetry-specific groups for development and optional evaluation dependencies
- `[build-system]` will switch away from `poetry-core` to a standard backend, expected to be `hatchling`

### Environment and Locking

The repository will use uv for local project management:

- `uv sync` will create and update `.venv`
- `uv run ...` will replace `poetry run ...`
- `uv.lock` will be checked in and treated as the only project lockfile
- `.python-version` will remain as the Python version pin

### Release Configuration

The semantic-release configuration will be updated so it no longer depends on Poetry-specific fields:

- versioning will target `pyproject.toml:project.version`
- build commands will use a uv-compatible or standard PEP 517 build path rather than `poetry build`

### CI

GitHub Actions workflows will install uv and use it directly:

- lint workflow: `uv sync` then `uv run pre-commit run --all-files`
- test workflow: `uv sync` then `uv run pytest ...`
- docs workflow: `uv sync` then `uv run ...`

The existing macOS x86 special-case should be preserved unless verification proves it is unnecessary after the migration.

## File-Level Changes

### `pyproject.toml`

Convert:

- `[tool.poetry]` -> `[project]`
- `[tool.poetry.scripts]` -> `[project.scripts]`
- `[tool.poetry.dependencies]` -> `project.dependencies`
- `[tool.poetry.group.dev.dependencies]` -> `[dependency-groups] dev = [...]`
- `[tool.poetry.group.ev.dependencies]` -> `[dependency-groups] ev = [...]`
- `build-system` -> uv-compatible standard backend
- semantic-release references from `tool.poetry.version` -> `project.version`
- semantic-release build command away from Poetry

### `uv.lock`

Generate and check in a real uv lockfile.

### `poetry.lock`

Remove from the repository.

### `poetry.toml`

Remove from the repository.

### Documentation

Update:

- `README.md`
- `docs/developer.md`

Replace Poetry-specific setup and command examples with uv equivalents.

### GitHub Actions

Update:

- `.github/workflows/lint.yml`
- `.github/workflows/test.yml`
- `.github/workflows/docs.yml`

Replace Poetry installation and command execution with uv equivalents.

## Dependency Translation Rules

To reduce migration risk, dependency translation should be mechanical:

- all runtime dependencies in `[tool.poetry.dependencies]`, except `python`, move to `project.dependencies`
- Python version constraint becomes `project.requires-python`
- all development/test/docs dependencies move into the `dev` dependency group unless there is a clear reason to keep them separate
- the existing `ev` group should remain separate if it is still intentionally optional

No dependency upgrades should be bundled into the migration unless uv resolution makes a specific upgrade unavoidable.

## Validation Requirements

The migration is only complete once all of the following are verified:

### Packaging and CLI

- `uv sync` succeeds from a clean checkout
- `uv run seagoat --help` succeeds
- `uv run gt --help` succeeds
- `uv run seagoat-server --help` succeeds
- `uv run seagoat mcp-server --help` or equivalent CLI help path remains discoverable

### Tests

At minimum, rerun the focused suites that validate the recently changed integration surfaces:

- `tests/test_cli.py`
- `tests/test_server.py`
- `tests/test_mcp_server.py`

These should be run through `uv run pytest ...`.

### Documentation / Workflow Sanity

Developer instructions in the README and developer docs must match the actual uv commands used locally and in CI.

## Risks

### Incorrect metadata conversion

If package metadata or entry points are translated incorrectly, installs or CLI discovery could break.

Mitigation:

- keep script names unchanged
- verify all three CLI entry points explicitly

### CI workflow drift

The repository currently depends on Poetry in multiple workflows. Missing one workflow would leave the migration incomplete.

Mitigation:

- update all Poetry-referencing workflows in the same migration
- search the repository for `poetry` before finalizing

### Release pipeline drift

semantic-release currently references Poetry metadata and build commands.

Mitigation:

- update both version path and build command together
- verify that no Poetry-specific semantic-release setting remains

### Lockfile ambiguity

Keeping both `poetry.lock` and `uv.lock` would create unclear source-of-truth.

Mitigation:

- remove Poetry lock/config files in the same migration

## Out of Scope

These are not part of the migration:

- changing SeaGOAT runtime logic
- redesigning the CLI
- changing MCP behavior
- broad dependency upgrades unrelated to uv adoption
- introducing dual support for Poetry and uv

## Recommended Rollout

Implement the migration as one focused change set:

1. convert packaging metadata in `pyproject.toml`
2. generate `uv.lock`
3. remove Poetry lock/config files
4. update docs
5. update CI and release configuration
6. run uv-based verification

This keeps the repo from sitting in a half-converted state.

## Success Criteria

The migration is successful when:

- a clean checkout can be set up with `uv sync`
- SeaGOAT commands run through `uv run`
- CI no longer installs or invokes Poetry
- the repository no longer contains authoritative Poetry project files
- focused test verification passes with uv
