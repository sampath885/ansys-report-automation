# EP2737 report phases (post Phase 7)

See **docs/DATA_POLICY.md** for what is live vs layout-only from the reference DOCX.

| Phase | Status | Description |
|-------|--------|-------------|
| 5 | **Deferred** | Images / Mechanical export (`skip_images: true`) |
| 8 | Done | Block renderer + live Excel/CAERep/standards tables |
| 9 | Done | Reference layout (cover/TOC/header/footer) — **not** table data |
| 10 | Pending | Live DPF bolt extraction (Tables 15, 17–22) |

## Production build (live RST/Excel/CAERep)

```bash
ansys-report build --config config/project.ep2737.yaml
python scripts/spikes/run_ep2737_build.py --out output/test_ep2737_build.docx
```

## CI without ANSYS

```bash
ansys-report build --config config/project.ep2737.yaml --golden-dpf
```

## Regression against sample report Word tables (opt-in)

Set `use_word_table_data: true` in `config/project.ep2737.yaml`.
