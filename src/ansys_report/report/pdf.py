"""Local DOCX to PDF conversion."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_to_pdf(docx_path: Path, pdf_path: Path | None = None) -> Path | None:
    pdf_path = pdf_path or docx_path.with_suffix(".pdf")

    result = _try_docx2pdf(docx_path, pdf_path)
    if result:
        return result

    result = _try_libreoffice(docx_path, pdf_path.parent)
    if result:
        return result

    logger.warning(
        "PDF export unavailable (install Microsoft Word + docx2pdf, or LibreOffice). "
        "DOCX was still generated: %s",
        docx_path,
    )
    return None


def _try_docx2pdf(docx_path: Path, pdf_path: Path) -> Path | None:
    try:
        from docx2pdf import convert

        convert(str(docx_path), str(pdf_path))
        if pdf_path.exists():
            logger.info("Wrote PDF via docx2pdf: %s", pdf_path)
            return pdf_path
    except Exception as exc:
        logger.debug("docx2pdf failed: %s", exc)
    return None


def _try_libreoffice(docx_path: Path, out_dir: Path) -> Path | None:
    for cmd in ("soffice", "libreoffice"):
        exe = shutil.which(cmd)
        if not exe:
            continue
        try:
            subprocess.run(
                [exe, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)],
                check=True,
                capture_output=True,
            )
            pdf = out_dir / docx_path.with_suffix(".pdf").name
            if pdf.exists():
                logger.info("Wrote PDF via LibreOffice: %s", pdf)
                return pdf
        except Exception as exc:
            logger.debug("LibreOffice conversion failed: %s", exc)
    return None


def pdf_available() -> bool:
    try:
        import docx2pdf  # noqa: F401

        return True
    except ImportError:
        pass
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))
