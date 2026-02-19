# Domain Validators

Deterministic physics and engineering checks — no LLM involved. Each validator scans the output text for specific claims and checks them against known bounds.

## Checks

| Validator | Scans for | Reasonable range | Example match |
|-----------|-----------|-----------------|---------------|
| **FSPL** | Free-space path loss values | 140–200 dB | `"FSPL = 165 dB"` |
| **Antenna size** | Antenna diameters | 1–50 m | `"antenna diameter: 9 m"` |
| **Constellation size** | Number of satellites | 5–5000 | `"168 satellites"` |
| **Cost bounds** | Total mission cost | $100M–$10B | `"$2.5 billion"` |

!!! info "Conservative bounds"
    The bounds are intentionally wide to avoid false negatives. They catch obviously wrong values (e.g., a 500 m antenna or a $50 mission) without penalizing reasonable designs.

## Output

```json title="evaluation.json (excerpt)"
{
  "validator_results": {
    "checks": [
      {
        "check": "fspl",
        "found_values_db": [165.2, 170.8],
        "reasonable_range": "140-200 dB",
        "pass": true
      },
      {
        "check": "cost_bounds",
        "found_costs_usd": [2500000000],
        "bounds": {"min": 100000000, "max": 10000000000},
        "pass": true
      }
    ],
    "total_checks": 4,
    "passed": 3,
    "verified_claims_ratio": 0.75
  }
}
```

## Physics Utilities

The validators expose helper functions useful for reference calculations:

```python
from src.evaluation.validators import fspl_db, antenna_gain_db, beamwidth_deg, coverage_sats

fspl_db(2e9, 735e3)           # → 155.8 dB (FSPL for 2 GHz at 735 km)
antenna_gain_db(9.0, 2e9)     # → 43.3 dBi (9m dish at 2 GHz)
beamwidth_deg(9.0, 2e9)       # → 1.17° (half-power beamwidth)
coverage_sats(735, 1.17)      # → satellites needed for global coverage
```

## Implementation

:material-file-code: `src/evaluation/validators.py`
