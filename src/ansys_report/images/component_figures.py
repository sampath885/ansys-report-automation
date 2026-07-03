"""Discover per-component / per-material Mechanical export figures."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Aggregate result plots — not per-material component figures.
SOLUTION_AGGREGATE_STEMS = frozenset(
    {
        "total_deformation",
        "equivalent_stress",
        "equivalent_stress_flange",
        "equivalent_stress_maximum_overtime",
        "vonmises_assembly",
        "vonmises_stress",
    }
)

REACTION_KEYWORDS = ("reaction", "force_reaction", "moment_reaction")


@dataclass(frozen=True)
class ComponentFigure:
    path: Path
    label: str
    stem: str
    rel_path: str


def filename_to_material_label(stem: str) -> str:
    """Convert export stem (bs970_en19) to EP1581-style label (MAT_BS970_EN19)."""
    normalized = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return f"MAT_{normalized.upper()}"


def _is_material_stress_file(stem: str) -> bool:
    if stem in SOLUTION_AGGREGATE_STEMS:
        return False
    if stem.startswith("total_deformation"):
        return False
    if any(k in stem for k in REACTION_KEYWORDS):
        return False
    if stem.startswith("bolt_"):
        return False
    return True


def _is_reaction_file(stem: str) -> bool:
    return any(k in stem for k in REACTION_KEYWORDS)


def discover_gallery_figures(
    image_root: Path,
    analysis_folder: str,
    *,
    subfolder: str = "solution",
    category: str = "material_stress",
    filename: str | None = None,
) -> list[ComponentFigure]:
    """Return ordered component figures under *image_root/analysis_folder/subfolder*."""
    base = image_root / analysis_folder / subfolder
    if not base.is_dir():
        return []

    if filename:
        path = base / filename
        if not path.is_file():
            return []
        stem = path.stem
        return [
            ComponentFigure(
                path=path.resolve(),
                label=filename_to_material_label(stem) if category == "material_stress" else _title_label(stem),
                stem=stem,
                rel_path=str(path.relative_to(image_root)).replace("\\", "/"),
            )
        ]

    figures: list[ComponentFigure] = []
    for path in sorted(base.glob("*.png")):
        stem = path.stem
        if category == "material_stress" and not _is_material_stress_file(stem):
            continue
        if category == "reaction" and not _is_reaction_file(stem):
            continue
        figures.append(
            ComponentFigure(
                path=path.resolve(),
                label=filename_to_material_label(stem) if category == "material_stress" else _title_label(stem),
                stem=stem,
                rel_path=str(path.relative_to(image_root)).replace("\\", "/"),
            )
        )
    return figures


def _title_label(stem: str) -> str:
    return stem.replace("_", " ").title()


def shock_analysis_folder(direction_key: str) -> str:
    """Map shock direction key (plus_x) to EP2741 export folder name."""
    mapping = {
        "plus_x": "equivalent_static_analysis_posx",
        "plus_y": "equivalent_static_analysis_posy",
        "plus_z": "equivalent_static_analysis_posz",
        "minus_x": "equivalent_static_analysis_negx",
        "minus_y": "equivalent_static_analysis_negy",
        "minus_z": "equivalent_static_analysis_negz",
    }
    return mapping[direction_key]
