"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"
REPO = FIXTURES.parent.parent
CONFIG = REPO / "config"
TEMPLATE = REPO / "templates" / "EP1763_report_template.docx"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def template_path(repo_root) -> Path:
    tpl = repo_root / "templates" / "EP1763_report_template.docx"
    if not tpl.exists():
        from ansys_report.report.template_builder import create_minimal_template_from_scratch

        create_minimal_template_from_scratch(tpl)
    return tpl


@pytest.fixture(scope="session")
def sample_calcs_xlsx(fixtures_dir) -> Path:
    path = fixtures_dir / "sample_calcs.xlsx"
    if path.exists():
        return path
    wb = Workbook()
    ws = wb.active
    ws.title = "Bolt Load"
    ws.append(["Label", "Symbol", "Formula", "Value", "Unit", "Source", "Verdict"])
    ws.append(["FOS", "", "", 16.36, "", "ASME VIII", "ACCEPTABLE"])
    ws.append(["Ab/Am", "", "", 0.85, "", "ASME", "ACCEPTABLE"])
    wb.create_sheet("Flange Moments").append(["Label", "Value", "Verdict"])
    wb["Flange Moments"].append(["Moment M", 1250, "ACCEPTABLE"])
    wb.save(path)
    return path


@pytest.fixture(scope="session")
def tiny_png(fixtures_dir) -> Path:
    img_dir = fixtures_dir / "img"
    img_dir.mkdir(exist_ok=True)
    path = img_dir / "test.png"
    if not path.exists():
        Image.new("RGB", (1024, 768), color=(200, 200, 255)).save(path)
    return path
