"""Tests for post-figure material stress narratives."""

from pathlib import Path

from ansys_report.config import MaterialConfig, PersonRole, ProjectConfig
from ansys_report.narrative.figure_narrative import (
    material_stress_figure_description,
    resolve_material_stress_mpa,
)


def _cfg(repo_root: Path) -> ProjectConfig:
    return ProjectConfig(
        bom_id="EP2741",
        title="Test",
        customer="Test",
        project_dir=repo_root,
        sections_enabled=["static"],
        prepared_by=PersonRole(name="a", role="b"),
        checked_by=PersonRole(name="a", role="b"),
        approved_by=PersonRole(name="a", role="b"),
        materials=[
            MaterialConfig(name="ASTM B367 Gr 5", yield_mpa=300.0, static_allowable_mpa=255.71),
            MaterialConfig(name="ASTM B348 Gr 5", yield_mpa=300.0, static_allowable_mpa=255.71),
        ],
        primary_yield_mpa=300.0,
    )


def test_resolve_material_stress_from_per_material():
    data = {"per_material": {"ASTM B367 Gr 5": 77.82}}
    assert resolve_material_stress_mpa("MAT_ASTM_B367_GR_5", data) == 77.82


def test_material_stress_figure_description_safe(repo_root: Path):
    cfg = _cfg(repo_root)
    data = {"per_material": {"ASTM B367 Gr 5": 77.82}}
    text = material_stress_figure_description("MAT_ASTM_B367_GR_5", data, cfg)
    assert text is not None
    assert "77.82" in text
    assert "255.71" in text
    assert any(
        word in text.lower()
        for word in ("below", "within", "safe", "does not breach", "acceptable", "maintained")
    )


def test_material_stress_figure_description_missing_stress(repo_root: Path):
    cfg = _cfg(repo_root)
    assert material_stress_figure_description("MAT_UNKNOWN", {"per_material": {}}, cfg) is None
