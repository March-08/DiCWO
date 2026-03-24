"""Prompt templates and builders for the DTHH mission design study."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Task descriptions (used by both centralized and dicwo systems)
# ---------------------------------------------------------------------------

TASK_DESCRIPTIONS = {
    "market_analysis": (
        "Analyze underserved communication regions, estimate the number of "
        "potential users, average data rate per user, and derive the total "
        "aggregated throughput required for the satellite constellation. "
        "Provide quantitative estimates with sources/reasoning.\n\n"
        "REFERENCE CONSTRAINTS — use these to sanity-check your derivation:\n"
        "• Total throughput = concurrent_users × data_rate_per_user. Double-check "
        "unit conversions: e.g. 1M users × 0.5 Mbps = 500 Gbps (NOT 0.5 Gbps). "
        "Show the multiplication step explicitly.\n"
        "• Concurrency ratio is typically 5–15% of total subscribers at peak hour.\n"
        "• Realistic per-user rates for DTHH: 0.1–1 Mbps (voice+data), not 10+ Mbps."
    ),
    "frequency_filing": (
        "Analyze ITU regulations, assess mobile phone G/T and EIRP values "
        "for direct communications with satellites, and select appropriate "
        "frequency bands and bandwidth to provide voice and broadband services "
        "for the estimated total throughput. Ensure ITU compliance.\n\n"
        "REFERENCE CONSTRAINTS — use these to sanity-check your values:\n"
        "• Standard smartphone transmit power: ~23 dBm (200 mW), i.e. EIRP ≈ 23 dBm "
        "(≈ −7 dBW). Values above 26 dBm or stated in tens of dBW are wrong.\n"
        "• Typical smartphone G/T: approximately −34 to −24 dB/K (depending on band "
        "and noise figure ~7-9 dB). Values outside this range need explicit justification.\n"
        "• DTHH bands: L-band (1.5–1.6 GHz, MSS allocation) and S-band (2.0–2.2 GHz) "
        "are the primary candidates. Wi-Fi / ISM bands are NOT suitable for MSS.\n"
        "• You MUST include a quantitative comparison table against at least one "
        "existing DTHH operator (AST SpaceMobile: 10 MHz L-band, ~5 MHz uplink; "
        "Lynk: sub-1 MHz narrowband; T-Mobile/SpaceX: mid-band PCS)."
    ),
    "payload_design": (
        "Generate full link budgets for the selected frequency band and "
        "bandwidth, for altitudes 400 km, 735 km, and 1100 km. Ensure that "
        "the proposed antennas are large enough to close the link budget. "
        "Validate against real-world implementations (e.g., AST SpaceMobile). "
        "Present each link budget in table format with power calculations, "
        "noise levels, and expected throughput. Calculate antenna directivity "
        "and beamwidth for each case.\n\n"
        "REFERENCE CONSTRAINTS — use these to sanity-check your calculations:\n"
        "• FSPL at L-band (1.6 GHz): ~158 dB at 400 km, ~163 dB at 735 km, "
        "~167 dB at 1100 km. Derive using 20·log10(4πd/λ), not approximations.\n"
        "• Antenna directivity: D ≈ π²d²/λ² (or 10·log10 of that in dBi). "
        "A 10 m reflector at 1.6 GHz yields ~44–45 dBi gain, NOT 30–32 dBi.\n"
        "• 3 dB beamwidth ≈ 70λ/d degrees. At 1.6 GHz: ~1.3° for 10 m, ~2.6° for 5 m.\n"
        "• AST SpaceMobile BlueWalker 3 reference: 64 m² phased array, ~693 beams, "
        "L/S-band, ~40 dBi+ gain. Your design should be in the same order of magnitude.\n"
        "• Link budget MUST close with positive margin (≥3 dB). If margin is negative, "
        "increase antenna size or transmit power — do not accept non-closing budgets.\n"
        "• Smartphone receive sensitivity: approximately −120 to −110 dBm for LTE-class "
        "waveforms. Use this to verify your downlink closes.\n"
        "• Use consistent units throughout: dBW for power, dBi for gain, dB for losses. "
        "Never mix dBm and dBW without explicit conversion (dBW = dBm − 30)."
    ),
    "mission_analysis": (
        "Using the beamwidth values from the Payload Expert, calculate the "
        "required number of satellites for each altitude (400 km, 735 km, "
        "1100 km). Determine the optimal altitude and constellation size for "
        "cost-effective global coverage. Verify against real-world DTHH "
        "satellites. Provide a launch cost analysis using Falcon 9 pricing."
    ),
    "integration": (
        "Review and integrate all specialist outputs to finalize the full "
        "satellite constellation design. Ensure that market demand, spectrum "
        "allocation, payload design, and mission parameters are internally "
        "consistent. Deliver the final validated system architecture with "
        "a cost-effectiveness analysis."
    ),
}

TASK_AGENT_MAP = {
    "market_analysis": "Market Analyst",
    "frequency_filing": "Frequency Filing Expert",
    "payload_design": "Payload Expert",
    "mission_analysis": "Mission Analyst",
    "integration": "Study Manager",
}

# ---------------------------------------------------------------------------
# Single-agent monolithic prompt
# ---------------------------------------------------------------------------

SINGLE_AGENT_SYSTEM_PROMPT = """\
You are a senior satellite systems engineer performing a complete Phase 0/A \
concurrent design study for a Direct-To-Handheld (DTHH) LEO satellite \
constellation. You must cover ALL of the following areas in a single, \
comprehensive response:

