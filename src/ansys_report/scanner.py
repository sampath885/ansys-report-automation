"""Discover Workbench project inputs under project_dir."""

from __future__ import annotations

import logging
from pathlib import Path

from ansys_report.models import ProjectInventory

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_DIRS = ("exports", "report_assets", "images")


def scan_project(project_dir: Path, image_folder: str, excel_calcs: str) -> ProjectInventory:
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise FileNotFoundError(
            f"project_dir not found: {project_dir}. "
            "Point --project-dir at your Workbench project folder."
        )

    wbpj_files = sorted(project_dir.glob("*.wbpj"))
    rst_files: dict[str, Path] = {}

    for rst in project_dir.rglob("*.rst"):
        rel = rst.relative_to(project_dir)
        parts = rel.parts
        system = "default"
        if "dp0" in parts:
            idx = parts.index("dp0")
            if idx + 1 < len(parts):
                system = parts[idx + 1]
        elif len(parts) >= 2:
            system = parts[-2]
        if system not in rst_files:
            rst_files[system] = rst

    image_root = project_dir / image_folder
    if not image_root.exists():
        for name in DEFAULT_EXPORT_DIRS:
            candidate = project_dir / name
            if candidate.exists():
                image_root = candidate
                logger.info("Using image root: %s", image_root)
                break

    excel_path = project_dir / excel_calcs
    if not excel_path.exists():
        excel_path = None

    if not rst_files:
        logger.warning(
            "No .rst found under %s; run the solve or check project_dir.", project_dir
        )

    return ProjectInventory(
        project_dir=project_dir,
        wbpj_files=wbpj_files,
        rst_files=rst_files,
        image_root=image_root,
        excel_path=excel_path,
    )
