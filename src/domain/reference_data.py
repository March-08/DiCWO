"""Reference constants for the DTHH mission design study.

Sources: AST SpaceMobile filings, ITU Radio Regulations, SpaceX pricing,
standard RF engineering references.
"""

# ---------------------------------------------------------------------------
# AST SpaceMobile reference data
# ---------------------------------------------------------------------------
AST_SPACEMOBILE = {
    "bluebird_satellites": {
        "altitude_km": 735,
        "antenna_area_m2": 64,  # ~8m x 8m phased array
        "antenna_diameter_equiv_m": 9.0,
        "frequency_band": "Low-band cellular (700-900 MHz)",
        "mass_kg": 1500,
        "constellation_size_planned": 168,  # Block 2 target
    },
    "bluewalker3_test": {
        "altitude_km": 500,
        "antenna_area_m2": 64,
        "demonstrated": "Voice calls and 4G data to unmodified smartphones",
    },
}

# ---------------------------------------------------------------------------
# ITU frequency bands for DTHH
# ---------------------------------------------------------------------------
ITU_BANDS = {
    "L-band": {
        "range_mhz": (1518, 1559),  # Downlink
        "uplink_mhz": (1626.5, 1660.5),
        "typical_use": "MSS (Mobile Satellite Service)",
        "notes": "Used by Iridium, Globalstar. Good penetration, moderate bandwidth.",
    },
    "S-band": {
        "range_mhz": (2170, 2200),  # Downlink
        "uplink_mhz": (1980, 2010),
        "typical_use": "MSS supplemental ground component",
        "notes": "AST SpaceMobile primary band. Good smartphone compatibility.",
    },
    "Low-band cellular": {
        "range_mhz": (700, 900),
        "typical_use": "Terrestrial LTE reused for NTN",
        "notes": "3GPP NTN standard. Existing handset support. Shared spectrum.",
    },
}

# ---------------------------------------------------------------------------
# Smartphone RF parameters (typical values)
# ---------------------------------------------------------------------------
SMARTPHONE_RF = {
    "eirp_dbm": 23,  # 200 mW at antenna
    "gt_db_k": -24,  # G/T for typical smartphone
    "antenna_gain_dbi": 0,  # Isotropic approximation
    "noise_figure_db": 7,
}

# ---------------------------------------------------------------------------
# Falcon 9 launch parameters
# ---------------------------------------------------------------------------
FALCON_9 = {
    "leo_capacity_kg": 22_800,
    "cost_usd": 67_000_000,
    "cost_per_kg_usd": 2_720,  # ~$2,720/kg
    "reuse_discount": 0.7,  # Reused boosters ~30% cheaper
    "rideshare_cost_per_kg_usd": 5_500,  # Transporter missions
}

# ---------------------------------------------------------------------------
# Physics constants
# ---------------------------------------------------------------------------
SPEED_OF_LIGHT_M_S = 299_792_458
BOLTZMANN_DB = -228.6  # dBW/K/Hz
EARTH_RADIUS_KM = 6371

# ---------------------------------------------------------------------------
# Cost model bounds (sanity checks)
# ---------------------------------------------------------------------------
COST_BOUNDS = {
    "total_mission_min_usd": 100_000_000,   # $100M floor
    "total_mission_max_usd": 10_000_000_000,  # $10B ceiling
    "per_satellite_min_usd": 500_000,
    "per_satellite_max_usd": 50_000_000,
}

# ---------------------------------------------------------------------------
# Study altitudes
# ---------------------------------------------------------------------------
STUDY_ALTITUDES_KM = [400, 735, 1100]
