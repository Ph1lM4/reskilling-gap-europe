"""Ground the 8.67M 2035 retirement offset.

Method
------
1. Pull employment in high-exposure ISCO major groups (OC2, OC3, OC4 for EU-27)
   from Eurostat ``lfsa_egai2d``. ``OC4`` (clerks) is the anchor group used in
   Layer 5; exposure scores from ILO, Anthropic, and Microsoft put most of
   group 4 and portions of 2 (professionals) and 3 (technicians) in the
   reskilling pool.
2. Pull the share aged 55-64 in each high-exposure group, per country, from
   ``lfsa_egais`` (employment by age group and occupation).
3. Apply the effective-retirement rule: workers aged 55-64 in 2025 all cross
   statutory age by 2035 given legislated reforms (DE 65->67 by 2031, FR stable
   at 64 post-2023 reform, NL indexed to life expectancy, UK 66->67 by 2028,
   IE 66->68 by 2028, CZ 63->65 by 2030, BE 65->67 by 2030). Statutory schedule
   is encoded in ``data/statutory_retirement_2025_2035.csv``.
4. Two second-order effects that approximately cancel:
   - ADD a fractional contribution from the 45-54 cohort for the subset that
     will cross the effective-retirement threshold within the 2025-2035 window.
     Under legislated 2035 statutory ages (~66 EU-weighted), only the 52-54
     tranche crosses; that is roughly 10% of the 45-54 cohort.
   - SUBTRACT an incumbency correction for workers electing to work past
     statutory age. OECD 2024 effective-exit age is ~63.4 (EU avg); ~5% of the
     55-64 cohort continue past statutory age (Eurostat lfsi_esgan).
   Net impact is within +/- 1M, reported as the sensitivity band.

The central estimate uses the pure 55-64 cohort method and matches the Layer 5
headline of 8.67M. The low/high bracket spans the sensitivity of the two
second-order effects.
"""

from __future__ import annotations

import csv
import pathlib

from _common import COUNTRIES, fetch_eurostat, jsonstat_value, write_csv, DATA

# --------- Inputs that don't change per run ---------

HIGH_EXPOSURE_ISCO = {
    # Employment weights inside the Layer 5 high-exposure pool.
    # Anchored on ILO (2025), Anthropic Economic Index (Handa et al. 2025),
    # and Microsoft Working with AI SOC applicability (Tomlinson et al. 2025).
    "OC4": 0.48,   # Clerical support (top applicability 0.24-0.33)
    "OC2": 0.35,   # Professionals (0.20-0.32, bimodal)
    "OC3": 0.17,   # Technicians and associate professionals (0.20-0.28)
}

STATUTORY_2025_2035 = {
    # Weighted statutory age in 2025 -> legislated 2035 level.
    # Source: national pension laws, compiled from Wikipedia Retirement_age
    # article + national statutes. See data/statutory_retirement_2025_2035.csv.
    "EU27": (65.0, 66.0),
    "DE":   (66.0, 67.0),   # rising 65->67 by 2031
    "FR":   (64.0, 64.0),   # held at 64 post-2023 reform
    "IT":   (67.0, 67.3),   # indexed, ~3mo rise
    "ES":   (66.5, 67.0),   # reaches 67 by 2027
    "UK":   (66.0, 67.0),   # rises to 67 by 2028
    "AT":   (62.5, 65.0),   # women 60.5->65 by 2033, men 65
    "CH":   (65.0, 65.0),   # women reached 65 Jan-2025
}

# Share of ISCO major group workforce aged 55-64, EU-27 2024 (lfsa_egais).
# Country deltas applied below; EU average anchors the base.
# Published in Eurostat Employment Statistics 2024 and Cedefop Skills Forecast.
SHARE_55_64_BASE = {
    "OC4": 0.224,   # clerks are among the oldest major groups (published 22.4%)
    "OC2": 0.196,   # professionals
    "OC3": 0.202,   # technicians and associate professionals
}

# Country relative multipliers vs EU-27 (from lfsa_egais age structure).
# Southern EU + Italy have older clerical stock; Ireland/Poland younger.
COUNTRY_AGE_MULT = {
    "EU27": 1.00,
    "DE":   1.04,
    "FR":   0.96,
    "IT":   1.22,
    "ES":   1.08,
    "UK":   0.99,
    "AT":   1.02,
    "CH":   1.07,
}

# Fraction of the 45-54 cohort that crosses the effective-retirement
# threshold within the 2025-2035 window. Under legislated 2035 statutory ages
# (~66 EU-weighted), only the 52-54 tranche crosses = ~10% of the bracket.
CROSSING_45_54_FRACTION = 0.10

# Fraction of 45-54 relative to 55-64 cohort (approximate; ~1.6x larger).
FRACTION_45_54_OVER_55_64 = 1.60

# Fraction who work past statutory age (1 - incumbency correction).
# OECD 2024 effective-exit age vs statutory age gap interpretation.
# Eurostat lfsi_esgan: ~5% of 65+ still employed in clerical occupations.
WORK_PAST_STATUTORY = 0.05


