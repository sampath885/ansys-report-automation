"""Resolve canonical analysis folder names to actual export folder names."""

from __future__ import annotations

from pathlib import Path

from ansys_report.images.component_figures import shock_analysis_folder
from ansys_report.images.slot_semantics import (
    analysis_root_from_rel_path,
    canonical_analysis_folder,
    is_semantic_scope_slot,
    parse_slot_semantics,
)

_GALLERY_CANONICAL_FOLDERS: frozenset[str] = frozenset(
    {
        "static_structural",
        "vibration_resistance_analysis_x",
        "vibration_resistance_analysis_y",
        "vibration_resistance_analysis_z",
        "equivalent_static_analysis_posx",
        "equivalent_static_analysis_posy",
        "equivalent_static_analysis_posz",
        "equivalent_static_analysis_negx",
        "equivalent_static_analysis_negy",
        "equivalent_static_analysis_negz",
    }
)


def all_gallery_canonical_folders() -> frozenset[str]:
    return _GALLERY_CANONICAL_FOLDERS


def resolve_gallery_folder(canonical: str, aliases: dict[str, str] | None) -> str:
    """Return actual folder name for a canonical analysis folder (or canonical if unknown)."""
    if not aliases or canonical not in _GALLERY_CANONICAL_FOLDERS:
        return canonical
    return aliases.get(canonical, canonical)


def build_folder_aliases_from_resolved(
    resolved: dict[str, Path],
    image_root: Path | None = None,
) -> dict[str, str]:
    """Infer canonical → actual folder map from resolved semantic-scope slots."""
    aliases: dict[str, str] = {}
    votes: dict[str, dict[str, int]] = {}

    for slot, path in resolved.items():
        if not is_semantic_scope_slot(slot):
            continue
        canonical = canonical_analysis_folder(slot)
        if not canonical:
            continue
        try:
            if image_root is not None:
                rel = path.relative_to(image_root.resolve()).as_posix()
            else:
                rel = path.as_posix()
        except ValueError:
            rel = path.as_posix()
        actual = analysis_root_from_rel_path(rel)
        if not actual or actual == canonical:
            continue
        bucket = votes.setdefault(canonical, {})
        bucket[actual] = bucket.get(actual, 0) + 1

    for canonical, counts in votes.items():
        best = max(counts, key=lambda name: (counts[name], name))
        aliases[canonical] = best

    return aliases


def merge_folder_aliases(*maps: dict[str, str] | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    for item in maps:
        if item:
            merged.update(item)
    return merged


def shock_canonical_folders() -> dict[str, str]:
    """Direction key → canonical folder (for documentation / tests)."""
    return {
        direction: shock_analysis_folder(direction)
        for direction in (
            "plus_x",
            "plus_y",
            "plus_z",
            "minus_x",
            "minus_y",
            "minus_z",
        )
    }


def filter_semantic_candidate_paths(unused_paths: list[str]) -> list[str]:
    """PNG paths eligible for semantic routing (exclude stable analysis types)."""
    skip_prefixes = (
        "mesh/",
        "modal/",
        "geometry/",
        "connections/",
        "coordinate_systems/",
    )
    out: list[str] = []
    for rel in unused_paths:
        lower = rel.lower().replace("\\", "/")
        if lower.startswith(skip_prefixes):
            continue
        out.append(rel)
    return sorted(out)
