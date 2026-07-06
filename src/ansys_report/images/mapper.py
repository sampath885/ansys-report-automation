"""Resolve image_map slots to paths and InlineImage objects."""

from __future__ import annotations

import logging
from pathlib import Path

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from PIL import Image

from ansys_report.config import ImageMapConfig, ValidationReport
from ansys_report.images.analysis_registry import (
    alternate_map_paths,
    folder_markers_for_slot,
    resolve_export_folder,
    resolve_file_variant_in_folder,
)
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
        path = _resolve_mapped_path(image_root, slot, rel)
        if path is None:
            missing.append(slot)
            continue
        resolved[slot] = path
        if check_quality:
            warnings.extend(_quality_warnings(slot, path))

    return MissingAssets(missing_slots=missing, warnings=warnings, resolved=resolved)


def _resolve_mapped_path(image_root: Path, slot: str, rel: str) -> Path | None:
    """Resolve image_map path, trying registry folder and file aliases when absent."""
    rel_norm = rel.replace("\\", "/")
    candidates: list[str] = []
    seen: set[str] = set()
    for cand in (rel_norm, *alternate_map_paths(slot, rel_norm)):
        if cand not in seen:
            seen.add(cand)
            candidates.append(cand)

    for cand in candidates:
        path = image_root / cand
        if path.is_file():
            return path.resolve()
        variant = _resolve_variant_under_mapped_path(image_root, slot, cand)
        if variant is not None:
            logger.debug("Resolved %s via variant %s (map had %s)", slot, variant, rel)
            return variant

    return _resolve_tail_across_folders(image_root, slot, rel_norm)


def _resolve_variant_under_mapped_path(image_root: Path, slot: str, rel: str) -> Path | None:
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    folder_name = resolve_export_folder(image_root, parts[0])
    folder = image_root / folder_name
    if not folder.is_dir():
        return None
    tail = "/".join(parts[1:])
    return resolve_file_variant_in_folder(folder, tail)


def _resolve_tail_across_folders(image_root: Path, slot: str, rel: str) -> Path | None:
    parts = rel.replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    tail = "/".join(parts[1:])
    folder_names: list[str] = []
    for name in (parts[0], resolve_export_folder(image_root, parts[0])):
        if name and name not in folder_names:
            folder_names.append(name)
    for marker in folder_markers_for_slot(slot):
        token = marker.strip("/").split("/")[0]
        if token and token not in folder_names:
            folder_names.append(token)

    for folder_name in folder_names:
        folder = image_root / folder_name
        if not folder.is_dir():
            continue
        variant = resolve_file_variant_in_folder(folder, tail)
        if variant is not None:
            logger.debug("Resolved %s via folder %s tail %s (map had %s)", slot, folder_name, tail, rel)
            return variant
    return None


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
