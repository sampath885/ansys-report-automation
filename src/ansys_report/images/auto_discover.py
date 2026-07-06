"""Match auto-discover Mechanical export folders to report figure slots."""

from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ansys_report.config import ImageMapConfig
from ansys_report.images.analysis_registry import (
    infer_folder_keywords_for_slot,
    path_allowed_for_slot,
)
from ansys_report.models import MissingAssets

logger = logging.getLogger(__name__)

_LOG_LINE = re.compile(
    r"^OK\s+\[[^\]]+\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)
_MANIFEST_LOG_LINE = re.compile(
    r"^OK\s+\[([^\]]+)\]\s+->\s+(.+\.png)\s*$",
    re.IGNORECASE,
)


class ImageMatchRule(BaseModel):
    path: str | None = None
    path_glob: str | None = None
    folder_keywords: list[str] = Field(default_factory=list)
    subpath: str = ""
    file: str | None = None
    exclude_keywords: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class ImageMatchRulesConfig(BaseModel):
    version: int = 1
    rules: dict[str, ImageMatchRule] = Field(default_factory=dict)


def load_image_match_rules(path: Path) -> ImageMatchRulesConfig:
    import yaml

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    rules_raw = data.get("rules", data)
    rules: dict[str, ImageMatchRule] = {}
    if isinstance(rules_raw, dict):
        for key, value in rules_raw.items():
            if isinstance(value, dict):
                rules[str(key)] = ImageMatchRule(**value)
            elif isinstance(value, str):
                rules[str(key)] = ImageMatchRule(path=value)
    return ImageMatchRulesConfig(version=int(data.get("version", 1)), rules=rules)


def scan_image_folder(image_root: Path) -> list[str]:
    """Return POSIX relative paths for every PNG under image_root."""
    if not image_root.exists():
        return []
    paths: list[str] = []
    for path in sorted(image_root.rglob("*.png")):
        try:
            rel = path.relative_to(image_root).as_posix()
        except ValueError:
            continue
        paths.append(rel)
    return paths


def parse_auto_discover_log(log_path: Path) -> dict[str, str]:
    """Parse auto_discover_log.txt entries into basename -> relative path hints."""
    if not log_path.exists():
        return {}
    hints: dict[str, str] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _LOG_LINE.match(line.strip())
        if not match:
            continue
        full = match.group(1).replace("\\", "/")
        name = Path(full).name
        hints[name] = full
    return hints


def parse_manifest_export_log(log_path: Path, exports_root: Path) -> dict[str, str]:
    """Parse manifest export log lines ``OK [slot] -> path`` into slot -> relative path."""
    if not log_path.exists():
        return {}
    mapping: dict[str, str] = {}
    root = exports_root.resolve()
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _MANIFEST_LOG_LINE.match(line.strip())
        if not match:
            continue
        slot, raw_path = match.group(1).strip(), match.group(2).replace("\\", "/")
        path = Path(raw_path)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            parts = path.as_posix().split("/exports/")
            if len(parts) == 2:
                rel = parts[1]
            else:
                continue
        mapping[slot] = rel
    return mapping


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _path_key(path: Path | str, image_root: Path | None = None) -> str:
    candidate = Path(path)
    if not candidate.is_absolute() and image_root is not None:
        candidate = image_root / candidate
    return str(candidate.resolve()).lower()


def _path_tokens(rel_path: str) -> set[str]:
    return {token for token in re.split(r"[/_\-\s]+", rel_path.lower()) if token}


def _slot_priority(slot: str) -> tuple[int, str]:
    """Deterministic resolve order: equipment first, shock last."""
    order = [
        ("cad_", 10),
        ("geometry_", 10),
        ("mesh_", 20),
        ("modelling_", 25),
        ("static_earth", 30),
        ("static_fixed", 31),
        ("static_pressure", 32),
        ("static_total", 33),
        ("static_vonmises_stress", 34),
        ("static_vonmises_flange", 35),
        ("static_reaction", 36),
        ("modal_mode", 40),
        ("harmonic_x_", 50),
        ("harmonic_y_", 51),
        ("harmonic_z_", 52),
        ("shock_plus_x_", 60),
        ("shock_plus_y_", 61),
        ("shock_plus_z_", 62),
        ("shock_minus_x_", 63),
        ("shock_minus_y_", 64),
        ("shock_minus_z_", 65),
    ]
    for prefix, rank in order:
        if slot.startswith(prefix) or slot == prefix.rstrip("_"):
            return rank, slot
    return 99, slot


def _sort_slots(slots: list[str]) -> list[str]:
    return sorted(slots, key=_slot_priority)


def _is_flange_stress_slot(slot: str) -> bool:
    return slot.endswith("_stress_flange") or slot.endswith("_vonmises_flange")


def _is_assembly_stress_slot(slot: str) -> bool:
    return slot.endswith("_stress_asm") or slot.endswith("_vonmises_stress")


def _stress_filename_for_slot(slot: str) -> str | None:
    if _is_flange_stress_slot(slot):
        return "solution/equivalent_stress_flange.png"
    if _is_assembly_stress_slot(slot):
        if slot.startswith("shock_"):
            return "solution/equivalent_stress_maximum_overtime.png"
        return "solution/equivalent_stress.png"
    return None


def infer_rule_from_slot(slot: str) -> ImageMatchRule | None:
    """Build a best-effort match rule from a slot name (project-agnostic)."""
    s = slot.lower().strip()
    if not s:
        return None

    if s == "cad_isometric":
        return ImageMatchRule(path="geometry/geometry.png")
    if s == "cad_section":
        return ImageMatchRule(path_glob="connections/*connections*.png")
    if s == "geometry_model_orientation":
        return ImageMatchRule(path_glob="coordinate_systems/*coordinate*.png")
    if s == "model_orientation_gravity":
        return ImageMatchRule(
            folder_keywords=["static_structural"],
            file="loading/standard_earth_gravity.png",
            exclude_keywords=["modal", "harmonic", "vibration", "shock", "transient", "equivalent_static"],
        )

    if s == "mesh_global":
        return ImageMatchRule(path_glob="mesh/mesh*.png")
    if s.startswith("mesh_"):
        metric = s.replace("mesh_quality_", "").replace("mesh_", "")
        return ImageMatchRule(folder_keywords=["mesh"], file=f"{metric}.png")

    if s == "modelling_contacts":
        return ImageMatchRule(path_glob="connections/*connections*.png")

    if s.startswith("static_"):
        load_files = {
            "earth_gravity": "loading/standard_earth_gravity.png",
            "fixed_support": "loading/fixed_support.png",
            "pressure": "loading/pressure.png",
            "total_deformation": "solution/total_deformation.png",
            "vonmises_stress": "solution/equivalent_stress.png",
            "vonmises_flange": "solution/equivalent_stress_flange.png",
            "reaction_force": "solution/reaction_force.png",
        }
        tail = s[len("static_") :]
        file_name = load_files.get(tail)
        if file_name:
            exclude = ["modal", "harmonic", "vibration", "shock", "transient", "equivalent_static"]
            return ImageMatchRule(
                folder_keywords=["static_structural"],
                file=file_name,
                exclude_keywords=exclude,
            )

    mode_match = re.match(r"modal_mode(\d+)$", s)
    if mode_match:
        mode_no = int(mode_match.group(1))
        file_name = (
            "solution/total_deformation.png"
            if mode_no == 1
            else f"solution/total_deformation_{mode_no}.png"
        )
        return ImageMatchRule(folder_keywords=["modal"], file=file_name)

    harmonic_match = re.match(r"harmonic_([xyz])_(.+)$", s)
    if harmonic_match:
        axis = harmonic_match.group(1)
        tail = harmonic_match.group(2)
        file_map = {
            "location": "loading/acceleration.png",
            "accel_plot": "solution/graphs/frequency_response.png",
            "deformation": "solution/total_deformation.png",
            "stress_asm": "solution/equivalent_stress.png",
            "stress_flange": "solution/equivalent_stress_flange.png",
        }
        file_name = file_map.get(tail)
        folder_keywords = infer_folder_keywords_for_slot(f"harmonic_{axis}_deformation")
        if file_name and folder_keywords:
            return ImageMatchRule(
                folder_keywords=folder_keywords,
                file=file_name,
                exclude_keywords=["modal_modal"],
            )

    shock_match = re.match(r"shock_(plus|minus)_([xyz])_(.+)$", s)
    if shock_match:
        sign, axis, tail = shock_match.groups()
        file_map = {
            "deformation": "solution/total_deformation.png",
            "stress_asm": "solution/equivalent_stress_maximum_overtime.png",
            "stress_flange": "solution/equivalent_stress_flange.png",
        }
        file_name = file_map.get(tail)
        if tail == "stress_asm":
            file_name = "solution/equivalent_stress.png"
        family = f"shock_{sign}_{axis}"
        folder_keywords = infer_folder_keywords_for_slot(f"{family}_deformation")
        if file_name and folder_keywords:
            return ImageMatchRule(folder_keywords=folder_keywords, file=file_name)

    return None


def _score_path_for_slot(slot: str, rel_path: str) -> int:
    """Heuristic score for matching an export path to a logical figure slot."""
    if not path_allowed_for_slot(slot, rel_path):
        return -999

    s = slot.lower()
    p = rel_path.lower()
    tokens = _path_tokens(rel_path)
    score = 0

    families: list[tuple[str, int]] = []
    if s.startswith("static_") or s.startswith("modelling_"):
        families.extend([("static", 12), ("structural", 10)])
    if s.startswith("modal_"):
        families.append(("modal", 14))
    if s.startswith("harmonic_"):
        families.extend([("harmonic", 12), ("vibration", 12)])
    if s.startswith("shock_"):
        families.extend([("shock", 12), ("transient", 10), ("equivalent", 8)])
    if s.startswith("mesh_") or s == "modelling_contacts":
        families.append(("mesh", 8))
    if s.startswith("cad_") or s.startswith("geometry_"):
        families.append(("geometry", 12))
    if s == "modelling_contacts":
        families.append(("connection", 12))

    for token, points in families:
        if token in p or token in tokens:
            score += points

    for axis in "xyz":
        axis_refs = (
            f"harmonic_{axis}",
            f"_{axis}_",
            f"plus_{axis}",
            f"minus_{axis}",
            f"_{axis}_direction",
        )
        if any(ref in s for ref in axis_refs):
            if axis in tokens or f"{axis}_direction" in p or f"_{axis}_" in p:
                score += 18
            for other in "xyz":
                if other != axis and (other in tokens or f"{other}_direction" in p):
                    score -= 12

    if "plus" in s or "plus_" in s:
        for token in ("posx", "posy", "posz", "plus_x", "plus_y", "plus_z"):
            if token in p:
                score += 40
        if "minus" in tokens or "neg" in p:
            score -= 40
        for wrong in ("negx", "negy", "negz", "minus_x", "minus_y", "minus_z"):
            if wrong in p:
                score -= 40
    if "minus" in s:
        for token in ("negx", "negy", "negz", "minus_x", "minus_y", "minus_z"):
            if token in p:
                score += 40
        for wrong in ("posx", "posy", "posz", "plus_x", "plus_y", "plus_z"):
            if wrong in p:
                score -= 40

    mode_match = re.search(r"modal_mode(\d+)", s)
    if mode_match:
        mode_no = int(mode_match.group(1))
        if mode_no == 1 and p.endswith("solution/total_deformation.png"):
            score += 25
        elif p.endswith(f"solution/total_deformation_{mode_no}.png"):
            score += 25
        elif "total_deformation" in p:
            score += 5

    if "deformation" in s and "total_deformation" in p:
        score += 20
    if ("stress" in s or "vonmises" in s) and (
        "equivalent_stress" in p or "von_mises" in p or "vonmises" in p
    ):
        score += 20

    if _is_flange_stress_slot(s):
        if "flange" in p:
            score += 30
        if "maximum_overtime" in p:
            score -= 25
        if p.endswith("equivalent_stress.png"):
            score -= 20
    elif _is_assembly_stress_slot(s):
        if "maximum_overtime" in p and s.startswith("shock_"):
            score += 30
        if "flange" in p:
            score -= 30
        if p.endswith("equivalent_stress.png"):
            score += 15

    if "accel" in s and ("frequency_response" in p or "acceleration" in p):
        score += 20
    if "location" in s and ("loading" in p or "acceleration" in p):
        score += 12
        if "modal_modal" in p:
            score -= 50
    if "earth_gravity" in s and "gravity" in p:
        score += 20
    if "fixed_support" in s and "fixed_support" in p:
        score += 20
    if "pressure" in s and "pressure" in p:
        score += 20
        if "static_structural" in p:
            score += 30
        if "equivalent_static" in p:
            score -= 50
    if s == "mesh_global" and p.startswith("mesh/") and "mesh" in Path(p).name:
        score += 20
    if s.startswith("mesh_") and s.replace("mesh_quality_", "").replace("mesh_", "") in p:
        score += 15
    if s == "cad_isometric" and p.endswith("geometry/geometry.png"):
        score += 40
    if s == "cad_section" and "connections" in p:
        score += 35
    if s == "geometry_model_orientation" and "coordinate" in p:
        score += 35
    if s == "model_orientation_gravity" and "standard_earth_gravity" in p and "static_structural" in p:
        score += 45

    if "graphs/" in p and "accel" in s:
        score += 8
    if "loading/" in p and any(k in s for k in ("gravity", "support", "pressure", "location")):
        score += 6

    return score


def _available_paths(image_root: Path, indexed_paths: list[str], used_paths: set[str]) -> list[str]:
    return [
        rel
        for rel in indexed_paths
        if _path_key(rel, image_root) not in used_paths
    ]


def _resolve_slot_by_scoring(
    slot: str,
    image_root: Path,
    indexed_paths: list[str],
    *,
    used_paths: set[str],
    min_score: int = 18,
) -> Path | None:
    candidates = _available_paths(image_root, indexed_paths, used_paths)
    ranked = sorted(
        ((rel, _score_path_for_slot(slot, rel)) for rel in candidates),
        key=lambda item: (-item[1], item[0].count("/"), len(item[0]), item[0].lower()),
    )
    if not ranked or ranked[0][1] < min_score:
        return None
    best_rel, best_score = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == best_score:
        logger.debug("Ambiguous image match for %s: %s vs %s", slot, ranked[0][0], ranked[1][0])
    path = image_root / best_rel
    return path.resolve() if path.exists() else None


def _matches_rule(rel_path: str, rule: ImageMatchRule, *, slot: str = "") -> bool:
    rel_lower = rel_path.lower()
    if slot and not path_allowed_for_slot(slot, rel_path):
        return False
    if rule.exclude_keywords and any(kw.lower() in rel_lower for kw in rule.exclude_keywords):
        return False

    if rule.path:
        return rel_lower == _normalize_rel(rule.path).lower()

    if rule.path_glob:
        return fnmatch.fnmatch(rel_lower, _normalize_rel(rule.path_glob).lower())

    if rule.folder_keywords:
        if not all(kw.lower() in rel_lower for kw in rule.folder_keywords):
            return False
        if rule.file:
            target = _normalize_rel(rule.file).lower()
            if rule.subpath:
                target = f"{_normalize_rel(rule.subpath).lower().rstrip('/')}/{target}"
            return rel_lower.endswith(target) or rel_lower == target
        return True

    return False


def _pick_best_match(
    candidates: list[str],
    rule: ImageMatchRule,
    *,
    slot: str = "",
) -> str | None:
    if not candidates:
        return None
    if rule.path:
        norm = _normalize_rel(rule.path).lower()
        for candidate in candidates:
            if candidate.lower() == norm:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    if slot:
        return max(
            candidates,
            key=lambda p: (
                _score_path_for_slot(slot, p),
                -p.count("/"),
                -len(p),
                p.lower(),
            ),
        )
    return sorted(candidates, key=lambda p: (p.count("/"), len(p), p.lower()))[0]


def resolve_slot_with_rules(
    slot: str,
    rule: ImageMatchRule,
    image_root: Path,
    indexed_paths: list[str],
    *,
    used_paths: set[str],
) -> Path | None:
    available = _available_paths(image_root, indexed_paths, used_paths)
    matches = [rel for rel in available if _matches_rule(rel, rule, slot=slot)]
    chosen = _pick_best_match(matches, rule, slot=slot)
    if not chosen:
        return None
    path = image_root / chosen
    return path.resolve() if path.exists() else None


def resolve_slot_for_exports(
    slot: str,
    image_root: Path,
    indexed_paths: list[str],
    rules: ImageMatchRulesConfig | None = None,
    *,
    used_paths: set[str] | None = None,
) -> Path | None:
    """Resolve one slot using YAML rules, inferred rules, then scoring."""
    used = used_paths if used_paths is not None else set()
    candidates: list[ImageMatchRule] = []
    if rules and rules.rules.get(slot):
        candidates.append(rules.rules[slot])
    inferred = infer_rule_from_slot(slot)
    if inferred is not None:
        candidates.append(inferred)

    seen_signatures: set[tuple] = set()
    for rule in candidates:
        signature = (
            rule.path,
            rule.path_glob,
            tuple(rule.folder_keywords),
            rule.file,
            rule.subpath,
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        path = resolve_slot_with_rules(slot, rule, image_root, indexed_paths, used_paths=used)
        if path is not None:
            return path

    return _resolve_slot_by_scoring(slot, image_root, indexed_paths, used_paths=used)


def _duplicate_path_warnings(resolved: dict[str, Path]) -> list[str]:
    by_path: dict[str, list[str]] = {}
    for slot, path in resolved.items():
        by_path.setdefault(_path_key(path), []).append(slot)
    warnings: list[str] = []
    for slots in by_path.values():
        if len(slots) > 1:
            warnings.append(f"Duplicate image path shared by slots: {', '.join(sorted(slots))}")
    return warnings


def resolve_assets_auto_discover(
    image_root: Path,
    rules: ImageMatchRulesConfig,
    slots: list[str] | None = None,
    check_quality: bool = True,
    quality_checker=None,
    *,
    used_paths: set[str] | None = None,
) -> MissingAssets:
    from ansys_report.images.mapper import _quality_warnings

    target_slots = _sort_slots(slots if slots is not None else sorted(rules.rules.keys()))
    indexed = scan_image_folder(image_root)
    missing: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, Path] = {}
    used = set(used_paths or [])

    for slot in target_slots:
        path = resolve_slot_for_exports(slot, image_root, indexed, rules, used_paths=used)
        if path is None:
            missing.append(slot)
            continue
        resolved[slot] = path
        used.add(_path_key(path))
        if check_quality:
            checker = quality_checker or _quality_warnings
            warnings.extend(checker(slot, path))

    warnings.extend(_duplicate_path_warnings(resolved))
    return MissingAssets(missing_slots=missing, warnings=warnings, resolved=resolved)


def resolve_assets_smart(
    image_root: Path,
    *,
    slots: list[str] | None = None,
    image_map: ImageMapConfig | None = None,
    rules: ImageMatchRulesConfig | None = None,
    mode: str = "hybrid",
    check_quality: bool = True,
) -> MissingAssets:
    """Resolve figure slots using exact map, auto-discover rules, or both."""
    from ansys_report.images.mapper import resolve_assets

    mode = (mode or "hybrid").lower()
    if mode not in {"exact", "auto", "hybrid"}:
        raise ValueError(f"Unknown image_resolve_mode: {mode}")

    requested = list(slots or [])
    if not requested:
        if image_map:
            requested.extend(image_map.slots.keys())
        if rules:
            requested.extend(rules.rules.keys())
        requested = sorted(set(requested))

    resolved: dict[str, Path] = {}
    warnings: list[str] = []
    used_paths: set[str] = set()

    if mode in {"exact", "hybrid"} and image_map and image_map.slots:
        exact = resolve_assets(image_root, image_map, check_quality=check_quality)
        for slot, path in exact.resolved.items():
            resolved[slot] = path
            used_paths.add(_path_key(path))
        warnings.extend(exact.warnings)

    if mode in {"exact", "auto", "hybrid"}:
        _apply_log_map(image_root, requested, resolved, used_paths)
        pending = [slot for slot in _sort_slots(requested) if slot not in resolved]
    else:
        pending = [slot for slot in _sort_slots(requested) if slot not in resolved]

    if mode in {"auto", "hybrid"}:
        auto = resolve_assets_auto_discover(
            image_root,
            rules or ImageMatchRulesConfig(),
            slots=pending or None,
            check_quality=check_quality,
            used_paths=used_paths,
        )
        resolved.update(auto.resolved)
        used_paths.update(_path_key(path) for path in auto.resolved.values())
        warnings.extend(auto.warnings)
        pending = [slot for slot in requested if slot not in resolved]

    missing_after = [slot for slot in requested if slot not in resolved]

    from ansys_report.images.image_validation import validate_resolved_images

    validation_errors, validation_warnings = validate_resolved_images(resolved, image_root)
    warnings.extend(validation_warnings)
    errors: list[str] = []
    errors.extend(validation_errors)

    seen: set[str] = set()
    unique_warnings: list[str] = []
    for msg in warnings:
        if msg not in seen:
            seen.add(msg)
            unique_warnings.append(msg)

    _apply_image_slot_aliases(resolved)

    return MissingAssets(
        missing_slots=missing_after,
        warnings=unique_warnings,
        errors=errors,
        resolved=resolved,
    )


_IMAGE_SLOT_ALIASES: dict[str, str] = {
    "model_orientation_gravity": "static_earth_gravity",
}


def _apply_image_slot_aliases(resolved: dict[str, Path]) -> None:
    for alias, source in _IMAGE_SLOT_ALIASES.items():
        if alias not in resolved and source in resolved:
            resolved[alias] = resolved[source]


def _apply_log_map(
    image_root: Path,
    requested: list[str],
    resolved: dict[str, Path],
    used_paths: set[str],
) -> None:
    """Fill slots from auto_discover_log.txt when present."""
    log_path = image_root / "auto_discover_log.txt"
    if not log_path.exists():
        return
    from ansys_report.images.log_slot_mapper import parse_autodiscover_export_log

    log_map = parse_autodiscover_export_log(log_path, image_root)
    for slot in _sort_slots(requested):
        if slot in resolved:
            continue
        rel = log_map.get(slot)
        if not rel:
            continue
        path = image_root / rel
        if not path.exists():
            continue
        key = _path_key(path, image_root)
        if key in used_paths:
            continue
        resolved[slot] = path.resolve()
        used_paths.add(key)
