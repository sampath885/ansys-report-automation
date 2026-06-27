"""Build report figure slot maps from auto-discover export logs."""

from __future__ import annotations

import re
from pathlib import Path

from ansys_report.images.analysis_registry import analysis_name_to_family, sanitize_analysis_name

_AUTO_OK_LINE = re.compile(
    r"^OK\s+\[([^\]]+)\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)


def _normalize_log_label(label: str) -> str:
    return re.sub(r"\s*/\s*", "/", label.strip())


def _parse_log_label(label: str) -> tuple[str, str, str]:
    """Return (analysis, section, result) from a log bracket label."""
    normalized = _normalize_log_label(label)
    parts = [p.strip() for p in normalized.split("/") if p.strip()]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", parts[0]
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], parts[1], "/".join(parts[2:])


def _rel_from_absolute(exports_root: Path, raw_path: str) -> str | None:
    path = Path(raw_path.replace("\\", "/"))
    try:
        return path.relative_to(exports_root.resolve()).as_posix()
    except ValueError:
        parts = path.as_posix().split("/exports/")
        if len(parts) == 2:
            return parts[1]
    return None


def _slot_from_log_parts(family: str, section: str, result: str, rel_path: str) -> str | None:
    sec = section.lower()
    res = result.lower().strip()
    filename = Path(rel_path).name.lower()

    if family == "geometry":
        if "geometry" in res or filename == "geometry.png":
            return "cad_isometric"
        return None

    if family == "connections":
        return "modelling_contacts"

    if family == "coordinate_systems":
        return "geometry_model_orientation"

    if family == "mesh":
        if filename.startswith("mesh"):
            return "mesh_global"
        if "aspect" in filename:
            return "mesh_quality_aspect"
        if "skewness" in filename:
            return "mesh_skewness"
        if "jacobian" in filename:
            return "mesh_jacobian"
        return None

    if family == "static":
        if "loading" in sec or sec == "loading":
            if "earth gravity" in res or "gravity" in res:
                return "static_earth_gravity"
            if "fixed support" in res:
                return "static_fixed_support"
            if res == "pressure" or res.startswith("pressure"):
                return "static_pressure"
        if "solution" in sec or "solution" in rel_path:
            if "flange" in res:
                return "static_vonmises_flange"
            if "total deformation" in res:
                return "static_total_deformation"
            if "equivalent stress" in res or "von mises" in res or "von-mises" in res:
                return "static_vonmises_stress"
            if "reaction" in res:
                return "static_reaction_force"
        return None

    if family == "modal":
        if "total deformation" not in res and "total_deformation" not in filename:
            return None
        mode_match = re.search(r"total_deformation_(\d+)", filename)
        if mode_match:
            return f"modal_mode{mode_match.group(1)}"
        return "modal_mode1"

    if family.startswith("harmonic_"):
        axis = family.split("_", 1)[1]
        prefix = f"harmonic_{axis}"
        if "loading" in sec or "loading" in rel_path:
            if "acceleration" in res or "acceleration" in filename:
                return f"{prefix}_location"
        if "graphs" in sec or "graphs" in rel_path:
            if "frequency" in res or "frequency_response" in filename:
                return f"{prefix}_accel_plot"
        if "solution" in sec or "solution" in rel_path:
            if "flange" in res:
                return f"{prefix}_stress_flange"
            if "total deformation" in res or "total_deformation" in filename:
                return f"{prefix}_deformation"
            if "equivalent stress" in res or "equivalent_stress" in filename:
                return f"{prefix}_stress_asm"
        return None

    if family.startswith("shock_"):
        prefix = family
        if "solution" in sec or "solution" in rel_path:
            if "flange" in res:
                return f"{prefix}_stress_flange"
            if "total deformation" in res or "total_deformation" in filename:
                return f"{prefix}_deformation"
            if (
                "maximum over time" in res
                or "maximum_overtime" in filename
                or ("equivalent stress" in res and "maximum" in res)
            ):
                return f"{prefix}_stress_asm"
            if "equivalent stress" in res or "equivalent_stress" in filename:
                return f"{prefix}_stress_asm"
        return None

    return None


def parse_autodiscover_export_log(log_path: Path, exports_root: Path) -> dict[str, str]:
    """Parse auto-discover log into slot -> relative PNG path."""
    if not log_path.exists():
        return {}

    mapping: dict[str, str] = {}
    root = exports_root.resolve()

    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _AUTO_OK_LINE.match(line.strip())
        if not match:
            continue
        label, raw_path = match.group(1), match.group(2)
        rel = _rel_from_absolute(root, raw_path)
        if not rel:
            continue

        analysis, section, result = _parse_log_label(label)
        family = analysis_name_to_family(analysis)
        if not family:
            continue

        slot = _slot_from_log_parts(family, section, result, rel)
        if not slot:
            continue

        if slot not in mapping:
            mapping[slot] = rel

    return dict(sorted(mapping.items()))


def merge_log_map_into_resolved(
    log_path: Path,
    exports_root: Path,
    resolved: dict[str, Path],
    *,
    used_paths: set[str],
) -> dict[str, Path]:
    """Apply log-derived mappings without overwriting existing slots."""
    from ansys_report.images.auto_discover import _path_key

    for slot, rel in parse_autodiscover_export_log(log_path, exports_root).items():
        if slot in resolved:
            continue
        path = exports_root / rel
        if not path.exists():
            continue
        key = _path_key(path)
        if key in used_paths:
            continue
        resolved[slot] = path.resolve()
        used_paths.add(key)
    return resolved
