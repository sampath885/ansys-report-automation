"""Quick probe of CAERep.xml structure for Phase 3."""
import re

from ansys_report.ep2737_paths import ep2737_dp0

p = ep2737_dp0() / "SYS" / "MECH" / "CAERep.xml"
t = p.read_text(encoding="utf-8")

for block in re.finditer(r"<BodyAttributes[^>]*>(.*?)</BodyAttributes>", t, re.S):
    b = block.group(1)
    cap = re.search(r'<Caption PropType="string">([^<]+)</Caption>', b)
    mass = re.search(r'<Mass PropType="double"[^>]*>([\d.E+-]+)</Mass>', b)
    mat = re.search(r'<MaterialName PropType="string">([^<]+)</MaterialName>', b)
    if cap:
        print("body", cap.group(1), "mass", mass.group(1) if mass else "?", "mat", mat.group(1) if mat else "?")

for c in re.finditer(
    r'<ContactRep[^>]*>.*?<Caption PropType="string">([^<]+)</Caption>.*?<Type PropType="string">([^<]+)</Type>',
    t,
    re.S,
):
    print("contact", c.group(1), c.group(2))

print("pretensions", len(re.findall(r"<PretensionBolt", t)))

for block in re.finditer(r"<AssemblyAttributes[^>]*>(.*?)</AssemblyAttributes>", t, re.S):
    b = block.group(1)
    cap = re.search(r'<Caption PropType="string">([^<]+)</Caption>', b)
    mass = re.search(r'<Mass PropType="double"[^>]*>([\d.E+-]+)</Mass>', b)
    print("assembly", cap.group(1) if cap else "?", "mass", mass.group(1) if mass else "?")

cog_m = re.search(
    r'<Centroid ObjId=\d+ Type="DSGePoint3d".*?'
    r'<Coordinates PropType="vector&lt;double>"[^>]*>([^<]+)</Coordinates>',
    t,
    re.S,
)
print("cog", cog_m.group(1) if cog_m else None)

for tag in ["NormalPressure", "Acceleration", "FixedSurface"]:
    print(tag, len(re.findall(rf"<{tag}", t)))

for m in re.finditer(r"<NormalPressure[^>]*>(.*?)</NormalPressure>", t, re.S):
    cap = re.search(r'<Caption PropType="string">([^<]*)</Caption>', m.group(1))
    print("pressure", cap.group(1) if cap else "?")

for m in re.finditer(r"<FixedSurface[^>]*>(.*?)</FixedSurface>", t, re.S):
    cap = re.search(r'<Caption PropType="string">([^<]*)</Caption>', m.group(1))
    print("fixed", cap.group(1) if cap else "?")

so = ep2737_dp0() / "SYS" / "MECH" / "solve.out"
for line in so.read_text(encoding="utf-8").splitlines():
    if "total nodes" in line.lower() or "total elements" in line.lower():
        print("solve", line.strip())
