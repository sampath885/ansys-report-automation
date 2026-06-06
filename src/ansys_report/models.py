"""Data models for extracted results and report context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModeResult(BaseModel):
    index: int
    freq_hz: float | None = None
    participation: float | None = None


class StaticResult(BaseModel):
    max_stress_mpa: float | None = None
    max_deformation_mm: float | None = None
    reaction_force_n: float | None = None
    reaction_moment_nmm: float | None = None
    fos: float | None = None
    per_material: dict[str, float] = Field(default_factory=dict)
    manual_fields: list[str] = Field(default_factory=list)


class MeshResult(BaseModel):
    node_count: int | None = None
    element_count: int | None = None
    quality_metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    manual_fields: list[str] = Field(default_factory=list)


class ModalResult(BaseModel):
    modes: list[ModeResult] = Field(default_factory=list)
    manual_fields: list[str] = Field(default_factory=list)


class CalcRow(BaseModel):
    label: str
    symbol: str | None = None
    formula: str | None = None
    value: float | str
    unit: str | None = None
    source_ref: str | None = None
    verdict: str | None = None


class DesignCalcsResult(BaseModel):
    bolt_load: list[CalcRow] = Field(default_factory=list)
    flange_moments: list[CalcRow] = Field(default_factory=list)
    effort: list[CalcRow] = Field(default_factory=list)
    end_flange: list[CalcRow] = Field(default_factory=list)


class Narrative(BaseModel):
    executive_summary: str = ""
    observations: list[str] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    verdict: str = "PASS"
    source: str = "rules"


class ProjectInventory(BaseModel):
    project_dir: Path
    wbpj_files: list[Path] = Field(default_factory=list)
    rst_files: dict[str, Path] = Field(default_factory=dict)
    image_root: Path
    excel_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


class MissingAssets(BaseModel):
    missing_slots: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resolved: dict[str, Path] = Field(default_factory=dict)

    @property
    def has_missing(self) -> bool:
        return bool(self.missing_slots)


class SectionVerdict(BaseModel):
    section: str
    verdict: str
    observations: list[str] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)


class RenderContext(BaseModel):
    """Validated context passed to docxtpl."""

    bom_id: str
    title: str
    customer: str
    prepared_by: dict[str, str]
    checked_by: dict[str, str]
    approved_by: dict[str, str]
    ansys_version: str
    sections: dict[str, Any] = Field(default_factory=dict)
    modal: dict[str, Any] = Field(default_factory=dict)
    static: dict[str, Any] = Field(default_factory=dict)
    mesh: dict[str, Any] = Field(default_factory=dict)
    design_calcs: dict[str, Any] = Field(default_factory=dict)
    harmonic_x: dict[str, Any] = Field(default_factory=dict)
    narrative: dict[str, Any] = Field(default_factory=dict)
    images: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
