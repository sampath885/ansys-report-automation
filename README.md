# ANSYS Report Automation

Laptop-local Python tool that ingests ANSYS result files, merges Excel design calculations, fills an EP1763-style Word template, and exports DOCX/PDF.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python** | 3.10 or newer |
| **ANSYS** | 2024 R2 recommended (for DPF `.rst` extraction) |
| **Microsoft Word** | Optional; used by `docx2pdf` for PDF export on Windows |
| **LibreOffice** | Optional fallback for PDF export |

## Installation

```powershell
cd "c:\Users\jaswa\OneDrive\Desktop\ansys automation"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Copy and edit configuration:

```powershell
copy config\project.example.yaml config\project.yaml
copy config\image_map.example.yaml config\image_map.yaml
copy .env.example .env
```

Generate the Word template (first time only):

```powershell
ansys-report template --out templates
```

## Project layout

Point `project_dir` in `config/project.yaml` at your Workbench folder containing:

- Solved `.rst` files (under `dp0/SYS*/MECH/` or anywhere under the project)
- `exports/` — PNG figures keyed by `config/image_map.yaml`
- `design_calcs.xlsx` — Section 10 calculation tables

## Usage

### Validate inputs (no render)

```powershell
ansys-report validate --config config\project.yaml --project-dir "D:\Projects\EP1763"
```

Exit code `2` means warnings or errors (missing images, unresolved DPF fields, etc.).

### Build report from real project

```powershell
ansys-report build --config config\project.yaml --project-dir "D:\Projects\EP1763" --out output\
```

Flags:

- `--no-pdf` — skip PDF conversion
- `--no-ai` — use rule-based narratives only
- `--verbose` — debug logging
- `--image-map config\image_map.yaml` — custom image mapping

### Mock build (no ANSYS required)

```powershell
ansys-report build --config config\project.example.yaml --project-dir tests\fixtures --mock tests\fixtures\mock_results.json --template templates\EP1763_report_template.docx --out output\ --no-pdf
```

### Optional AI narratives

Set one of these in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

Install optional deps: `pip install -e ".[ai]"`

## Tests

```powershell
pytest
```

DPF integration tests are skipped unless `ANSYS_AVAILABLE=1` and a real `.rst` path is configured.

## Mechanical image export (optional)

1. Open your model in ANSYS Mechanical
2. Edit `output_dir` in `scripts/mechanical_export_views.py`
3. Run the script from the Mechanical scripting console

Alternatively, place PNGs manually in `exports/` using filenames from `config/image_map.example.yaml`.

## Troubleshooting

| Issue | Action |
|-------|--------|
| No `.rst` found | Run the solve in Workbench; check `--project-dir` |
| DPF import fails | Confirm ANSYS 2024 R2 and matching `ansys-dpf-core` version |
| PDF not created | Install Word + `docx2pdf`, or LibreOffice; DOCX is still produced |
| Missing figures | Run `validate` and populate `exports/` per image map |
| TOC not updating | Open DOCX in Word → Update Field on Table of Contents |

## Documentation

- `docs/IMPLEMENTATION.md` — architecture and module specifications
- `docs/SPRINTS.md` — phased delivery plan
- `docs/USAGE.md` — extended usage guide
