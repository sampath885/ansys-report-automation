"""Config loading tests."""

from pathlib import Path

import pytest

from ansys_report.config import (
    REGISTERED_SECTIONS,
    load_project_config,
    load_thresholds,
    validate_project_paths,
)


def test_load_project_config(repo_root):
    cfg_path = repo_root / "config" / "project.example.yaml"
    cfg = load_project_config(cfg_path, project_dir_override=repo_root / "tests" / "fixtures")
    assert cfg.bom_id == "EP 1763"
    assert "modal" in cfg.sections_enabled
    assert cfg.operating_freq_hz[0] < cfg.operating_freq_hz[1]


def test_invalid_section_raises(repo_root, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "bom_id: X\ntitle: T\ncustomer: C\n"
        "prepared_by: {name: a, role: b}\nchecked_by: {name: a, role: b}\n"
        "approved_by: {name: a, role: b}\nproject_dir: .\n"
        "sections_enabled: [not_a_section]\noperating_freq_hz: [1, 2]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown sections"):
        load_project_config(bad)


def test_load_thresholds(repo_root):
    th = load_thresholds(repo_root / "config" / "thresholds.yaml")
    assert th.stress.warn_fraction_of_yield == 0.80
    assert th.fos.min_acceptable == 1.5


def test_registered_sections_cover_defaults():
    assert "modal" in REGISTERED_SECTIONS
    assert "design_calcs" in REGISTERED_SECTIONS
