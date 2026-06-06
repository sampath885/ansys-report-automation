"""Context builder tests."""

from ansys_report.config import load_project_config
from ansys_report.report.context_builder import build_context, load_mock_results
from ansys_report.scanner import scan_project


def test_build_context_from_mock(repo_root, fixtures_dir):
    cfg = load_project_config(
        repo_root / "config" / "project.example.yaml",
        project_dir_override=fixtures_dir,
    )
    mock = load_mock_results(fixtures_dir / "mock_results.json")
    ctx, validation = build_context(cfg, mock_data=mock)
    assert ctx["bom_id"] == "EP 1763"
    assert ctx["static"]["max_stress_mpa"] == 210.5
    assert not validation.has_errors


def test_build_context_from_inventory(repo_root, fixtures_dir, sample_calcs_xlsx):
    cfg = load_project_config(
        repo_root / "config" / "project.example.yaml",
        project_dir_override=fixtures_dir,
    )
    inventory = scan_project(fixtures_dir, cfg.image_folder, sample_calcs_xlsx.name)
    ctx, validation = build_context(cfg, inventory=inventory, use_ai=False)
    assert "narrative" in ctx
    assert "design_calcs" in ctx
