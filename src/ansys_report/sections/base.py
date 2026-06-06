"""Report section plugin protocol."""

from __future__ import annotations

from typing import Any, Protocol

from ansys_report.config import ProjectConfig
from ansys_report.models import ProjectInventory


class ReportSection(Protocol):
    key: str

    def is_enabled(self, cfg: ProjectConfig) -> bool: ...

    def extract(self, inventory: ProjectInventory, cfg: ProjectConfig) -> dict[str, Any]: ...

    def narrate(self, data: dict[str, Any], cfg: ProjectConfig) -> dict[str, Any]: ...

    def context(self, data: dict[str, Any], narrative: dict[str, Any]) -> dict[str, Any]: ...
