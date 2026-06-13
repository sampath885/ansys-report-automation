"""Loads and materials section plugins — live CAERep / MatML extraction."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.extract.metadata import extract_analysis_metadata, _static_system
from ansys_report.models import ProjectInventory


class LoadsSection:
    key = "loads"
    title = "Loads & Boundary Conditions"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        static = _static_system(inventory)
        if static is None:
            return {"title": self.title, "loads": [], "boundary_conditions": [], "contacts": []}
        analysis = extract_analysis_metadata(static.mech_dir)
        return {
            "title": self.title,
            "project_name": analysis.project_name,
            "solver_analysis_type": analysis.solver_analysis_type,
            "load_steps": analysis.load_steps,
            "loads": [load.model_dump(mode="json") for load in analysis.loads],
            "boundary_conditions": [bc.model_dump(mode="json") for bc in analysis.boundary_conditions],
            "contacts": [contact.model_dump(mode="json") for contact in analysis.contacts],
            "source": "caerep",
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        return {}

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {self.key: data}


class MaterialsSection:
    key = "materials"
    title = "Material Properties & Static allowable Strength"

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        static = _static_system(inventory)
        materials: list[dict[str, Any]] = []
        if static is not None:
            analysis = extract_analysis_metadata(static.mech_dir)
            materials = [mat.model_dump(mode="json") for mat in analysis.materials]

        return {
            "title": self.title,
            "materials": materials,
            "configured_materials": [mat.model_dump(mode="json") for mat in cfg.materials],
            "source": "caerep" if materials else "config",
        }

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        return {}

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {self.key: data}
