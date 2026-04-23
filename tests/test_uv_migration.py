from pathlib import Path
import tomllib


def test_pyproject_uses_standard_project_metadata():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "project" in pyproject
    assert "tool" in pyproject
    assert "poetry" not in pyproject["tool"]
    assert pyproject["project"]["name"] == "seagoat"
    assert pyproject["project"]["scripts"]["seagoat"] == "seagoat.cli:cli"
    assert pyproject["project"]["scripts"]["gt"] == "seagoat.cli:cli"
    assert pyproject["project"]["scripts"]["seagoat-server"] == "seagoat.server:server"
    assert pyproject["build-system"]["build-backend"] != "poetry.core.masonry.api"


def test_repo_uses_uv_instead_of_poetry_for_development_workflow():
    readme = Path("README.md").read_text(encoding="utf-8")
    developer_docs = Path("docs/developer.md").read_text(encoding="utf-8")
    test_workflow = Path(".github/workflows/test.yml").read_text(encoding="utf-8")
    lint_workflow = Path(".github/workflows/lint.yml").read_text(encoding="utf-8")
    docs_workflow = Path(".github/workflows/docs.yml").read_text(encoding="utf-8")

    assert "poetry install" not in readme
    assert "poetry run" not in readme
    assert "poetry install" not in developer_docs
    assert "poetry run" not in developer_docs
    assert "Install Poetry" not in test_workflow
    assert "poetry " not in test_workflow
    assert "Install Poetry" not in lint_workflow
    assert "poetry " not in lint_workflow
    assert "Install Poetry" not in docs_workflow
    assert "poetry " not in docs_workflow
    assert "uv sync" in readme
    assert "uv run pytest" in developer_docs
    assert "uv sync" in test_workflow
    assert "uv sync" in lint_workflow
    assert "uv sync" in docs_workflow
