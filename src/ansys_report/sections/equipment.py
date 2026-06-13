"""Static front-matter section plugins."""

from __future__ import annotations

from typing import Any

from ansys_report.config import ProjectConfig
from ansys_report.models import ProjectInventory


class _StaticSection:
    key: str
    title: str
    body: str

    def __init__(self, key: str, title: str, body: str) -> None:
        self.key = key
        self.title = title
        self.body = body

    def is_enabled(self, cfg: ProjectConfig) -> bool:
        return self.key in cfg.sections_enabled

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        return {"title": self.title, "body": self.body}

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]:
        return {}

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]:
        return {self.key: data}


class RevisionSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__(
            "revision",
            "Revision Log",
            "Automated revision entry — verify revision number before issue.",
        )


class ScopeSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__(
            "scope",
            "Scope of Analysis",
            "Structural assessment per configured enabled sections.",
        )


class SoftwareSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__("software", "Software and Tools", "")

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        return {
            "title": self.title,
            "ansys_version": cfg.ansys_version,
            "tools": ["ANSYS Workbench", "ANSYS Mechanical", "ansys-report automation"],
        }


class ReferencesSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__(
            "references",
            "References",
            "ASME BPVC, project P&ID, and customer specifications as applicable.",
        )


class EquipmentSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__("equipment", "Equipment Description", "")

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        from ansys_report.extract.metadata import extract_equipment_metadata

        meta = extract_equipment_metadata(inventory, cfg.bom_id, cfg.title)
        return {
            "title": self.title,
            **meta.model_dump(mode="json"),
        }


class ModellingSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__("modelling", "Modelling", "")

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        import os

        from ansys_report.extract.dpf_mesh import extract_mesh_quality
        from ansys_report.extract.metadata import extract_modelling_metadata, _static_system

        meta = extract_modelling_metadata(inventory)
        payload = meta.model_dump(mode="json")

        if os.getenv("ANSYS_AVAILABLE") == "1":
            static = _static_system(inventory)
            if static and static.primary_rst:
                quality = extract_mesh_quality(static.primary_rst)
                if quality:
                    payload["quality_metrics"] = quality
                    payload["mesh_quality_source"] = "dpf"

        return {"title": self.title, **payload}