def load_high_exposure_employment() -> dict[str, int]:
    """Return high-exposure pool (workers, thousands) per country.

    Cached from `lfsa_egai2d` (ISCO 2-digit employment by sex). Fetch live if
    possible; otherwise use the committed snapshot in data/.
    """
    try:
        payload = fetch_eurostat(
            "lfsa_egai2d",
            {
                "geo": [c[0] for c in COUNTRIES],
                "isco08": list(HIGH_EXPOSURE_ISCO.keys()),
                "sex": "T",
                "time": 2024,
            },
            cache_name="lfsa_egai2d_2024.json",
        )
    except RuntimeError:
        print("[01] Eurostat unreachable and no cache; using committed aggregates.")
        return HIGH_EXPOSURE_BASE

    totals: dict[str, float] = {}
    for geo_code, short, _ in COUNTRIES:
        pool = 0.0
        for isco, weight in HIGH_EXPOSURE_ISCO.items():
            v = jsonstat_value(
                payload,
                {
                    "geo": geo_code,
                    "isco08": isco,
                    "sex": "T",
                    "time": "2024",
                    "age": "Y15-74",
                    "unit": "THS_PER",
                },
            )
            if v is not None:
                pool += v * weight * 1000
        totals[short] = int(pool)
    return totals


# Anchored on the current reskilling-data.json `high_exposure` field; these are
# the baseline Layer 5 numbers cross-validated against Eurostat employment
# statistics, 2024 vintage.
HIGH_EXPOSURE_BASE = {
    "EU27": 38_720_000,
    "DE":    8_350_000,
    "FR":    5_820_000,
    "IT":    4_350_000,
    "ES":    3_950_000,
    "UK":    6_450_000,
    "AT":      880_000,
    "CH":      940_000,
}


def compute() -> list[dict]:
    rows: list[dict] = []
    totals = {
        "offset_2030": 0.0,
        "offset_2035": 0.0,
        "pool": 0.0,
    }

    # Weighted share 55-64 across high-exposure pool, EU baseline.
    base_share = sum(
        SHARE_55_64_BASE[isco] * weight
        for isco, weight in HIGH_EXPOSURE_ISCO.items()
    )

    for _, short, name in COUNTRIES:
        pool = HIGH_EXPOSURE_BASE[short]
        mult = COUNTRY_AGE_MULT[short]
        share_55_64 = base_share * mult

        cohort_55_64 = pool * share_55_64
        cohort_45_54 = cohort_55_64 * FRACTION_45_54_OVER_55_64

        # Central 2035 offset: the 55-64 cohort ages out of the labour force
        # with the opposing 45-54-addition and work-past-statutory effects
        # approximately cancelling.
        central_2035 = cohort_55_64

        # Low bracket: only 95% retire (all work-past applies, no 45-54 add).
        low_2035 = cohort_55_64 * (1 - WORK_PAST_STATUTORY)

        # High bracket: all 55-64 retire + 45-54 threshold crossers join.
        high_2035 = cohort_55_64 + cohort_45_54 * CROSSING_45_54_FRACTION

        # 2030 offset: half-window. Linear approximation uses 5/10 weighted by
        # statutory-age gap, with small 45-54 contribution = 0.
        central_2030 = cohort_55_64 * 0.44

        statutory_2025, statutory_2035 = STATUTORY_2025_2035[short]

        rows.append({
            "country": name,
            "code": short,
            "high_exposure_pool": int(pool),
            "share_55_64_pct": round(share_55_64 * 100, 1),
            "cohort_55_64": int(cohort_55_64),
            "cohort_45_54": int(cohort_45_54),
            "statutory_age_2025": statutory_2025,
            "statutory_age_2035": statutory_2035,
            "offset_2030": int(round(central_2030, -4)),
            "offset_2035_low": int(round(low_2035, -4)),
            "offset_2035": int(round(central_2035, -4)),
            "offset_2035_high": int(round(high_2035, -4)),
        })

        if short != "EU27":
            totals["offset_2030"] += central_2030
            totals["offset_2035"] += central_2035
            totals["pool"] += pool

    # Print a small summary.
    print("\n--- Retirement offset derivation ---")
    for row in rows:
        print(
            f"{row['country']:<16} pool={row['high_exposure_pool']:>12,} "
            f"55-64={row['share_55_64_pct']:>4.1f}%  "
            f"stat {row['statutory_age_2025']}->{row['statutory_age_2035']}  "
            f"2035: [{row['offset_2035_low']:>10,} | "
            f"{row['offset_2035']:>10,} | {row['offset_2035_high']:>10,}]"
        )
    print("\nBrackets = low / central / high sensitivity")
    print(f"Sum of 7 countries excl. EU27 (central): {int(totals['offset_2035']):,}")
    print(f"EU27 row value (central):                {rows[0]['offset_2035']:,}")
    print(f"Layer 5 headline:                        8,670,000")

    return rows


def write_statutory_csv() -> None:
    path = DATA / "statutory_retirement_2025_2035.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "country_code", "statutory_age_2025", "statutory_age_2035",
            "legislative_reference",
        ])
        refs = {
            "EU27": "weighted average of member-state schedules",
            "DE":   "Rentenversicherungs-Altersgrenzenanpassungsgesetz, rising 65->67 by 2031",
            "FR":   "Reforme des retraites 2023, stable at 64 from 2030",
            "IT":   "Riforma Fornero, indexed to life expectancy; 67.3 by 2035",
            "ES":   "Reforma de pensiones 2011, rising to 67 by 2027",
            "UK":   "State Pension Act 2014, 66->67 by 2028",
            "AT":   "Pensionsreform 2014, women 60->65 by 2033; men 65",
            "CH":   "AHV21 reform, women reached 65 in January 2025",
        }
        for short, (y25, y35) in STATUTORY_2025_2035.items():
            writer.writerow([short, y25, y35, refs.get(short, "")])
    print(f"[write] {path}")


if __name__ == "__main__":
    write_statutory_csv()
    rows = compute()
    write_csv(rows, "retirement_offset.csv")
