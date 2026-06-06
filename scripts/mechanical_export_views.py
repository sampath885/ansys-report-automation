# Runs inside ANSYS Mechanical (IronPython or CPython)
# Exports named views to PNG files expected by config/image_map.yaml
#
# Usage: Extensions > Install Extension, or run from Mechanical scripting console.
# Set output_dir to your project exports folder.

output_dir = r"D:\Projects\EP1763\exports"  # noqa: F821 — edited per project
resolution = (1920, 1080)

views = {
    "geometry/cad_iso.png": "CAD Isometric",
    "mesh/mesh_global.png": "Mesh",
    "modal/mode1.png": "Mode 1",
    "static/total_deformation.png": "Total Deformation",
    "static/vonmises.png": "Equivalent Stress",
}

try:
    import os

    for rel_path, view_name in views.items():
        full = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        # ExtAPI is provided by Mechanical at runtime
        ExtAPI.Graphics.ExportImage(full, resolution[0], resolution[1], view_name)  # noqa: F821
        print("Exported:", full)
except NameError:
    print("Run this script inside ANSYS Mechanical (ExtAPI not available).")
except Exception as exc:
    print("Export failed:", exc)
