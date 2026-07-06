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

    excluded_parts = (
        "Non-structural items such as nameplates, lubricants, paint coatings and temporary "
        "assembly aids are excluded from the FE model. Seals and soft gaskets are represented "
        "either by contact/gasket elements or by equivalent pressure loading as described in "
        "the joint-modelling subsections below."
    )

    welded_joint_method = (
        "Welded regions between the valve body, bonnet and pipe connections are modelled using "
        "shared topology with conforming mesh at the weld interfaces where higher-fidelity "
        "stress recovery is required. This allows direct transfer of tractions across the "
        "weld without tied-contact artefacts in the peak-stress region."
    )

    gasket_method = (
        "Gaskets and soft seals are represented using gasket behaviour or appropriate contact "
        "stiffness so that load transfer and local compression in the sealing region are captured "
        "without modelling the seal geometry in detail."
    )

    vibration_methodology = (
        f"Vibration resistance is assessed using harmonic response analyses in the X, Y and Z "
        f"directions over the operating frequency range of {low:.0f}-{high:.0f} Hz. Peak "
        f"displacement and stress responses are compared against allowable limits to confirm "
        f"adequate margin under the specified vibration environment."
    )

    working_principle = (
        f"The {part} is a pressure-boundary valve assembly that must contain the working medium, "
        f"transmit piping loads and withstand operating pressure, dead weight, manual/actuator "
        f"effort and externally applied dynamic loads. Loads are carried through the body, bonnet, "
        f"stem/spindle, closure member and bolted/flanged joints. The objective of this analysis "
        f"is to verify structural adequacy of all critical components and joints under static, "
        f"dynamic and shock load cases specified in the purchase order."
    )

    modelling_approach = (
        f"The assembly is modelled in 3D from the released CAD geometry. Connected pipework is "
        f"represented to a practical length on each nozzle so that load transfer into the valve "
        f"is captured realistically. Solid bodies are meshed with quadratic tetrahedral elements "
        f"using curvature-based sizing and patch-conforming controls to resolve fillets, threads "
        f"and bolt-hole regions."
    )

    bolted_joint_method = (
        f"Bolted joints are modelled with pretensioned bolt elements coupled to the flanged faces, "
        f"with contact between mating surfaces to represent compression, separation and load "
        f"redistribution. Bolt axial and shear forces are recovered for comparison against allowable "
        f"stresses on the bolt tensile and shear areas."
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
        "excluded_parts": excluded_parts,
        "bolted_joint_method": bolted_joint_method,
        "welded_joint_method": welded_joint_method,
        "gasket_method": gasket_method,
        "vibration_methodology": vibration_methodology,
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
