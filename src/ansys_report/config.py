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
        "loads",
        "materials",
        "modal",
        "static",
        "harmonic_x",
        "harmonic_y",
        "harmonic_z",
        "shock",
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
    elongation_pct: float | None = 30.0
    static_allowable_mpa: float | None = None
    fatigue_allowable_mpa: float | None = None


class EquipmentSpecConfig(BaseModel):
    part_name: str = "Welded plane Pipe Flange"
    material_grade: str = "ASTM A 182 F32100"
    drawing_mass_kg: str = "1.94±3%"
    fe_mass_note: str = "Model Mass (Excluding Extended pipes & Counter Flanges)"
    # Verified design centre of gravity [x, y, z] in mm. When set, overrides the
    # raw CAERep solver centroid (which references the global origin, not the
    # drawing datum) in the Centre of Gravity table.
    verified_cog_mm: list[float] | None = None


class BoltConfig(BaseModel):
    count: int = 8
    tensile_stress_area_mm2: float = 115.0
    shear_stress_area_mm2: float = 100.0
    report_yield_mpa: float = 205.0
    # Used only when extraction_mode is "step". Stress extraction uses static.load_step separately.
    load_step: int = 1
    extraction_mode: str = "envelope"
    static_extraction_mode: str | None = None
    shock_extraction_mode: str = "envelope"
    uniform_axial_from_preload: bool = True
    sort_by_position: bool = True
    shock_sort_by_position: bool = False


class ModalConfig(BaseModel):
    num_modes: int = 6


class StaticConfig(BaseModel):
    fos_target: float = 1.5


class MeshQualityCriterion(BaseModel):
    operator: str
    limit: float


class MeshQualityCriteriaConfig(BaseModel):
    aspect_ratio: MeshQualityCriterion = Field(
        default_factory=lambda: MeshQualityCriterion(operator="<", limit=10.0)
    )
    skewness: MeshQualityCriterion = Field(
        default_factory=lambda: MeshQualityCriterion(operator="<", limit=0.31)
    )
    jacobian_ratio: MeshQualityCriterion = Field(
        default_factory=lambda: MeshQualityCriterion(operator=">", limit=0.97)
    )
    element_quality: MeshQualityCriterion = Field(
        default_factory=lambda: MeshQualityCriterion(operator=">=", limit=0.77)
    )
    max_corner_angle_deg: MeshQualityCriterion = Field(
        default_factory=lambda: MeshQualityCriterion(operator="<=", limit=100.0)
    )


class ProjectConfig(BaseModel):
    bom_id: str
    title: str
    customer: str
    prepared_by: PersonRole
    checked_by: PersonRole
    approved_by: PersonRole
    ansys_version: str = "2024 R2"
    project_dir: Path
    case_root: Path | None = None
    image_folder: str = "exports"
    excel_calcs: str = "design_calcs.xlsx"
    excel_bolt_preload: str | None = None
    excel_map_path: Path | None = None
    section_content_path: Path | None = None
    template_path: Path | None = None
    style_shell_path: Path | None = None
    reference_layout_path: Path | None = None
    use_reference_front_matter: bool = True
    use_word_table_data: bool = False
    report_defaults_path: Path | None = None
    use_dpf_golden_fallback: bool = False
    standards_tables_path: Path | None = None
    skip_images: bool = False
    sections_enabled: list[str]
    operating_freq_hz: list[float] = Field(default_factory=lambda: [10.0, 200.0])
    materials: list[MaterialConfig] = Field(default_factory=list)
    equipment_spec: EquipmentSpecConfig = Field(default_factory=EquipmentSpecConfig)
    bolts: BoltConfig = Field(default_factory=BoltConfig)
    mesh_quality_criteria: MeshQualityCriteriaConfig = Field(default_factory=MeshQualityCriteriaConfig)
    modal: ModalConfig = Field(default_factory=ModalConfig)
    static: StaticConfig = Field(default_factory=StaticConfig)
    image_map_path: Path | None = None
    image_match_rules_path: Path | None = None
    image_resolve_mode: str = "hybrid"
    thresholds_path: Path | None = None

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
        folder = Path(self.image_folder)
        if folder.is_absolute():
            return folder
        root = self.case_root if self.case_root else self.project_dir
        return root / self.image_folder

    @property
    def excel_path(self) -> Path:
        workbook = Path(self.excel_calcs)
        if workbook.is_absolute():
            return workbook
        root = self.case_root if self.case_root else self.project_dir
        return root / self.excel_calcs

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
    if data.get("case_root"):
        base = config_path.parent
        data["case_root"] = str((base / data["case_root"]).resolve())
    if data.get("excel_map_path"):
        base = config_path.parent
        data["excel_map_path"] = str((base / data["excel_map_path"]).resolve())
    if data.get("template_path"):
        base = config_path.parent
        data["template_path"] = str((base / data["template_path"]).resolve())
    if data.get("style_shell_path"):
        base = config_path.parent
        data["style_shell_path"] = str((base / data["style_shell_path"]).resolve())
    if data.get("reference_layout_path"):
        base = config_path.parent
        data["reference_layout_path"] = str((base / data["reference_layout_path"]).resolve())
    if data.get("standards_tables_path"):
        base = config_path.parent
        data["standards_tables_path"] = str((base / data["standards_tables_path"]).resolve())
    if data.get("report_defaults_path"):
        base = config_path.parent
        data["report_defaults_path"] = str((base / data["report_defaults_path"]).resolve())
    if data.get("section_content_path"):
        base = config_path.parent
        data["section_content_path"] = str((base / data["section_content_path"]).resolve())
    if data.get("image_map_path"):
        base = config_path.parent
        data["image_map_path"] = str((base / data["image_map_path"]).resolve())
    if data.get("image_match_rules_path"):
        base = config_path.parent
        data["image_match_rules_path"] = str((base / data["image_match_rules_path"]).resolve())
    cfg = ProjectConfig(**data)
    cfg.project_dir = cfg.project_dir.resolve()
    if cfg.case_root:
        cfg.case_root = cfg.case_root.resolve()
    return cfg


def load_thresholds(path: Path | None = None) -> ThresholdsConfig:
    if path is None:
        default = Path(__file__).resolve().parents[2] / "config" / "thresholds.yaml"
        path = default if default.exists() else None
    if path is None or not path.exists():
        return ThresholdsConfig()
    return ThresholdsConfig(**_load_yaml(path))


def load_image_map(path: Path) -> ImageMapConfig:
    data = _load_yaml(path)
    if "slots" in data and isinstance(data["slots"], dict):
        slots = {str(k): str(v) for k, v in data["slots"].items()}
    else:
        slots = {str(k): str(v) for k, v in data.items() if isinstance(v, str)}
    return ImageMapConfig(slots=slots)


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
