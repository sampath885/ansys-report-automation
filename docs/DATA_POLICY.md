# EP2737 data policy

## Production builds (`use_word_table_data: false`)

| Source | Used for |
|--------|----------|
| **RST + DPF** | Modal, static, harmonic, shock stresses/deformations/frequencies |
| **config/ep2737_report_defaults.yaml** | Tables 1–4, 2, 7, 9, 11 (project metadata — edited per job, not read from Word at build time) |
| **CAERep / solve.out / MatML** | Equipment mass, COG, mesh counts, load steps, contacts, materials (Tables 6, 8, 10, 12–13) |
| **RST regression fixtures** (when `use_dpf_golden_fallback: true` and DPF unavailable) | Modal, static, harmonic, shock, bolt loads (Tables 15, 17–22) |
| **Excel** | Tables 25–27 (design calculations) |
| **config/ep2737_standards_tables.yaml** | Tables 28–29 (ASME lookup constants) |
| **project.ep2737.yaml** | BOM, customer, roles, materials, sections |
| **Reference DOCX (layout only)** | Cover, TOC, LOF, LOT, headers, footers, page borders |

Nothing is read from the reference Word **table cells** unless `use_word_table_data: true`.

## Regression / CI only

- `use_dpf_golden_fallback: false` (default) — production uses extracted RST/CAERep/Excel only.
- `use_dpf_golden_fallback: true` or `--golden-dpf` — CI regression only; fills gaps from `tests/fixtures/ep2737_golden/*.json`.
- `use_word_table_data: true` — enables Word-exported YAML (`ep2737_front_matter.yaml`, `ep2737_reference_tables.yaml`) for comparing against the sample EP2737 report.

## Pending live extraction

- DPF bolt mapping (`dpf_bolt.py`) — production bolt tables when `ANSYS_AVAILABLE=1`; until then fixtures fill tables when `use_dpf_golden_fallback` is on.

## Build commands

```bash
# Production — extracted data only (no golden fallback)
ansys-report build --config config/project.ep2737.yaml -v   # -v prints data source report

# CI without ANSYS — force golden fixtures
ansys-report build --config config/project.ep2737.yaml --golden-dpf

# Match sample report table text (Word YAML regression)
# set use_word_table_data: true in project.ep2737.yaml
```
