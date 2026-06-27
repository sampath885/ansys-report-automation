"""Resolve image_map slots to paths and InlineImage objects."""

from __future__ import annotations

import logging
from pathlib import Path

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from PIL import Image

from ansys_report.config import ImageMapConfig, ValidationReport
from ansys_report.models import MissingAssets

logger = logging.getLogger(__name__)

MIN_WIDTH_PX = 800
MIN_DPI = 72


def resolve_assets(
    image_root: Path,
    image_map: ImageMapConfig,
    check_quality: bool = True,
) -> MissingAssets:
    missing: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, Path] = {}

    for slot, rel in image_map.slots.items():
        path = image_root / rel
        if not path.exists():
            missing.append(slot)
            continue
        resolved[slot] = path.resolve()
        if check_quality:
            warnings.extend(_quality_warnings(slot, path))

    return MissingAssets(missing_slots=missing, warnings=warnings, resolved=resolved)


def build_inline_images(
    template: DocxTemplate,
    assets: MissingAssets,
    width_mm: float = 150,
) -> dict[str, InlineImage | None]:
    images: dict[str, InlineImage | None] = {}
    for slot, path in assets.resolved.items():
        try:
            images[slot] = InlineImage(template, str(path), width=Mm(width_mm))
        except Exception as exc:
            logger.warning("Failed to load image %s: %s", slot, exc)
            images[slot] = None
    return images


def assets_to_validation(missing: MissingAssets) -> ValidationReport:
    report = ValidationReport()
    for slot in missing.missing_slots:
        report.add("images", f"Missing image slot: {slot}", "warning")
    for msg in missing.errors:
        report.add("images", msg, "error")
    for msg in missing.warnings:
        report.add("images", msg, "warning")
    return report


def _quality_warnings(slot: str, path: Path) -> list[str]:
    warnings: list[str] = []
    try:
        with Image.open(path) as img:
            w, h = img.size
            if w < MIN_WIDTH_PX:
                warnings.append(f"{slot}: width {w}px below recommended {MIN_WIDTH_PX}px")
            dpi = img.info.get("dpi", (MIN_DPI, MIN_DPI))
            if isinstance(dpi, tuple) and dpi[0] < MIN_DPI:
                warnings.append(f"{slot}: DPI may be low ({dpi[0]})")
    except Exception as exc:
        warnings.append(f"{slot}: could not read image metadata ({exc})")
    return warnings
