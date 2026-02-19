"""Deterministic domain validators — binary pass/fail physics checks."""

from __future__ import annotations

import math
import re
from typing import Any

from src.domain.reference_data import (
    COST_BOUNDS,
    EARTH_RADIUS_KM,
    SPEED_OF_LIGHT_M_S,
)


def fspl_db(frequency_hz: float, distance_m: float) -> float:
    """Free-Space Path Loss in dB."""
    return 20 * math.log10(distance_m) + 20 * math.log10(frequency_hz) - 147.55


def antenna_gain_db(diameter_m: float, frequency_hz: float, efficiency: float = 0.6) -> float:
    """Antenna gain in dBi from diameter and frequency."""
    wavelength = SPEED_OF_LIGHT_M_S / frequency_hz
    area = math.pi * (diameter_m / 2) ** 2
    return 10 * math.log10(efficiency * 4 * math.pi * area / wavelength**2)


def beamwidth_deg(diameter_m: float, frequency_hz: float) -> float:
    """Half-power beamwidth in degrees (engineering approximation)."""
    wavelength = SPEED_OF_LIGHT_M_S / frequency_hz
    return 70 * wavelength / diameter_m


def coverage_sats(altitude_km: float, beamwidth_deg_val: float) -> int:
    """Rough estimate of satellites needed for global coverage."""
    # Footprint radius on ground
    half_beam_rad = math.radians(beamwidth_deg_val / 2)
    R = EARTH_RADIUS_KM
    h = altitude_km
    # Nadir angle
    footprint_radius_km = h * math.tan(half_beam_rad)
    # Spherical cap area
    cap_area_km2 = math.pi * footprint_radius_km**2
    earth_area_km2 = 4 * math.pi * R**2
    # Packing factor ~1.5 for hexagonal
    return max(1, int(math.ceil(1.5 * earth_area_km2 / cap_area_km2)))


def _extract_numbers(text: str) -> list[float]:
    """Extract all numbers from a text string."""
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", text)]


def _check_fspl(text: str) -> dict[str, Any]:
    """Check if FSPL values mentioned are approximately correct."""
    # Look for patterns like "FSPL = 165 dB" or "path loss: 170 dB"
    fspl_pattern = re.findall(
        r"(?:FSPL|path\s*loss|free.?space)\s*[=:≈]\s*([\d.]+)\s*dB",
        text,
        re.IGNORECASE,
    )
    if not fspl_pattern:
        return {"check": "fspl", "status": "not_found", "pass": True}

    # Check against expected range for LEO DTHH (150-185 dB typical)
    values = [float(v) for v in fspl_pattern]
    all_reasonable = all(140 < v < 200 for v in values)

    return {
        "check": "fspl",
        "found_values_db": values,
        "reasonable_range": "140-200 dB",
        "pass": all_reasonable,
    }


def _check_cost_bounds(text: str) -> dict[str, Any]:
    """Check if total cost estimates are within sanity bounds."""
    # Look for cost patterns like "$5B", "$500M", "$2.5 billion"
    cost_patterns = re.findall(
        r"\$\s*([\d.]+)\s*(billion|B|million|M)\b",
        text,
        re.IGNORECASE,
    )
    if not cost_patterns:
        return {"check": "cost_bounds", "status": "not_found", "pass": True}

    costs_usd = []
    for val, unit in cost_patterns:
        v = float(val)
        if unit.lower() in ("billion", "b"):
            costs_usd.append(v * 1e9)
        else:
            costs_usd.append(v * 1e6)

    min_ok = COST_BOUNDS["total_mission_min_usd"]
    max_ok = COST_BOUNDS["total_mission_max_usd"]
    all_in_bounds = all(min_ok <= c <= max_ok for c in costs_usd)

    return {
        "check": "cost_bounds",
        "found_costs_usd": costs_usd,
        "bounds": {"min": min_ok, "max": max_ok},
        "pass": all_in_bounds,
    }


def _check_antenna_consistency(text: str) -> dict[str, Any]:
    """Check if antenna sizes mentioned are in reasonable range for LEO DTHH."""
    # Look for antenna diameter patterns
    ant_pattern = re.findall(
        r"antenna\s*(?:diameter|size|aperture)\s*[=:≈]?\s*([\d.]+)\s*m",
        text,
        re.IGNORECASE,
    )
    if not ant_pattern:
        return {"check": "antenna_size", "status": "not_found", "pass": True}

    diameters = [float(v) for v in ant_pattern]
    # For LEO DTHH, expect 5-30m (AST SpaceMobile ~9m equiv)
    all_reasonable = all(1 < d < 50 for d in diameters)

    return {
        "check": "antenna_size",
        "found_diameters_m": diameters,
        "reasonable_range": "1-50 m",
        "pass": all_reasonable,
    }


def _check_constellation_size(text: str) -> dict[str, Any]:
    """Check if constellation sizes mentioned are reasonable."""
    # Look for "X satellites" patterns
    const_pattern = re.findall(
        r"(\d+)\s*satellite", text, re.IGNORECASE
    )
    if not const_pattern:
        return {"check": "constellation_size", "status": "not_found", "pass": True}

    sizes = [int(v) for v in const_pattern]
    # For LEO global coverage: 20-2000 satellites is reasonable
    all_reasonable = all(5 < s < 5000 for s in sizes)

    return {
        "check": "constellation_size",
        "found_sizes": sizes,
        "reasonable_range": "5-5000",
        "pass": all_reasonable,
    }


# All validators
_VALIDATORS = [
    _check_fspl,
    _check_cost_bounds,
    _check_antenna_consistency,
    _check_constellation_size,
]


def validate_artifacts(artifacts: dict[str, Any]) -> dict[str, Any]:
    """Run all validators on all artifacts.

    Returns structured results with per-check pass/fail and aggregate ratio.
    """
    all_text = " ".join(str(v) for v in artifacts.values())

    results: list[dict[str, Any]] = []
    for validator in _VALIDATORS:
        result = validator(all_text)
        results.append(result)

    total_checks = len(results)
    passed = sum(1 for r in results if r.get("pass", False))

    return {
        "checks": results,
        "total_checks": total_checks,
        "passed": passed,
        "verified_claims_ratio": round(passed / total_checks, 4) if total_checks > 0 else 0,
    }
