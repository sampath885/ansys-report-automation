"""Data models for extracted results and report context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ModeResult(BaseModel):
    index: int
    freq_hz: float | None = None
    participation: float | None = None


class BodyStressRow(BaseModel):
    """Per-body peak stress from DPF (static or shock RST)."""

    body_name: str
    material: str | None = None
    max_stress_mpa: float | None = None
    max_deformation_mm: float | None = None
    location: str | None = None


class StaticResult(BaseModel):
    max_stress_mpa: float | None = None
    max_deformation_mm: float | None = None
    reaction_force_n: float | None = None
    reaction_moment_nmm: float | None = None
    fos: float | None = None
    per_material: dict[str, float] = Field(default_factory=dict)
    per_body: list[BodyStressRow] = Field(default_factory=list)
    manual_fields: list[str] = Field(default_factory=list)


class MeshResult(BaseModel):
    node_count: int | None = None
    element_count: int | None = None
    quality_metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    manual_fields: list[str] = Field(default_factory=list)


class BodyMetadata(BaseModel):
    name: str
    mass_tonne: float | None = None
    mass_kg: float | None = None
    material: str | None = None


class AssemblyMetadata(BaseModel):
    name: str = "Assembly"
    mass_tonne: float | None = None
    mass_kg: float | None = None
    cog_mm: dict[str, float] | None = None


class ContactMetadata(BaseModel):
    caption: str
    contact_type: str | None = None


class BoundaryConditionMetadata(BaseModel):
    caption: str
    bc_type: str


class LoadMetadata(BaseModel):
    load_type: str
    caption: str
    magnitude: float | None = None
    count: int | None = None


class MaterialMetadata(BaseModel):
    name: str
    youngs_modulus_gpa: float | None = None
    poissons_ratio: float | None = None
    density_kg_m3: float | None = None
    tensile_yield_mpa: float | None = None


class AnalysisMetadata(BaseModel):
    project_name: str | None = None
    solver_analysis_type: str | None = None
    antype: str | None = None
    load_steps: list[float] = Field(default_factory=list)
    bodies: list[BodyMetadata] = Field(default_factory=list)
    assembly: AssemblyMetadata | None = None
    contacts: list[ContactMetadata] = Field(default_factory=list)
    boundary_conditions: list[BoundaryConditionMetadata] = Field(default_factory=list)
    loads: list[LoadMetadata] = Field(default_factory=list)
    materials: list[MaterialMetadata] = Field(default_factory=list)
    mesh: MeshResult = Field(default_factory=MeshResult)
    source_mech_dir: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


class EquipmentMetadata(BaseModel):
    bom_id: str
    title: str
    cad_step: Path | None = None
    bodies: list[BodyMetadata] = Field(default_factory=list)
    assembly: AssemblyMetadata | None = None
    material_names: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class ModellingMetadata(BaseModel):
    project_name: str | None = None
    solver_analysis_type: str | None = None
    antype: str | None = None
    load_steps: list[float] = Field(default_factory=list)
    contacts: list[ContactMetadata] = Field(default_factory=list)
    boundary_conditions: list[BoundaryConditionMetadata] = Field(default_factory=list)
    loads: list[LoadMetadata] = Field(default_factory=list)
    materials: list[MaterialMetadata] = Field(default_factory=list)
    node_count: int | None = None
    element_count: int | None = None
    mesh_source: str | None = None
    manual_fields: list[str] = Field(default_factory=list)


class ProjectMetadata(BaseModel):
    bom_id: str
    title: str
    ansys_version: str | None = None
    cad_step: Path | None = None
    equipment: EquipmentMetadata
    modelling: ModellingMetadata
    static_analysis: AnalysisMetadata

    model_config = {"arbitrary_types_allowed": True}

    def to_json_dict(self) -> dict[str, Any]:
        def _path(p: Path | None) -> str | None:
            if p is None:
                return None
            try:
                return str(p.relative_to(Path.cwd()))
            except ValueError:
                return p.name

        def _dump(obj: BaseModel) -> dict[str, Any]:
            return obj.model_dump(mode="json")

        equipment = self.equipment.model_dump(mode="json")
        equipment["cad_step"] = _path(self.cad_step)

        static = self.static_analysis.model_dump(mode="json")
        if static.get("source_mech_dir"):
            try:
                static["source_mech_dir"] = str(Path(static["source_mech_dir"]).relative_to(Path.cwd()))
            except ValueError:
                pass

        return {
            "phase": "3_metadata",
            "bom_id": self.bom_id,
            "title": self.title,
            "ansys_version": self.ansys_version,
            "cad_step": _path(self.cad_step),
            "equipment": equipment,
            "modelling": _dump(self.modelling),
            "static_analysis": static,
        }


class ModalResult(BaseModel):
    modes: list[ModeResult] = Field(default_factory=list)
    manual_fields: list[str] = Field(default_factory=list)


class HarmonicPeakResult(BaseModel):
    peak_displacement_mm: float | None = None
    peak_frequency_hz: float | None = None
    num_frequency_sets: int | None = None
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


class AnalysisSystem(BaseModel):
    """One Workbench analysis system under dp0/SYS*."""

    key: str
    folder: str
    display_name: str
    workbench_analysis_type: str = "unknown"
    mech_dir: Path
    primary_rst: Path | None = None
    rst_files: list[Path] = Field(default_factory=list)
    project_name: str | None = None
    antype: str | None = None
    has_mcf: bool = False
    mapdl_errors: int | str | None = None

    model_config = {"arbitrary_types_allowed": True}


class ProjectInventory(BaseModel):
    project_dir: Path
    case_root: Path | None = None
    wbpj_files: list[Path] = Field(default_factory=list)
    wbpj_primary: Path | None = None
    systems: dict[str, AnalysisSystem] = Field(default_factory=dict)
    rst_files: dict[str, Path] = Field(default_factory=dict)
    image_root: Path
    excel_path: Path | None = None
    excel_bolt_preload: Path | None = None
    cad_step: Path | None = None
    geometry_scdocx: Path | None = None
    ansys_version: str | None = None
    warnings: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def to_json_dict(self) -> dict:
        """JSON-serializable inventory for Phase 1 artifacts."""

        def _p(path: Path | None) -> str | None:
            return str(path) if path else None

        return {
            "project_dir": str(self.project_dir),
            "case_root": _p(self.case_root),
            "wbpj_primary": _p(self.wbpj_primary),
            "ansys_version": self.ansys_version,
            "image_root": str(self.image_root),
            "excel_path": _p(self.excel_path),
            "excel_bolt_preload": _p(self.excel_bolt_preload),
            "cad_step": _p(self.cad_step),
            "geometry_scdocx": _p(self.geometry_scdocx),
            "warnings": self.warnings,
            "systems": {
                key: {
                    "key": sys.key,
                    "folder": sys.folder,
                    "display_name": sys.display_name,
                    "workbench_analysis_type": sys.workbench_analysis_type,
                    "mech_dir": str(sys.mech_dir),
                    "primary_rst": _p(sys.primary_rst),
                    "rst_files": [str(p) for p in sys.rst_files],
                    "project_name": sys.project_name,
                    "antype": sys.antype,
                    "has_mcf": sys.has_mcf,
                    "mapdl_errors": sys.mapdl_errors,
                }
                for key, sys in self.systems.items()
            },
        }


class MissingAssets(BaseModel):
    missing_slots: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
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
