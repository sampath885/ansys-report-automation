"""Extract Equipment / Modelling metadata from CAERep, MatML, ds.dat, solve.out — no DPF."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ansys_report.models import (
    AnalysisMetadata,
    AssemblyMetadata,
    BodyMetadata,
    BoundaryConditionMetadata,
    ContactMetadata,
    EquipmentMetadata,
    LoadMetadata,
    MaterialMetadata,
    ModellingMetadata,
    ProjectMetadata,
)
from ansys_report.models import MeshResult, ProjectInventory

logger = logging.getLogger(__name__)

_STATIC_SYSTEM_KEY = "static_structural"


def _read_text(path: Path, limit: int | None = None) -> str:
    with path.open(encoding="utf-8", errors="replace") as handle:
        if limit is not None:
            return handle.read(limit)
        return handle.read()


def parse_caerep_bodies(text: str) -> list[BodyMetadata]:
    bodies: list[BodyMetadata] = []
    for block in re.finditer(r"<BodyAttributes[^>]*>(.*?)</BodyAttributes>", text, re.S):
        chunk = block.group(1)
        cap = re.search(r'<Caption PropType="string">([^<]+)</Caption>', chunk)
        if not cap:
            continue
        mass_m = re.search(r'<Mass PropType="double"[^>]*>([\d.E+-]+)</Mass>', chunk)
        mat_m = re.search(r'<MaterialName PropType="string">([^<]+)</MaterialName>', chunk)
        mass_tonne = float(mass_m.group(1)) if mass_m else None
        bodies.append(
            BodyMetadata(
                name=cap.group(1),
                mass_tonne=mass_tonne,
                mass_kg=round(mass_tonne * 1000, 4) if mass_tonne is not None else None,
                material=mat_m.group(1) if mat_m else None,
            )
        )
    return bodies


def parse_caerep_assembly(text: str) -> AssemblyMetadata | None:
    for block in re.finditer(r"<AssemblyAttributes[^>]*>(.*?)</AssemblyAttributes>", text, re.S):
        chunk = block.group(1)
        cap = re.search(r'<Caption PropType="string">([^<]+)</Caption>', chunk)
        mass_m = re.search(r'<Mass PropType="double"[^>]*>([\d.E+-]+)</Mass>', chunk)
        if not cap and not mass_m:
            continue
        cog = _parse_centroid(chunk) or _parse_centroid(text)
        mass_tonne = float(mass_m.group(1)) if mass_m else None
        return AssemblyMetadata(
            name=cap.group(1) if cap else "Assembly",
            mass_tonne=mass_tonne,
            mass_kg=round(mass_tonne * 1000, 4) if mass_tonne is not None else None,
            cog_mm=cog,
        )
    return None


def _parse_centroid(text: str) -> dict[str, float] | None:
    m = re.search(
        r'<Coordinates PropType="vector&lt;double>"[^>]*>([^<]+)</Coordinates>',
        text,
    )
    if not m:
        return None
    parts = [float(x.strip()) for x in m.group(1).split(",")]
    if len(parts) != 3:
        return None
    return {"x_mm": parts[0], "y_mm": parts[1], "z_mm": parts[2]}


def parse_caerep_contacts(text: str) -> list[ContactMetadata]:
    contacts: list[ContactMetadata] = []
    for block in re.finditer(r"<ContactRep[^>]*>(.*?)</ContactRep>", text, re.S):
        chunk = block.group(1)
        cap = re.search(r'<Caption PropType="string">([^<]+)</Caption>', chunk)
        typ = re.search(r'<Type PropType="string">([^<]+)</Type>', chunk)
        if cap:
            contacts.append(ContactMetadata(caption=cap.group(1), contact_type=typ.group(1) if typ else None))
    return contacts


def parse_caerep_boundary_conditions(text: str) -> list[BoundaryConditionMetadata]:
    bcs: list[BoundaryConditionMetadata] = []
    for tag, bc_type in [("FixedSurface", "fixed_support"), ("Displacement", "displacement"), ("RemoteDisplacement", "remote_displacement")]:
        for block in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.S):
            chunk = block.group(1)
            cap = re.search(r'<Caption PropType="string">([^<]*)</Caption>', chunk)
            bcs.append(
                BoundaryConditionMetadata(
                    caption=cap.group(1) if cap else tag,
                    bc_type=bc_type,
                )
            )
    return bcs


def parse_caerep_loads(text: str) -> list[LoadMetadata]:
    loads: list[LoadMetadata] = []

    for block in re.finditer(r"<NormalPressure[^>]*>(.*?)</NormalPressure>", text, re.S):
        chunk = block.group(1)
        cap = re.search(r'<Caption PropType="string">([^<]*)</Caption>', chunk)
        loads.append(LoadMetadata(load_type="pressure", caption=cap.group(1) if cap else "Pressure"))

    for block in re.finditer(r"<Acceleration[^>]*>(.*?)</Acceleration>", text, re.S):
        chunk = block.group(1)
        cap = re.search(r'<Caption PropType="string">([^<]*)</Caption>', chunk)
        mag = re.search(r'<Magnitude PropType="double"[^>]*>([\d.E+-]+)</Magnitude>', chunk)
        loads.append(
            LoadMetadata(
                load_type="acceleration",
                caption=cap.group(1) if cap else "Acceleration",
                magnitude=float(mag.group(1)) if mag else None,
            )
        )

    preloads = [float(v) for v in re.findall(r'<Preload PropType="double"[^>]*>([\d.E+-]+)</Preload>', text)]
    if preloads:
        loads.append(
            LoadMetadata(
                load_type="bolt_pretension",
                caption="Bolt pretension",
                magnitude=preloads[0],
                count=len(preloads),
            )
        )

    return loads


def parse_caerep_load_steps(text: str) -> list[float]:
    return [float(t) for t in re.findall(r"<EndTime>([\d.]+)</EndTime>", text)]


def parse_caerep_header(text: str) -> dict[str, str | None]:
    pm = re.search(r'<ProjectName PropType="string">([^<]+)</ProjectName>', text)
    at = re.search(r'<AnalysisType PropType="string">(\w+)</AnalysisType>', text)
    return {
        "project_name": pm.group(1) if pm else None,
        "analysis_type": at.group(1) if at else None,
    }


def parse_ds_dat_antype(ds_text: str) -> str | None:
    head = ds_text[:100_000]
    if "antype,harm" in head:
        return "harmonic"
    if "antype,modal" in head:
        return "modal"
    if "antype,static" in head or "/solu" in head:
        return "static"
    return None


def parse_mesh_from_solve(solve_path: Path) -> MeshResult:
    if not solve_path.exists():
        return MeshResult(manual_fields=["node_count", "element_count"])

    text = _read_text(solve_path)
    node_count = None
    total_element_count = None
    solid_element_count = None
    for line in text.splitlines():
        low = line.lower()
        if "number of total nodes" in low:
            m = re.search(r"=\s*(\d+)", line)
            if m:
                node_count = int(m.group(1))
        if "number of solid elements" in low:
            m = re.search(r"=\s*(\d+)", line)
            if m:
                solid_element_count = int(m.group(1))
        if "number of total elements" in low:
            m = re.search(r"=\s*(\d+)", line)
            if m:
                total_element_count = int(m.group(1))

    # Mechanical's mesh statistics report the solid body element count. The
    # solver "total elements" additionally includes contact/target/surface and
    # beam (pretension) elements, so prefer the solid count to match the report.
    element_count = (
        solid_element_count if solid_element_count is not None else total_element_count
    )

    manual: list[str] = []
    if node_count is None:
        manual.append("node_count")
    if element_count is None:
        manual.append("element_count")

    return MeshResult(
        node_count=node_count,
        element_count=element_count,
        manual_fields=manual,
    )


def parse_matml(material_path: Path) -> list[MaterialMetadata]:
    """Parse MatML.xml or EngineeringData.xml for isotropic material properties."""
    if not material_path.exists():
        return []

    try:
        root = ET.fromstring(material_path.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        logger.warning("MatML parse failed for %s: %s", material_path, exc)
        return []

    materials: list[MaterialMetadata] = []
    for bulk in root.iter("BulkDetails"):
        name_el = bulk.find("Name")
        if name_el is None or not (name_el.text or "").strip():
            continue
        name = name_el.text.strip()
        props: dict[str, float] = {}
        for prop in bulk.findall("PropertyData"):
            for pv in prop.findall("ParameterValue"):
                ln = pv.find('Qualifier[@name="Localized Name"]')
                data_el = pv.find("Data")
                if data_el is None or data_el.text is None:
                    continue
                label = ln.text.strip() if ln is not None and ln.text else None
                if not label:
                    continue
                try:
                    value = float(data_el.text)
                except ValueError:
                    continue
                if label == "Young's Modulus":
                    props["youngs_modulus_pa"] = value
                elif label == "Poisson's Ratio":
                    props["poissons_ratio"] = value
                elif label == "Density":
                    props["density_kg_m3"] = value
                elif label == "Tensile Yield Strength":
                    props["tensile_yield_pa"] = value

        if props:
            materials.append(
                MaterialMetadata(
                    name=name,
                    youngs_modulus_gpa=round(props["youngs_modulus_pa"] / 1e9, 3) if "youngs_modulus_pa" in props else None,
                    poissons_ratio=props.get("poissons_ratio"),
                    density_kg_m3=props.get("density_kg_m3"),
                    tensile_yield_mpa=round(props["tensile_yield_pa"] / 1e6, 1) if "tensile_yield_pa" in props else None,
                )
            )

    # Deduplicate by name (MatML can repeat entries)
    seen: dict[str, MaterialMetadata] = {}
    for mat in materials:
        if mat.name not in seen or mat.youngs_modulus_gpa is not None:
            seen[mat.name] = mat
    return list(seen.values())


def extract_analysis_metadata(mech_dir: Path) -> AnalysisMetadata:
    caerep_path = mech_dir / "CAERep.xml"
    ds_path = mech_dir / "ds.dat"
    solve_path = mech_dir / "solve.out"

    header: dict[str, str | None] = {}
    bodies: list[BodyMetadata] = []
    assembly: AssemblyMetadata | None = None
    contacts: list[ContactMetadata] = []
    boundary_conditions: list[BoundaryConditionMetadata] = []
    loads: list[LoadMetadata] = []
    load_steps: list[float] = []

    if caerep_path.exists():
        text = _read_text(caerep_path)
        header = parse_caerep_header(text)
        bodies = parse_caerep_bodies(text)
        assembly = parse_caerep_assembly(text)
        contacts = parse_caerep_contacts(text)
        boundary_conditions = parse_caerep_boundary_conditions(text)
        loads = parse_caerep_loads(text)
        load_steps = parse_caerep_load_steps(text)

    antype = None
    if ds_path.exists():
        antype = parse_ds_dat_antype(_read_text(ds_path, limit=100_000))

    mesh = parse_mesh_from_solve(solve_path)
    matml = mech_dir / "MatML.xml"
    engd = mech_dir.parent / "ENGD" / "EngineeringData.xml"
    material_path = matml if matml.exists() else engd
    materials = parse_matml(material_path)

    return AnalysisMetadata(
        project_name=header.get("project_name"),
        solver_analysis_type=header.get("analysis_type"),
        antype=antype,
        load_steps=load_steps,
        bodies=bodies,
        assembly=assembly,
        contacts=contacts,
        boundary_conditions=boundary_conditions,
        loads=loads,
        materials=materials,
        mesh=mesh,
        source_mech_dir=mech_dir,
    )


def _static_system(inventory: ProjectInventory):
    if _STATIC_SYSTEM_KEY in inventory.systems:
        return inventory.systems[_STATIC_SYSTEM_KEY]
    for key, sys in inventory.systems.items():
        if sys.folder == "SYS":
            return sys
    return next(iter(inventory.systems.values()), None)


def extract_equipment_metadata(inventory: ProjectInventory, bom_id: str, title: str) -> EquipmentMetadata:
    static = _static_system(inventory)
    analysis = extract_analysis_metadata(static.mech_dir) if static else AnalysisMetadata()

    unique_materials = sorted({b.material for b in analysis.bodies if b.material})
    return EquipmentMetadata(
        bom_id=bom_id,
        title=title,
        cad_step=inventory.cad_step,
        bodies=analysis.bodies,
        assembly=analysis.assembly,
        material_names=unique_materials,
    )


def extract_modelling_metadata(inventory: ProjectInventory) -> ModellingMetadata:
    static = _static_system(inventory)
    if static is None:
        return ModellingMetadata(manual_fields=["node_count", "element_count"])

    analysis = extract_analysis_metadata(static.mech_dir)
    return ModellingMetadata(
        project_name=analysis.project_name,
        solver_analysis_type=analysis.solver_analysis_type,
        antype=analysis.antype,
        load_steps=analysis.load_steps,
        contacts=analysis.contacts,
        boundary_conditions=analysis.boundary_conditions,
        loads=analysis.loads,
        materials=analysis.materials,
        node_count=analysis.mesh.node_count,
        element_count=analysis.mesh.element_count,
        mesh_source="solve.out",
        manual_fields=list(analysis.mesh.manual_fields),
    )


def extract_project_metadata(inventory: ProjectInventory, bom_id: str, title: str) -> ProjectMetadata:
    static = _static_system(inventory)
    analysis = extract_analysis_metadata(static.mech_dir) if static else AnalysisMetadata()
    return ProjectMetadata(
        bom_id=bom_id,
        title=title,
        ansys_version=inventory.ansys_version,
        cad_step=inventory.cad_step,
        equipment=extract_equipment_metadata(inventory, bom_id, title),
        modelling=extract_modelling_metadata(inventory),
        static_analysis=analysis,
    )


def bodies_from_inventory(inventory: ProjectInventory) -> list[BodyMetadata]:
    static = _static_system(inventory)
    if static is None:
        return []
    return extract_analysis_metadata(static.mech_dir).bodies


def dedupe_bodies(bodies: list[BodyMetadata]) -> list[BodyMetadata]:
    """Drop duplicate CAERep body entries (same name + material)."""
    seen: set[tuple[str, str | None]] = set()
    unique: list[BodyMetadata] = []
    for body in bodies:
        key = (body.name, body.material)
        if key in seen:
            continue
        seen.add(key)
        unique.append(body)
    return unique
