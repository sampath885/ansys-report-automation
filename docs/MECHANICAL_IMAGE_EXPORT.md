# EP2737 — export report images from ANSYS Mechanical

This guide is for engineers who have **never used ANSYS before**. You will run one Python script **inside Mechanical** (once per analysis system). PNGs land in `E:\EP 2737\exports\` with fixed names the report builder expects.

---

## What you need

| Item | Location |
|------|----------|
| Workbench project | `E:\EP 2737\Structural Analysis_EP2737\EP2737.wbpj` |
| Export script | `E:\ansys-report-automation\scripts\mechanical\ep2737_export_images.py` |
| Export manifest | `E:\ansys-report-automation\config\ep2737_mechanical_export.json` |
| PNG output folder | `E:\EP 2737\exports\` (created automatically) |

---

## Step 1 — Open ANSYS Workbench

1. Start **ANSYS Workbench 2025 R2** from the Windows Start menu (search **Workbench** or **ANSYS**).
2. In Workbench: **File → Open…**
3. Browse to:
   ```
   E:\EP 2737\Structural Analysis_EP2737\EP2737.wbpj
   ```
4. Click **Open**.

You should see a flowchart (pipeline) with boxes like **Static Structural**, **Modal**, **Harmonic Response**, **Shock** systems.

---

## Step 2 — Open Mechanical for one system

Mechanical is the 3D window where you view mesh, loads, and stress plots.

For each system below, do the same pattern:

1. Find the system row in Workbench (e.g. **Static Structural**).
2. In that row, find the green **Model** cell (under **Static Structural**).
3. **Double-click Model** (or right-click → **Edit**).
4. Wait — Mechanical opens in a separate window (may take 1–2 minutes).

### Systems to repeat (11 runs total)

| Run | Workbench system | Folder | What gets exported |
|-----|------------------|--------|-------------------|
| 1 | **Static Structural** | SYS | Mesh, contacts, BCs, static stress/deformation |
| 2 | **Modal** | SYS-1 | Mode shapes 1–6 |
| 3 | Harmonic X | SYS-2 | Harmonic X plots |
| 4 | Harmonic Y | SYS-3 | Harmonic Y plots |
| 5 | Harmonic Z | SYS-4 | Harmonic Z plots |
| 6 | Shock +X | SYS-5 | Shock +X results |
| 7 | Shock +Y | SYS-6 | Shock +Y results |
| 8 | Shock +Z | SYS-7 | Shock +Z results |
| 9 | Shock -X | SYS-8 | Shock -X results |
| 10 | Shock -Y | SYS-9 | Shock -Y results |
| 11 | Shock -Z | SYS-10 | Shock -Z results |

**Tip:** You do **not** re-solve. Open Mechanical **after** results already exist (green checkmarks on Solution cells).

---

## Step 3 — Run the export script in Mechanical

With Mechanical open for the current system:

1. Top menu: **Automation** tab.
2. Open **Mechanical Scripting** (Scripting button on the ribbon).
3. **Open** (folder icon) → select:
   ```
   E:\ansys-report-automation\scripts\mechanical\ep2737_export_images.py
   ```
4. Click **Run** (green play). Output appears in the **Shell** panel below.
5. If nothing happens, type `main()` in the Shell and press Enter.

### Where to see output

- **Mechanical Scripting window** (bottom pane): lines like `OK static_total_deformation -> E:\EP 2737\exports\...`
- **Log file:** `E:\EP 2737\exports\export_log_SYS.txt` (name changes per system, e.g. `export_log_SYS_5.txt`)

### If auto-detect fails

Edit the top of `ep2737_export_images.py` and set:

```python
SYSTEM_OVERRIDE = "SYS-5"   # example for Shock +X
```

Then run the script again.

---

## Step 4 — Repeat for every system

1. **Close Mechanical** (or return to Workbench tab).
2. Open the **next** system's **Model** cell.
3. Run the **same script** again.

The script detects which system you opened (`SYS`, `SYS-1`, …) and only exports that system's PNGs.

---

## Step 5 — Check PNGs (optional, from repo)

In PowerShell:

```powershell
cd E:\ansys-report-automation
python scripts/validate_ep2737_exports.py
```

Lists missing PNGs vs the report image map.

---

## Troubleshooting

### "ExtAPI is not available"

You ran the script from **PowerShell/cmd**. It must run **inside Mechanical** (Automation → Run Script).

### Many lines say SKIP

The script searches the Mechanical tree for result names like **Total Deformation** and **Equivalent Stress**.

**Fix:**

1. In Mechanical, manually insert the missing result: **Solution → Insert → Deformation → Total** (or **Stress → Equivalent**).
2. Solve / evaluate if needed.
3. Run the script again.

Optional results (mesh metrics, harmonic charts) are marked non-required — SKIP is OK for those.

### Flange-only stress looks wrong

The script hides non-flange bodies by name (`flange`, `welded`, etc.). If your body names differ, create a **Named Selection** called `Flange` in Mechanical, or adjust `FLANGE_NAME_HINTS` in the script.

### Paths on another PC

Edit at the top of `ep2737_export_images.py`:

```python
OUTPUT_ROOT = r"E:\EP 2737\exports"
MANIFEST_PATH = r"E:\ansys-report-automation\config\ep2737_mechanical_export.json"
```

---

## Figures not from Mechanical

Copy once into `E:\EP 2737\exports\geometry\`:

| Slot | File |
|------|------|
| 2D drawing | `cad_section.png` |
| Isometric CAD | `cad_isometric.png` |

These are drawings/diagrams, not FE contours.

---

## After export — report build

When images exist and report config has `skip_images: false` + `image_map_path`, rebuild the DOCX. Figures embed automatically by slot name (`config/ep2737_image_map.yaml`).

---

## Quick reference diagram

```
Workbench (.wbpj)
    │
    ├─ Static Structural → Model → Mechanical → Run Script → exports/mesh, static/...
    ├─ Modal             → Model → Mechanical → Run Script → exports/modal/...
    ├─ Harmonic X        → Model → Mechanical → Run Script → exports/harmonic/x/...
    └─ Shock +X …        → Model → Mechanical → Run Script → exports/shock/plus_x/...
```
