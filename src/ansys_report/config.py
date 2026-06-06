"""Pydantic configuration models and YAML loaders."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

REGISTERED_SECTIONS = frozenset(
    {
        "revision",
        "scope",
        "software",
        "references",
        "equipment",
        "modelling",
        "modal",
        "static",
        "harmonic_x",
        "harmonic_y",
        "harmonic_z",
        "design_calcs",
    }
)


class PersonRole(BaseModel):
    name: str
    role: str


class MaterialConfig(BaseModel):
    name: str
    yield_mpa: float
    uts_mpa: float | None = None


class ModalConfig(BaseModel):
    num_modes: int = 6


class StaticConfig(BaseModel):
    fos_target: float = 1.5


class ProjectConfig(BaseModel):
    bom_id: str
    title: str
    customer: str
    prepared_by: PersonRole
    checked_by: PersonRole
    approved_by: PersonRole
    ansys_version: str = "2024 R2"
    project_dir: Path
    image_folder: str = "exports"
    excel_calcs: str = "design_calcs.xlsx"
    sections_enabled: list[str]
    operating_freq_hz: list[float] = Field(default_factory=lambda: [10.0, 200.0])
    materials: list[MaterialConfig] = Field(default_factory=list)
    modal: ModalConfig = Field(default_factory=ModalConfig)
    static: StaticConfig = Field(default_factory=StaticConfig)
    image_map_path: Path | None = None
    thresholds_path: Path | None = None
    template_path: Path | None = None

    @field_validator("sections_enabled")
    @classmethod
    def validate_sections(cls, v: list[str]) -> list[str]:
        unknown = set(v) - REGISTERED_SECTIONS
        if unknown:
            raise ValueError(f"Unknown sections: {sorted(unknown)}")
        return v

    @field_validator("operating_freq_hz")
    @classmethod
    def validate_freq_band(cls, v: list[float]) -> list[float]:
        if len(v) != 2 or v[0] >= v[1]:
            raise ValueError("operating_freq_hz must be a 2-element ascending list")
        return v

    @property
    def image_root(self) -> Path:
        return self.project_dir / self.image_folder

    @property
    def excel_path(self) -> Path:
        return self.project_dir / self.excel_calcs

    @property
    def primary_yield_mpa(self) -> float | None:
        return self.materials[0].yield_mpa if self.materials else None


class StressThresholds(BaseModel):
    warn_fraction_of_yield: float = 0.80
    fail_fraction_of_yield: float = 1.00


class FosThresholds(BaseModel):
    min_acceptable: float = 1.5


class ModalThresholds(BaseModel):
    resonance_margin_hz: float = 10.0


class DeformationThresholds(BaseModel):
    warn_mm: float = 1.0


class ThresholdsConfig(BaseModel):
    stress: StressThresholds = Field(default_factory=StressThresholds)
    fos: FosThresholds = Field(default_factory=FosThresholds)
    modal: ModalThresholds = Field(default_factory=ModalThresholds)
    deformation: DeformationThresholds = Field(default_factory=DeformationThresholds)


class ImageMapConfig(BaseModel):
    slots: dict[str, str]

    @classmethod
    def from_mapping(cls, mapping: dict[str, str]) -> ImageMapConfig:
        return cls(slots=mapping)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_project_config(
    config_path: Path,
    project_dir_override: Path | None = None,
) -> ProjectConfig:
    data = _load_yaml(config_path)
    if project_dir_override:
        data["project_dir"] = str(project_dir_override)
    elif "project_dir" in data:
        base = config_path.parent
        data["project_dir"] = str((base / data["project_dir"]).resolve())
    cfg = ProjectConfig(**data)
    cfg.project_dir = cfg.project_dir.resolve()
    return cfg


def load_thresholds(path: Path | None = None) -> ThresholdsConfig:
    if path is None:
        default = Path(__file__).resolve().parents[2] / "config" / "thresholds.yaml"
        path = default if default.exists() else None
    if path is None or not path.exists():
        return ThresholdsConfig()
    return ThresholdsConfig(**_load_yaml(path))


def load_image_map(path: Path) -> ImageMapConfig:
    return ImageMapConfig.from_mapping(_load_yaml(path))


def ai_enabled(no_ai: bool = False) -> bool:
    if no_ai:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))


class ValidationIssue(BaseModel):
    category: str
    message: str
    severity: str = "warning"  # warning | error


class ValidationReport(BaseModel):
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def add(self, category: str, message: str, severity: str = "warning") -> None:
        self.issues.append(ValidationIssue(category=category, message=message, severity=severity))

    def merge(self, other: ValidationReport) -> None:
        self.issues.extend(other.issues)


def validate_project_paths(cfg: ProjectConfig) -> ValidationReport:
    report = ValidationReport()
    if not cfg.project_dir.exists():
        report.add("paths", f"project_dir not found: {cfg.project_dir}", "error")
    if not cfg.image_root.exists():
        report.add("paths", f"image_folder not found: {cfg.image_root}", "warning")
    if not cfg.excel_path.exists() and "design_calcs" in cfg.sections_enabled:
        report.add("paths", f"excel_calcs not found: {cfg.excel_path}", "warning")
    if not ai_enabled() and not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        report.add("ai", "No AI API key; using rule-based narratives only", "warning")
    return report
