"""Discover Workbench project inputs under project_dir."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ansys_report.models import AnalysisSystem, ProjectInventory

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_DIRS = ("exports", "report_assets", "images")


def _read_text_head(path: Path, max_chars: int = 100_000) -> str:
    """Read only the first max_chars — ds.dat can be gigabytes."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        return handle.read(max_chars)


def _read_text_tail(path: Path, max_bytes: int = 500_000) -> str:
    """Read the tail of a file — solve.out grows with every run."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, 2)
        data = handle.read()
    return data.decode("utf-8", errors="replace")

# Workbench folder → report / pipeline key (EP2737 convention)
FOLDER_TO_KEY: dict[str, str] = {
    "SYS": "static_structural",
    "SYS-1": "modal",
    "SYS-2": "vibration_x",
    "SYS-3": "vibration_y",
    "SYS-4": "vibration_z",
    "SYS-5": "shock_plus_x",
    "SYS-6": "shock_plus_y",
    "SYS-7": "shock_plus_z",
    "SYS-8": "shock_minus_x",
    "SYS-9": "shock_minus_y",
    "SYS-10": "shock_minus_z",
}


def parse_wbpj_systems(wbpj_path: Path) -> list[dict[str, str]]:
    """Read DisplayText and AnalysisType for each UniqueSystemDirectoryName."""
    text = wbpj_path.read_text(encoding="utf-8", errors="replace")
    seen: set[str] = set()
    systems: list[dict[str, str]] = []
    for m in re.finditer(r'"UniqueSystemDirectoryName": "(SYS(?:-\d+)?)"', text):
        folder = m.group(1)
        if folder in seen:
            continue
        seen.add(folder)
        chunk = text[max(0, m.start() - 2000) : m.end() + 100]
        names = re.findall(r'"DisplayText": "([^"]+)"', chunk)
        display_name = names[-1] if names else folder
        at = re.search(r'"AnalysisType": "(\w+)"', chunk)
        systems.append(
            {
                "folder": folder,
                "display_name": display_name,
                "workbench_analysis_type": at.group(1) if at else "unknown",
            }
        )
    return sorted(
        systems,
        key=lambda s: (0 if s["folder"] == "SYS" else int(s["folder"].split("-")[1])),
    )


def parse_wbpj_version(wbpj_path: Path) -> str | None:
    text = wbpj_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<VersionString>([^<]+)</VersionString>", text)
    if m:
        return m.group(1).strip()
    m2 = re.search(r'"ProductVersion"\s*:\s*"([^"]+)"', text)
    return m2.group(1) if m2 else None


def _read_caerep_fields(mech_dir: Path) -> dict[str, str | None]:
    caerep = mech_dir / "CAERep.xml"
    if not caerep.exists():
        return {"project_name": None, "solver_analysis_type": None}
    text = caerep.read_text(encoding="utf-8", errors="replace")
    pm = re.search(r'<ProjectName PropType="string">([^<]+)</ProjectName>', text)
    at = re.search(r'<AnalysisType PropType="string">(\w+)</AnalysisType>', text)
    return {
        "project_name": pm.group(1) if pm else None,
        "solver_analysis_type": at.group(1) if at else None,
    }


def _detect_antype(mech_dir: Path) -> str | None:
    ds = mech_dir / "ds.dat"
    if not ds.exists():
        return None
    head = _read_text_head(ds, 100_000)
    if "antype,harm" in head:
        return "harmonic"
    if "antype,modal" in head or (mech_dir / "file.db").exists():
        return "modal"
    return "static"


def _mapdl_error_count(mech_dir: Path) -> int | str | None:
    solve = mech_dir / "solve.out"
    if not solve.exists():
        return None
    sout = _read_text_tail(solve)
    m = re.search(r"NUMBER OF ERROR MESSAGES\s+=\s+(\d+)", sout)
    if m:
        return int(m.group(1))
    if "RUN COMPLETED" in sout:
        return 0
    return "unknown"


def _scan_dp0_system(project_dir: Path, folder: str, meta: dict[str, str]) -> AnalysisSystem | None:
    mech: Path | None = None
    for files_dir in project_dir.glob("*_files"):
        candidate = files_dir / "dp0" / folder / "MECH"
        if candidate.exists():
            mech = candidate
            break
    if mech is None:
        return None

    rst_paths = sorted(mech.glob("file*.rst"), key=lambda p: p.name)
    primary = mech / "file.rst" if (mech / "file.rst").exists() else (rst_paths[0] if rst_paths else None)
    caerep = _read_caerep_fields(mech)
    key = FOLDER_TO_KEY.get(folder, folder.lower().replace("-", "_"))

    return AnalysisSystem(
        key=key,
        folder=folder,
        display_name=meta.get("display_name", folder),
        workbench_analysis_type=meta.get("workbench_analysis_type", "unknown"),
        mech_dir=mech.resolve(),
        primary_rst=primary.resolve() if primary else None,
        rst_files=[p.resolve() for p in rst_paths],
        project_name=caerep["project_name"],
        antype=_detect_antype(mech),
        has_mcf=(mech / "file.mcf").exists(),
        mapdl_errors=_mapdl_error_count(mech),
    )


def _find_files_root(project_dir: Path) -> Path | None:
    for files_dir in project_dir.glob("*_files"):
        if (files_dir / "dp0").exists():
            return files_dir
    legacy = project_dir / f"{project_dir.stem}_files"
    if legacy.exists() and (legacy / "dp0").exists():
        return legacy
    return None


def _resolve_asset_path(
    name: str,
    project_dir: Path,
    case_root: Path | None,
) -> Path | None:
    path = Path(name)
    if path.is_absolute():
        return path.resolve() if path.exists() else None
    candidates = [project_dir / name]
    if case_root:
        candidates.insert(0, case_root / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _discover_image_root(
    project_dir: Path,
    case_root: Path | None,
    image_folder: str,
) -> tuple[Path, list[str]]:
    """Resolve exported figure folder; warn if nothing exists on disk."""
    warnings: list[str] = []
    image_root = None
    image_path = Path(image_folder)

    for root in filter(None, [case_root, project_dir]):
        candidate = image_path if image_path.is_absolute() else root / image_folder
        if candidate.exists():
            image_root = candidate.resolve()
            break

    if image_root is None:
        search_roots: list[Path] = []
        for root in filter(None, [case_root, project_dir]):
            search_roots.append(root)
        files_root = _find_files_root(project_dir)
        if files_root:
            search_roots.append(files_root)

        for root in search_roots:
            for name in DEFAULT_EXPORT_DIRS:
                candidate = root / name
                if candidate.exists():
                    image_root = candidate.resolve()
                    logger.info("Using image root: %s", image_root)
                    break
            if image_root:
                break

    if image_root is None:
        if image_path.is_absolute():
            image_root = image_path
        else:
            image_root = (case_root or project_dir) / image_folder
        warnings.append(f"image_folder not found: {image_root}")

    return image_root.resolve(), warnings


def scan_project(
    project_dir: Path,
    image_folder: str,
    excel_calcs: str,
    *,
    case_root: Path | None = None,
    excel_bolt_preload: str | None = None,
) -> ProjectInventory:
    """Locate .wbpj, dp0 systems, Excel, CAD, and image roots."""
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise FileNotFoundError(
            f"project_dir not found: {project_dir}. "
            "Point --project-dir at your Workbench project folder."
        )

    if case_root:
        case_root = case_root.resolve()

    warnings: list[str] = []
    wbpj_files = sorted(project_dir.glob("*.wbpj"))
    wbpj_primary = wbpj_files[0] if wbpj_files else None

    wbpj_meta: dict[str, dict[str, str]] = {}
    ansys_version = None
    if wbpj_primary:
        for entry in parse_wbpj_systems(wbpj_primary):
            wbpj_meta[entry["folder"]] = entry
        ansys_version = parse_wbpj_version(wbpj_primary)
    else:
        warnings.append(f"No .wbpj found under {project_dir}")

    systems: dict[str, AnalysisSystem] = {}
    rst_files: dict[str, Path] = {}

    if wbpj_meta:
        folders = [e["folder"] for e in parse_wbpj_systems(wbpj_primary)]  # type: ignore[arg-type]
    else:
        files_root = _find_files_root(project_dir)
        dp0 = files_root / "dp0" if files_root else None
        folders = sorted(
            p.name for p in dp0.glob("SYS*") if p.is_dir()
        ) if dp0 and dp0.exists() else []

    for folder in folders:
        sys = _scan_dp0_system(project_dir, folder, wbpj_meta.get(folder, {}))
        if sys is None:
            warnings.append(f"MECH folder missing for {folder}")
            continue
        systems[sys.key] = sys
        if sys.primary_rst:
            rst_files[folder] = sys.primary_rst

    if not rst_files:
        warnings.append(
            f"No primary file.rst found under {project_dir}; run the solve or check project_dir."
        )

    # Image root: explicit path, then common export folders (incl. Workbench *_files/exports)
    image_root, image_warnings = _discover_image_root(project_dir, case_root, image_folder)
    warnings.extend(image_warnings)

    from ansys_report.extract.result_summary import discover_result_summaries

    result_summaries = discover_result_summaries(image_root)
    if not result_summaries:
        candidate = image_root / "result_summaries"
        if not candidate.is_dir():
            warnings.append(
                f"No Result Summary JSON under {image_root / 'result_summaries'}; "
                "run scripts/mechanical/export_result_summary.py in Mechanical or DPF will be used."
            )

    excel_path = _resolve_asset_path(excel_calcs, project_dir, case_root)
    if excel_path is None:
        warnings.append(f"excel_calcs not found: {excel_calcs}")

    bolt_path = None
    if excel_bolt_preload:
        bolt_path = _resolve_asset_path(excel_bolt_preload, project_dir, case_root)
        if bolt_path is None:
            warnings.append(f"excel_bolt_preload not found: {excel_bolt_preload}")

    cad_step = None
    geometry_scdocx = None
    if case_root:
        step_candidates = list(case_root.glob("*.STEP")) + list(case_root.glob("*.step"))
        if step_candidates:
            cad_step = step_candidates[0].resolve()
    files_root = _find_files_root(project_dir)
    if files_root:
        scdoc = files_root / "dp0" / "SYS" / "DM" / "SYS.scdocx"
        if scdoc.exists():
            geometry_scdocx = scdoc.resolve()

    return ProjectInventory(
        project_dir=project_dir,
        case_root=case_root,
        wbpj_files=wbpj_files,
        wbpj_primary=wbpj_primary,
        systems=systems,
        rst_files=rst_files,
        result_summaries=result_summaries,
        image_root=image_root,
        excel_path=excel_path,
        excel_bolt_preload=bolt_path,
        cad_step=cad_step,
        geometry_scdocx=geometry_scdocx,
        ansys_version=ansys_version,
        warnings=warnings,
    )
