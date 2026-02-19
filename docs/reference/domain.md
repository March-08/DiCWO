# Domain: DTHH Satellite Constellation

## Problem Statement

Design a LEO satellite constellation for **Direct-To-Handheld (DTHH)** communications — voice and broadband data to standard unmodified smartphones, with global coverage.

This is a Phase 0/A concurrent design study covering five disciplines that must produce internally consistent outputs.

## The Five Subtasks

| # | Subtask | Assigned agent | Key deliverable |
|---|---------|---------------|-----------------|
| 1 | Market analysis | Market Analyst | User count, throughput requirements |
| 2 | Frequency filing | Frequency Expert | ITU-compliant bands, G/T, EIRP |
| 3 | Payload design | Payload Expert | Link budget tables for 3 altitudes |
| 4 | Mission analysis | Mission Analyst | Constellation size, orbit, cost |
| 5 | Integration | Study Manager | Consistent final design |

## Reference Data

### AST SpaceMobile

The primary real-world reference for DTHH:

| Parameter | Value |
|-----------|-------|
| Satellite | BlueBird (Block 2) |
| Altitude | 735 km |
| Antenna | ~64 m² phased array (~9 m equivalent diameter) |
| Mass | ~1,500 kg |
| Band | Low-band cellular (700–900 MHz) |
| Demonstrated | Voice calls and 4G data to unmodified smartphones |
| Planned constellation | 168 satellites |

### ITU Frequency Bands

| Band | Downlink (MHz) | Notes |
|------|---------------|-------|
| L-band | 1518–1559 | Used by Iridium, Globalstar. Good penetration. |
| S-band | 2170–2200 | AST SpaceMobile primary. Good smartphone compatibility. |
| Low-band cellular | 700–900 | 3GPP NTN standard. Existing handset support. |

### Smartphone RF Parameters

| Parameter | Typical value |
|-----------|--------------|
| EIRP | 23 dBm (200 mW) |
| G/T | −24 dB/K |
| Antenna gain | ~0 dBi |
| Noise figure | 7 dB |

### Falcon 9 Launch

| Parameter | Value |
|-----------|-------|
| LEO capacity | 22,800 kg |
| Cost | ~$67M per launch |
| Cost per kg | ~$2,720/kg |
| Reused booster | ~30% discount |
| Rideshare | ~$5,500/kg |

### Study Altitudes

| Altitude | Rationale |
|----------|-----------|
| **400 km** | Lower path loss, larger constellation, shorter orbital lifetime |
| **735 km** | AST SpaceMobile baseline, proven feasibility |
| **1100 km** | Fewer satellites, but larger antennas and higher latency |

## Implementation

Reference data is defined in `src/domain/reference_data.py` as Python constants. Domain parameters for the study are in `configs/domain/dthh_mission.yaml`.
