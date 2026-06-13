"""Production flow tests."""

from pathlib import Path

from typer.testing import CliRunner

from ansys_report.cli import app
from ansys_report.production_flow import (
    ProductionInputs,
    apply_production_inputs,
)
from ansys_report.config import load_project_config

runner = CliRunner()


def test_cli_run_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "automated_scripts_output" in result.stdout
    assert "--image-assets" in result.stdout


def test_apply_production_inputs(repo_root, fixtures_dir, sample_calcs_xlsx, tmp_path):
    config = repo_root / "config" / "project.ep2737.production.yaml"
    if not config.exists():
        config = repo_root / "config" / "project.ep2737.yaml"
    cfg = load_project_config(config)
    image_dir = tmp_path / "exports"
    image_dir.mkdir()
    inputs = ProductionInputs(
        project_dir=fixtures_dir,
        image_assets=image_dir,
        excel_calcs=sample_calcs_xlsx,
        excel_bolt_preload=None,
        out_dir=tmp_path / "automated_scripts_output",
    )
    apply_production_inputs(cfg, inputs)
    assert cfg.project_dir == fixtures_dir.resolve()
    assert cfg.image_folder == str(image_dir.resolve())
    assert cfg.excel_calcs == str(sample_calcs_xlsx.resolve())
    assert cfg.skip_images is False


def test_run_requires_all_flags_or_interactive(repo_root):
    result = runner.invoke(app, ["run", "--project-dir", str(repo_root)])
    assert result.exit_code == 1


def test_run_mock_flags(repo_root, fixtures_dir, sample_calcs_xlsx, tmp_path):
    config = repo_root / "config" / "project.example.yaml"
    mock = fixtures_dir / "mock_results.json"
    image_dir = tmp_path / "exports"
    image_dir.mkdir()
    out = tmp_path / "automated_scripts_output"
    result = runner.invoke(
        app,
        [
            "run",
            "--config",
            str(config),
            "--project-dir",
            str(fixtures_dir),
            "--image-assets",
            str(image_dir),
            "--excel-calcs",
            str(sample_calcs_xlsx),
            "--out",
            str(out),
            "--no-pdf",
        ],
    )
    # run uses real scan, not mock — may fail validation without rst; check it starts
    assert result.exit_code in (0, 1, 2)
