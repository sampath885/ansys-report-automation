# User Guide — ANSYS Report Automation

## Quick start (production)

1. Install the package (`pip install -e .`)
2. Run `ansys-report run` and enter your Workbench project, image exports, and Excel paths
3. Open the generated DOCX in `automated_scripts_output/`

## Quick start (manual config)

1. Install the package (`pip install -e .`)
2. Copy `config/project.example.yaml` → `config/project.yaml` and set `project_dir`
3. Run `ansys-report template --out templates`
4. Place export PNGs in `<project_dir>/exports/` per `config/image_map.yaml`
5. Run `ansys-report validate --config config/project.yaml`
6. Run `ansys-report build --config config/project.yaml --out output/`

## Enabled sections (default)

`revision`, `scope`, `software`, `references`, `equipment`, `modelling`, `modal`, `static`, `harmonic_x`, `design_calcs`

Disable sections by removing them from `sections_enabled` in `project.yaml`.

## Image workflow

**Path B (manual):** Export plots from Mechanical/Fluent and save under `exports/` using paths in `image_map.yaml`.

**Path A (scripted):** Run `scripts/mechanical_export_views.py` inside Mechanical to auto-export named views.

## Design calculations Excel format

Each table sheet should have a header row with columns such as:

`Label | Symbol | Formula | Value | Unit | Source | Verdict`

Supported sheet names: `Bolt Load`, `Flange Moments`, `Effort`, `End Flange`.

## Narrative engine

By default, rule-based text compares stresses to yield fractions and modal frequencies to the operating band in `project.yaml`. Thresholds live in `config/thresholds.yaml`.

Optional AI polish requires an API key in `.env` and `pip install -e ".[ai]"`.

## Exit codes


| Code | Meaning                    |
| ---- | -------------------------- |
| 0    | Success                    |
| 1    | Unexpected error           |
| 2    | Validation warnings/errors |


