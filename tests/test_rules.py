"""Rule-based narrative tests."""

import pytest

from ansys_report.config import ProjectConfig, PersonRole, load_thresholds
from ansys_report.models import ModalResult, ModeResult, StaticResult
from ansys_report.narrative import rules


@pytest.fixture
def sample_cfg(repo_root):
    return ProjectConfig(
        bom_id="T",
        title="T",
        customer="C",
        prepared_by=PersonRole(name="a", role="b"),
        checked_by=PersonRole(name="a", role="b"),
        approved_by=PersonRole(name="a", role="b"),
        project_dir=repo_root,
        sections_enabled=["static", "modal"],
        operating_freq_hz=[10, 200],
        materials=[{"name": "Steel", "yield_mpa": 350}],
    )


@pytest.fixture
def thresholds(repo_root):
    return load_thresholds(repo_root / "config" / "thresholds.yaml")


@pytest.mark.parametrize(
    "stress,expected",
    [
        (175.0, "PASS"),
        (290.0, "CAUTION"),
        (360.0, "FAIL"),
    ],
)
def test_static_verdicts(sample_cfg, thresholds, stress, expected):
    static = StaticResult(max_stress_mpa=stress, max_deformation_mm=0.5)
    narrative = rules.narrate_static(static, sample_cfg, thresholds)
    assert narrative.verdict == expected


def test_modal_resonance_in_band(sample_cfg, thresholds):
    modal = ModalResult(modes=[ModeResult(index=1, freq_hz=150.0)])
    narrative = rules.narrate_modal(modal, sample_cfg, thresholds)
    assert narrative.verdict == "CAUTION"
    assert any("resonance" in c.lower() for c in narrative.conclusions)


def test_modal_outside_band(sample_cfg, thresholds):
    modal = ModalResult(modes=[ModeResult(index=1, freq_hz=250.0)])
    narrative = rules.narrate_modal(modal, sample_cfg, thresholds)
    assert narrative.verdict == "PASS"


def test_executive_summary():
    from ansys_report.models import SectionVerdict

    summary = rules.build_executive_summary(
        [
            SectionVerdict(section="static", verdict="PASS"),
            SectionVerdict(section="modal", verdict="CAUTION"),
        ]
    )
    assert "CAUTION" in summary or "Overall" in summary
