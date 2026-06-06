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
        return {"title": self.title, "bom_id": cfg.bom_id, "title_full": cfg.title}


class ModellingSection(_StaticSection):
    def __init__(self) -> None:
        super().__init__("modelling", "Modelling", "")

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]:
        from ansys_report.extract.dpf_mesh import extract_mesh

        rst = next(iter(inventory.rst_files.values()), None)
        mesh = extract_mesh(rst) if rst else None
        return {
            "title": self.title,
            "node_count": mesh.node_count if mesh else None,
            "element_count": mesh.element_count if mesh else None,
            "manual_fields": mesh.manual_fields if mesh else ["node_count"],
        }