1. **Market Analysis**: Identify underserved regions, estimate user demand, \
derive total throughput requirements with quantitative data.

2. **Frequency Filing**: Select ITU-compliant frequency bands (reference \
AST SpaceMobile L-Band/S-Band), specify bandwidth, mobile phone G/T and \
EIRP values.

3. **Payload Design**: Generate link budget tables for 400 km, 735 km, and \
1100 km altitudes. Include transmit power, path loss, antenna gain, G/T, \
C/N, and achievable throughput. Calculate antenna diameter, directivity, \
and beamwidth for each altitude. Validate against AST SpaceMobile antenna \
sizes.

4. **Mission Analysis**: Calculate required number of satellites per altitude \
using the beamwidth values. Determine optimal constellation. Provide Falcon 9 \
launch cost estimates. Compare with existing constellations.

5. **Integration**: Ensure all subsystem outputs are consistent. Provide a \
final mission concept summary with selected orbit, number of satellites, \
link budget summary, and total mission cost estimate.

Use tables, quantitative values, and structured sections. Be specific — \
provide actual numbers, not ranges or vague estimates where possible.
"""

SINGLE_AGENT_USER_PROMPT = """\
Design a LEO satellite constellation for global direct-to-handheld (DTHH) \
communications service. The constellation must provide voice and broadband \
data services to standard unmodified smartphones.

Produce a complete Phase 0/A study covering market analysis, frequency \
planning, payload/link budget design (for 400 km, 735 km, 1100 km), \
constellation sizing, and a final integrated mission concept with cost \
estimates.
"""

# ---------------------------------------------------------------------------
# Centralized manager prompts
# ---------------------------------------------------------------------------

MANAGER_SYSTEM_PROMPT = """\
You are the Study Manager for a satellite constellation concurrent design \
study. Your role is to coordinate specialist agents to produce a complete \
Phase 0/A design for a Direct-To-Handheld (DTHH) LEO satellite constellation.

Available specialists:
- Market Analyst: demand estimation, underserved regions, throughput requirements
- Frequency Filing Expert: ITU bands, G/T, EIRP, spectrum compliance
- Payload Expert: link budgets, antenna sizing, RF design
- Mission Analyst: constellation sizing, orbit selection, cost analysis

You must decide which specialist to consult next and what specific task to \
give them. After all specialists have contributed, perform an integration \
pass to ensure consistency.

Respond with a JSON object:
{
  "next_agent": "<agent name>",
  "task": "<specific task description>",
  "context": "<relevant context from previous outputs>",
  "reasoning": "<why this agent is needed now>"
}

If all specialist work is complete, respond with:
{
  "next_agent": "DONE",
  "task": "integration",
  "reasoning": "<summary of readiness>"
}
"""

MANAGER_ROUTING_PROMPT = """\
Current state of the study:

{context}

Completed tasks: {completed_tasks}
Remaining budget: {remaining_rounds} rounds

Decide which specialist should work next and what specific task they should perform.
"""

INTEGRATION_PROMPT = """\
You are the Study Manager performing the final integration review.

Below are the outputs from all specialists:

{all_outputs}

Review all outputs for:
1. Internal consistency (do numbers match across subsystems?)
2. Completeness (are all required deliverables present?)
3. Technical soundness (are the engineering choices reasonable?)

Produce a final integrated mission concept report that includes:
- Selected orbit and justification
- Constellation size and configuration
- Finalized link budget summary
- Total mission cost estimate
- Key trade-offs and risks
"""

# ---------------------------------------------------------------------------
# Context injection template
# ---------------------------------------------------------------------------

CONTEXT_INJECTION = """\
The following outputs have been produced by other specialists in this study. \
Use this information to inform your work and ensure consistency:

{context}
"""
