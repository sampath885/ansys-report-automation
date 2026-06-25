"""Match auto-discover Mechanical export folders to report figure slots."""

from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ansys_report.config import ImageMapConfig
from ansys_report.models import MissingAssets

logger = logging.getLogger(__name__)

_LOG_LINE = re.compile(
    r"^OK\s+\[[^\]]+\]\s+->\s+(.+\.png)\s*$",
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


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _path_tokens(rel_path: str) -> set[str]:
    return {token for token in re.split(r"[/_\-\s]+", rel_path.lower()) if token}


def infer_rule_from_slot(slot: str) -> ImageMatchRule | None:
    """Build a best-effort match rule from a slot name (project-agnostic)."""
    s = slot.lower().strip()
    if not s:
        return None

    if s in {"cad_isometric", "cad_section", "geometry_model_orientation"}:
        return ImageMatchRule(path_glob="geometry/*.png")

    if s == "mesh_global":
        return ImageMatchRule(path_glob="mesh/mesh*.png")
    if s.startswith("mesh_"):
        metric = s.replace("mesh_quality_", "").replace("mesh_", "")
        return ImageMatchRule(folder_keywords=["mesh"], file=f"{metric}.png")

    if s == "modelling_contacts":
        return ImageMatchRule(path_glob="connections/*.png")

    if s.startswith("static_"):
        load_files = {
            "earth_gravity": "loading/standard_earth_gravity.png",
            "fixed_support": "loading/fixed_support.png",
            "pressure": "loading/pressure.png",
            "total_deformation": "solution/total_deformation.png",
            "vonmises_stress": "solution/equivalent_stress.png",
            "vonmises_flange": "solution/equivalent_stress.png",
        }
        tail = s[len("static_") :]
        file_name = load_files.get(tail)
        if file_name:
            return ImageMatchRule(folder_keywords=["static"], file=file_name)

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
        axis_keywords = {
            "x": ["x", "x_direction", "horizontal", "horizantal"],
            "y": ["y", "y_direction", "vertical"],
            "z": ["z", "z_direction", "longitudinal"],
        }
        file_map = {
            "location": "loading/acceleration.png",
            "accel_plot": "solution/graphs/frequency_response.png",
            "deformation": "solution/total_deformation.png",
            "stress_asm": "solution/equivalent_stress.png",
            "stress_flange": "solution/equivalent_stress.png",
        }
        folder_keywords = ["harmonic", "vibration", axis] + axis_keywords.get(axis, [])
        file_name = file_map.get(tail)
        if file_name:
            return ImageMatchRule(folder_keywords=folder_keywords, file=file_name)

    shock_match = re.match(r"shock_(plus|minus)_([xyz])_(.+)$", s)
    if shock_match:
        sign, axis, tail = shock_match.groups()
        sign_keywords = ["plus", "+"] if sign == "plus" else ["minus", "-"]
        axis_keywords = {
            "x": ["x", "horizontal", "horizantal"],
            "y": ["y", "vertical"],
            "z": ["z", "longitudinal"],
        }
        file_map = {
            "deformation": "solution/total_deformation.png",
            "stress_asm": "solution/equivalent_stress_maximum_overtime.png",
            "stress_flange": "solution/equivalent_stress.png",
        }
        folder_keywords = ["shock", "transient", "equivalent", sign] + sign_keywords + [axis]
        folder_keywords.extend(axis_keywords.get(axis, []))
        file_name = file_map.get(tail)
        if file_name:
            return ImageMatchRule(folder_keywords=folder_keywords, file=file_name)

    return None


def _score_path_for_slot(slot: str, rel_path: str) -> int:
    """Heuristic score for matching an export path to a logical figure slot."""
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
        if "plus" in tokens or "+x" in p or "+y" in p or "+z" in p:
            score += 10
        if "minus" in tokens:
            score -= 10
    if "minus" in s:
        if "minus" in tokens or "-x" in p or "-y" in p or "-z" in p:
            score += 10
        if "plus" in tokens:
            score -= 10

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
    if "accel" in s and ("frequency_response" in p or "acceleration" in p):
        score += 20
    if "location" in s and ("loading" in p or "acceleration" in p):
        score += 12
    if "earth_gravity" in s and "gravity" in p:
        score += 20
    if "fixed_support" in s and "fixed_support" in p:
        score += 20
    if "pressure" in s and "pressure" in p:
        score += 20
    if s == "mesh_global" and p.startswith("mesh/") and "mesh" in Path(p).name:
        score += 20
    if s.startswith("mesh_") and s.replace("mesh_quality_", "").replace("mesh_", "") in p:
        score += 15

    if "graphs/" in p and "accel" in s:
        score += 8
    if "loading/" in p and any(k in s for k in ("gravity", "support", "pressure", "location")):
        score += 6

    return score


def _resolve_slot_by_scoring(
    slot: str,
    image_root: Path,
    indexed_paths: list[str],
    *,
    min_score: int = 18,
) -> Path | None:
    ranked = sorted(
        ((rel, _score_path_for_slot(slot, rel)) for rel in indexed_paths),
        key=lambda item: (-item[1], item[0].count("/"), len(item[0]), item[0].lower()),
    )
    if not ranked or ranked[0][1] < min_score:
        return None
    best_rel, best_score = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == best_score:
        logger.debug("Ambiguous image match for %s: %s vs %s", slot, ranked[0][0], ranked[1][0])
    path = image_root / best_rel
    return path.resolve() if path.exists() else None


def _matches_rule(rel_path: str, rule: ImageMatchRule) -> bool:
    rel_lower = rel_path.lower()
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


def _pick_best_match(candidates: list[str], rule: ImageMatchRule) -> str | None:
    if not candidates:
        return None
    if rule.path:
        norm = _normalize_rel(rule.path).lower()
        for candidate in candidates:
            if candidate.lower() == norm:
                return candidate
    if len(candidates) == 1:
        return candidates[0]
    # Prefer shorter paths (less nested duplicates) then lexicographic stability.
    return sorted(candidates, key=lambda p: (p.count("/"), len(p), p.lower()))[0]


def resolve_slot_with_rules(
    slot: str,
    rule: ImageMatchRule,
    image_root: Path,
    indexed_paths: list[str],
) -> Path | None:
    matches = [rel for rel in indexed_paths if _matches_rule(rel, rule)]
    chosen = _pick_best_match(matches, rule)
    if not chosen:
        return None
    path = image_root / chosen
    return path.resolve() if path.exists() else None


def resolve_slot_for_exports(
    slot: str,
    image_root: Path,
    indexed_paths: list[str],
    rules: ImageMatchRulesConfig | None = None,
) -> Path | None:
    """Resolve one slot using YAML rules, inferred rules, then scoring."""
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
        path = resolve_slot_with_rules(slot, rule, image_root, indexed_paths)
        if path is not None:
            return path

    return _resolve_slot_by_scoring(slot, image_root, indexed_paths)


def resolve_assets_auto_discover(
    image_root: Path,
    rules: ImageMatchRulesConfig,
    slots: list[str] | None = None,
    check_quality: bool = True,
    quality_checker=None,
) -> MissingAssets:
    from ansys_report.images.mapper import _quality_warnings

    target_slots = slots if slots is not None else sorted(rules.rules.keys())
    indexed = scan_image_folder(image_root)
    missing: list[str] = []
    warnings: list[str] = []
    resolved: dict[str, Path] = {}

    for slot in target_slots:
        path = resolve_slot_for_exports(slot, image_root, indexed, rules)
        if path is None:
            missing.append(slot)
            continue
        resolved[slot] = path
        if check_quality:
            checker = quality_checker or _quality_warnings
            warnings.extend(checker(slot, path))

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
    missing_after: list[str] = []

    if mode in {"exact", "hybrid"} and image_map and image_map.slots:
        exact = resolve_assets(image_root, image_map, check_quality=check_quality)
        resolved.update(exact.resolved)
        warnings.extend(exact.warnings)

    pending = [slot for slot in requested if slot not in resolved]

    if mode in {"auto", "hybrid"}:
        auto = resolve_assets_auto_discover(
            image_root,
            rules or ImageMatchRulesConfig(),
            slots=pending or None,
            check_quality=check_quality,
        )
        resolved.update(auto.resolved)
        warnings.extend(auto.warnings)
        pending = [slot for slot in requested if slot not in resolved]

    missing_after = [slot for slot in requested if slot not in resolved]

    # De-duplicate warnings preserving order.
    seen: set[str] = set()
    unique_warnings: list[str] = []
    for msg in warnings:
        if msg not in seen:
            seen.add(msg)
            unique_warnings.append(msg)

    return MissingAssets(
        missing_slots=missing_after,
        warnings=unique_warnings,
        resolved=resolved,
    )
