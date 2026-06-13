"""Run isolated DPF jobs in a subprocess (timeout-safe on Windows)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ping_model(rst_path: Path) -> dict:
    from ansys.dpf import core as dpf

    model = dpf.Model(str(rst_path))
    mesh = model.metadata.meshed_region
    return {
        "ok": True,
        "nodes": int(mesh.nodes.n_nodes),
        "elements": int(mesh.elements.n_elements),
    }


def _mesh_quality(rst_path: Path) -> dict:
    from ansys_report.extract.dpf_mesh import compute_mesh_quality_metrics

    metrics = compute_mesh_quality_metrics(rst_path, use_subprocess=False)
    return {"ok": True, "metrics": metrics}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DPF subprocess worker")
    parser.add_argument("command", choices=["ping", "mesh_quality"])
    parser.add_argument("rst_path", type=Path)
    args = parser.parse_args(argv)

    if not args.rst_path.exists():
        print(json.dumps({"ok": False, "error": f"RST not found: {args.rst_path}"}))
        return 1

    try:
        if args.command == "ping":
            payload = _ping_model(args.rst_path)
        else:
            payload = _mesh_quality(args.rst_path)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
