"""Render smoke tests."""

from pathlib import Path

from docx import Document

from ansys_report.config import load_project_config
from ansys_report.report.context_builder import build_context, load_mock_results
from ansys_report.report.render import render_report


def test_render_smoke(repo_root, fixtures_dir, template_path, tmp_path):
    cfg = load_project_config(
        repo_root / "config" / "project.example.yaml",
        project_dir_override=fixtures_dir,
    )
    mock = load_mock_results(fixtures_dir / "mock_results.json")
    ctx, _ = build_context(cfg, mock_data=mock)

    out = tmp_path / "smoke_report.docx"
    render_report(template_path, ctx, out)

    assert out.exists()
    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "EP 1763" in text or "MOCK" in text
    assert "210.5" in text or "stress" in text.lower()
