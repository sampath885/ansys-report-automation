"""EP2737 case data paths (large Ansys project lives outside the repo)."""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_CASE_ROOT = Path(__file__).resolve().parents[2] / "ansys_automation_files"


def ep2737_case_root() -> Path:
    """Root folder for EP 2737 case data (Excel, STEP, exports, reference DOCX)."""
    override = os.getenv("EP2737_CASE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_CASE_ROOT.resolve()


def ep2737_workbench_dir() -> Path:
    return ep2737_case_root() / "Structural Analysis_EP2737"


def ep2737_dp0() -> Path:
    return ep2737_workbench_dir() / "EP2737_files" / "dp0"


def ep2737_reference_docx() -> Path:
    return ep2737_case_root() / "Design Report_EP2737_UPDATED.docx"


def ep2737_rst_relpath(rst_path: Path) -> str:
    """Relative RST path for golden fixtures (from case root, forward slashes)."""
    return str(rst_path.relative_to(ep2737_case_root())).replace("\\", "/")


def ep2737_available() -> bool:
    return ep2737_workbench_dir().exists()
