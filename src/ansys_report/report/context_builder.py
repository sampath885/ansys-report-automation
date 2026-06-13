"""Assemble validated render context from section plugins."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ansys_report.config import ProjectConfig, ValidationReport, ai_enabled, load_thresholds
from ansys_report.models import ProjectInventory, SectionVerdict
from ansys_report.narrative import rules
from ansys_report.narrative.ai import polish_narrative
from ansys_report.models import Narrative
from ansys_report.sections.design_calcs import DesignCalcsSection
from ansys_report.sections.equipment import (
    EquipmentSection,
    ModellingSection,
    ReferencesSection,
    RevisionSection,
    ScopeSection,
    SoftwareSection,
)
from ansys_report.sections.harmonic import harmonic_sections
from ansys_report.sections.modal import ModalSection
from ansys_report.sections.reference_only import LoadsSection, MaterialsSection
from ansys_report.sections.shock import ShockSection
from ansys_report.sections.static_structural import StaticStructuralSection

logger = logging.getLogger(__name__)

ALL_SECTIONS = [
    RevisionSection(),
    ScopeSection(),
    SoftwareSection(),
    ReferencesSection(),
    EquipmentSection(),
    ModellingSection(),
    LoadsSection(),
    MaterialsSection(),
    ModalSection(),
    StaticStructuralSection(),
    *harmonic_sections(),
    ShockSection(),
    DesignCalcsSection(),
]


def get_enabled_sections(cfg: ProjectConfig):
    return [s for s in ALL_SECTIONS if s.is_enabled(cfg)]


def load_mock_results(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_context(
    cfg: ProjectConfig,
    inventory: ProjectInventory | None = None,
    mock_data: dict[str, Any] | None = None,
    use_ai: bool = True,
    images: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ValidationReport]:
    validation = ValidationReport()
    ctx: dict[str, Any] = {
        "bom_id": cfg.bom_id,
        "title": cfg.title,
        "customer": cfg.customer,
        "prepared_by": cfg.prepared_by.model_dump(),
        "checked_by": cfg.checked_by.model_dump(),
        "approved_by": cfg.approved_by.model_dump(),
        "ansys_version": cfg.ansys_version,
        "sections": {},
        "images": images or {},
    }

    if mock_data:
        ctx.update(mock_data)
        ctx["images"] = images or mock_data.get("images", {})
        return ctx, validation

    if inventory is None:
        validation.add("inventory", "No project inventory provided", "error")
        return ctx, validation

    verdicts: list[SectionVerdict] = []
    thresholds = load_thresholds(cfg.thresholds_path)

    for section in get_enabled_sections(cfg):
        data = section.extract(inventory, cfg)
        narrative_data = section.narrate(data, cfg)

        if use_ai and ai_enabled():
            draft = Narrative(**{k: narrative_data.get(k, v) for k, v in {
                "observations": [], "conclusions": [], "recommendations": [],
                "verdict": "PASS", "source": "rules"
            }.items()})
            if hasattr(section, "key") and section.key in ("static", "modal"):
                polished = polish_narrative(
                    draft,
                    {"section": section.key, "data": data},
                    rules_prompt_for(section.key),
                )
                narrative_data = polished.model_dump()

        fragment = section.context(data, narrative_data)
        ctx.update(fragment)
        if section.key in ("revision", "scope", "software", "references", "equipment", "modelling", "loads", "materials"):
            ctx["sections"][section.key] = fragment.get(section.key, fragment)

        for field in data.get("manual_fields", []):
            validation.add("dpf", f"{section.key}: manual entry required for {field}", "warning")

        if narrative_data.get("verdict"):
            verdicts.append(
                SectionVerdict(
                    section=section.key,
                    verdict=narrative_data.get("verdict", "PASS"),
                    observations=narrative_data.get("observations", []),
                    conclusions=narrative_data.get("conclusions", []),
                )
            )

    exec_summary = rules.build_executive_summary(verdicts)
    ctx["narrative"] = {
        "executive_summary": exec_summary,
        "verdicts": [v.model_dump() for v in verdicts],
    }
    return ctx, validation


def rules_prompt_for(section_key: str) -> str:
    from ansys_report.narrative import prompts

    if section_key == "static":
        return prompts.STATIC_PROMPT
    if section_key == "modal":
        return prompts.MODAL_PROMPT
    return prompts.EXECUTIVE_PROMPT
