"""CLI smoke tests."""

from pathlib import Path

from typer.testing import CliRunner

from ansys_report.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "build" in result.stdout


def test_build_mock(repo_root, fixtures_dir, template_path, tmp_path):
    config = repo_root / "config" / "project.example.yaml"
    mock = fixtures_dir / "mock_results.json"
    out = tmp_path / "output"
    result = runner.invoke(
        app,
        [
            "build",
            "--config",
            str(config),
            "--project-dir",
            str(fixtures_dir),
            "--mock",
            str(mock),
            "--template",
            str(template_path),
            "--out",
            str(out),
            "--no-pdf",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert (out / "EP_1763_report.docx").exists()


def test_validate_exit_code(repo_root, fixtures_dir):
    config = repo_root / "config" / "project.example.yaml"
    result = runner.invoke(
        app,
        ["validate", "--config", str(config), "--project-dir", str(fixtures_dir)],
    )
    assert result.exit_code == 2
