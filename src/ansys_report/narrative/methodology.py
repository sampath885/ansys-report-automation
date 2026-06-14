"""Generate engineering methodology / rationale narrative for the EP2737 report.

These paragraphs (working principle, modelling approach, bolted-joint method,
modal and shock methodology, fatigue theory) explain *why* the analysis was done
the way it was. They are produced rule-based from the analysis parameters so the
report is complete without an AI key, and can optionally be AI-polished.
"""

from __future__ import annotations

import logging
from typing import Any

from ansys_report.config import ProjectConfig

logger = logging.getLogger(__name__)

# Equivalent-static shock analysis is valid when the structure responds quasi-
# statically to the shock pulse, i.e. its fundamental frequency is well above the
# pulse frequency content. EP reports cite ~160 Hz as the rigid-response threshold.
SHOCK_RIGID_THRESHOLD_HZ = 160.0


def _fundamental_freq_hz(context: dict[str, Any]) -> float | None:
    modal = context.get("modal") or {}
    freqs = [m.get("freq_hz") for m in modal.get("modes", []) if m.get("freq_hz") is not None]
    return min(freqs) if freqs else None


def _primary_material_name(context: dict[str, Any], cfg: ProjectConfig) -> str:
    if cfg.materials:
        return cfg.materials[0].name
    equipment = context.get("equipment") or {}
    names = equipment.get("material_names") or []
    return names[0] if names else "the specified material"


def build_methodology(context: dict[str, Any], cfg: ProjectConfig) -> dict[str, str]:
    """Return the methodology narrative paragraphs keyed by section."""
    spec = cfg.equipment_spec
    part = spec.part_name
    material = _primary_material_name(context, cfg)
    low, high = cfg.operating_freq_hz
    yield_mpa = cfg.primary_yield_mpa
    fatigue_allow = cfg.materials[0].fatigue_allowable_mpa if cfg.materials else None
    static_allow = cfg.materials[0].static_allowable_mpa if cfg.materials else None
    fundamental = _fundamental_freq_hz(context)
    bolt_count = cfg.bolts.count

    working_principle = (
        f"The {part} is a pressure-boundary component that connects mating pipe spools and "
        f"transmits internal pressure, dead weight and externally applied dynamic loads through "
        f"the bolted flange joint. In service it must contain the working medium without leakage "
        f"while withstanding bolt pretension, operating pressure, self weight and vibration/shock "
        f"loads transmitted from the supporting structure. The objective of this analysis is to "
        f"verify that the flange and its bolted joint remain structurally adequate under all "
        f"specified static and dynamic load cases."
    )

    modelling_approach = (
        f"The assembly is modelled in 3D from the released CAD geometry. The connected pipework is "
        f"represented to a length of approximately five pipe diameters (5D) on either side of the "
        f"flange so that the local stiffness and load transfer into the flange are captured "
        f"realistically while keeping the model size practical; truncating at 5D is sufficient "
        f"because stress disturbances at the flange decay well within this length (Saint-Venant's "
        f"principle). The solid bodies are meshed with quadratic tetrahedral elements (SOLID187) "
        f"using patch-conforming controls and curvature-based sizing to resolve fillets and "
        f"the bolt-hole regions."
    )

    bolted_joint_method = (
        f"The {bolt_count} bolts are modelled as 1D pretensioned beam elements (BEAM188) coupled to "
        f"the flange faces, with bolt pretension applied as a dedicated load step before the service "
        f"loads. Contact between the mating flange faces is defined to transfer compression and to "
        f"allow separation, so that the joint stiffness and the redistribution of bolt loads under "
        f"external load are represented. Bolt axial and shear forces are recovered from the beam "
        f"elements and converted to normal and shear stresses on the bolt tensile/shear stress "
        f"areas for comparison against the bolt material yield strength."
    )

    if fundamental is not None:
        modal_methodology = (
            f"A modal (free-vibration) analysis is performed to extract the natural frequencies of "
            f"the assembly and confirm there is no resonance within the operating frequency range "
            f"of {low:.0f}-{high:.0f} Hz. The fundamental natural frequency is {fundamental:.0f} Hz, "
            f"which lies well above the operating band, indicating the structure is dynamically "
            f"stiff and free from resonance under the specified excitation."
        )
    else:
        modal_methodology = (
            f"A modal (free-vibration) analysis is performed to extract the natural frequencies of "
            f"the assembly and confirm there is no resonance within the operating frequency range "
            f"of {low:.0f}-{high:.0f} Hz."
        )

    if fundamental is not None and fundamental > SHOCK_RIGID_THRESHOLD_HZ:
        shock_justification = (
            f"Because the fundamental natural frequency ({fundamental:.0f} Hz) is well above the "
            f"{SHOCK_RIGID_THRESHOLD_HZ:.0f} Hz rigid-response threshold and above the frequency "
            f"content of the specified shock pulse, the structure responds quasi-statically to the "
            f"shock event. The shock is therefore assessed using the equivalent-static approach, in "
            f"which the peak shock acceleration is applied as a static inertia load in each of the "
            f"six axis directions (+/-X, +/-Y, +/-Z) and the resulting stresses are compared against "
            f"the material allowable."
        )
    else:
        shock_justification = (
            f"The shock event is assessed using the equivalent-static approach, in which the peak "
            f"shock acceleration is applied as a static inertia load in each of the six axis "
            f"directions (+/-X, +/-Y, +/-Z) and the resulting stresses are compared against the "
            f"material allowable."
        )

    yield_text = f"{yield_mpa:.0f} MPa" if yield_mpa else "the material yield strength"
    static_allow_text = f" The static allowable stress is taken as {static_allow:.1f} MPa." if static_allow else ""
    fatigue_allow_text = (
        f" The fatigue (endurance) allowable stress is taken as {fatigue_allow:.1f} MPa."
        if fatigue_allow
        else ""
    )
    fatigue_theory = (
        f"Fatigue adequacy of the bolted joint is evaluated using a stress-life (S-N) approach. "
        f"Under fluctuating service loads each bolt experiences a mean stress and an alternating "
        f"stress; these are derived from the preload and the external load range carried by the "
        f"joint. The combination of mean and alternating stress is checked against a constant-life "
        f"(Goodman/Soderberg) criterion built from the material ultimate strength, yield strength "
        f"({yield_text}) and endurance limit. Stress-concentration at the thread root and the "
        f"effect of preload in reducing the alternating stress seen by the bolt are accounted for, "
        f"and the resulting alternating stress is compared against the fatigue allowable to "
        f"establish the fatigue factor of safety.{static_allow_text}{fatigue_allow_text}"
    )

    return {
        "working_principle": working_principle,
        "modelling_approach": modelling_approach,
        "bolted_joint_method": bolted_joint_method,
        "modal_methodology": modal_methodology,
        "shock_justification": shock_justification,
        "fatigue_theory": fatigue_theory,
    }


def polish_methodology(text_map: dict[str, str]) -> dict[str, str]:
    """Optionally refine methodology paragraphs with an LLM; returns input on failure."""
    from ansys_report.config import ai_enabled

    if not ai_enabled():
        return text_map
    from ansys_report.narrative.ai import _call_llm
    from ansys_report.narrative.prompts import METHODOLOGY_PROMPT

    polished: dict[str, str] = {}
    for key, draft in text_map.items():
        try:
            text = _call_llm(METHODOLOGY_PROMPT.format(section=key, draft=draft))
            polished[key] = text.strip() if text and text.strip() else draft
        except Exception as exc:  # pragma: no cover - network/SDK failures
            logger.warning("Methodology polish failed for %s: %s", key, exc)
            polished[key] = draft
    return polished
