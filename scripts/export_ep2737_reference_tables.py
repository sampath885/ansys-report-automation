"""Static reference tables from Design Report_EP2737_UPDATED.docx.

Prefer the fast exporter: python scripts/export_ep2737_tables_fast.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    import importlib.util

    fast = ROOT / "scripts" / "export_ep2737_tables_fast.py"
    spec = importlib.util.spec_from_file_location("export_ep2737_tables_fast", fast)
    if spec is None or spec.loader is None:
        raise RuntimeError("export_ep2737_tables_fast.py not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main()


if __name__ == "__main__":
    raise SystemExit(main())
