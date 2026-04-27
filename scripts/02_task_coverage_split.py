"""Ground the 7.55M / 15M / 7.5M deep-reskilling / upskilling / partial split.

The Layer 5 headline applies a 25 / 50 / 25 partition to the 30.05M net
reskilling need. This script tests that partition against two independent
task-coverage indexes:

1. Anthropic Economic Index (Handa et al. 2025): cumulative distribution of
   O*NET occupations by the fraction of tasks where Claude usage crosses the
   non-trivial threshold. Reported in Figure 4 of the AEI paper:
     - 4%  of occupations have AI usage on >=75% of tasks
     - 11% of occupations have AI usage on >=50% of tasks
     - 36% of occupations have AI usage on >=25% of tasks

2. Microsoft Working with AI (Tomlinson et al. 2025): employment-weighted
   AI applicability score for each of 97 SOC minor groups, Table 1. We
   count minor groups in each applicability decile and compute the
   employment share in each tier using US Census OEWS 2023 employment.

We compute three candidate splits and report the disagreement with the
headline 25/50/25.
"""

from __future__ import annotations

from _common import write_csv


NET_NEED = 30_050_000

# --- Method 1: Anthropic Economic Index cumulative distribution ---
# Figure 4 points in the Handa et al. (2025) paper.
AEI_POINTS = [
    (0.25, 0.36),   # 36% of occupations have AI usage on >=25% of tasks
    (0.50, 0.11),
    (0.75, 0.04),
]


def aei_split() -> dict[str, float]:
    # Within the reskilling pool (assumed = 36% of occupations threshold):
    top = 0.04 / 0.36          # >=75% task coverage
    mid = (0.11 - 0.04) / 0.36 # 50-75%
    bot = 1 - top - mid        # 25-50%
    return {
        "deep_reskilling_pct": top,
        "upskilling_pct": mid,
        "partial_pct": bot,
    }


# --- Method 2: Microsoft Working with AI applicability scores (Table 1) ---
# Top-25 minor groups by employment-weighted applicability score.
# Scores range 0.03 (low) to 0.38 (high). US OEWS 2023 employment weighting
# is encoded in the "emp" field (millions); asterisks in Table 1 denote:
# none=<0.5M, *=0.5-2M, **=2M+, ***>2M (we use 0.25M / 1M / 2.5M / 4M as
# midpoints). Minor groups in grey in the original table have <50% info-work
# composition and are excluded from the high-exposure pool.
MS_TABLE_1: list[tuple[str, float, float]] = [
    ("Media and Communication Workers", 0.38, 0.25),
    ("Sales Representatives, Services", 0.35, 2.5),
    ("Information and Record Clerks", 0.33, 2.5),
    ("Mathematical Science Occupations", 0.32, 0.25),
    ("Tour and Travel Guides", 0.32, 0.25),
    ("Postsecondary Teachers", 0.31, 1.0),
    ("Sales Reps Wholesale and Manufacturing", 0.31, 1.0),
    ("Communications Equipment Operators", 0.30, 0.25),
    ("Baggage Porters Bellhops and Concierges", 0.30, 0.25),
    ("Retail Sales Workers", 0.30, 2.5),
    ("Other Sales and Related Workers", 0.30, 0.25),
    ("Computer Occupations", 0.29, 4.0),
    ("Personal Care and Service Sups", 0.27, 0.25),
    ("Entertainment Attendants and Related", 0.27, 0.25),
    ("Religious Workers", 0.26, 0.25),
    ("Social Scientists and Related", 0.26, 0.25),
    ("Librarians Curators and Archivists", 0.25, 0.25),
    ("Counselors Social Workers and Related", 0.25, 1.0),
    ("Supervisors of Production Workers", 0.25, 1.0),
    ("Other Office and Admin Support Workers", 0.25, 2.5),
    ("Financial Clerks", 0.24, 2.5),
    ("Secretaries and Administrative Assistants", 0.24, 2.5),
    ("Business Operations Specialists", 0.24, 2.5),
    ("Animal Care and Service Workers", 0.24, 0.25),
    ("Financial Specialists", 0.23, 2.5),
    ("Other Teachers and Instructors", 0.23, 1.0),
    ("Engineers", 0.22, 2.5),
    ("Physical Scientists", 0.21, 0.25),
    ("Drafters and Eng Mapping Techns", 0.21, 0.25),
    ("Life Scientists", 0.20, 0.25),
    ("Art and Design Workers", 0.20, 0.25),
    ("Food and Beverage Serving Workers", 0.20, 2.5),
    ("Other Educational and Library Workers", 0.19, 1.0),
    ("Primary Secondary and Special Ed Teachers", 0.19, 2.5),
    ("Media and Comms Equipment Workers", 0.19, 0.25),
    ("Construction and Extraction Supervisors", 0.19, 0.25),
    ("Lawyers Judges and Related Workers", 0.18, 1.0),
    ("Other Healthcare Pracs and Tech Occs", 0.18, 0.25),
    ("Electrical and Electronic Equipment Mechs", 0.18, 0.25),
    ("Top Executives", 0.17, 2.5),
    ("Assemblers and Fabricators", 0.17, 1.0),
    ("Transportation and Material Moving Sups", 0.17, 0.25),
    ("Other Production Occupations", 0.17, 1.0),
    ("Health Technologists and Technicians", 0.16, 1.0),
    ("Vehicle and Mobile Equipment Mechs", 0.16, 0.25),
    ("Other Healthcare Support Occupations", 0.16, 1.0),
    ("Metal Workers and Plastic Workers", 0.15, 1.0),
]


def microsoft_split() -> dict[str, float]:
    # Employment-weighted top quartile: the score cut that captures ~25%
    # of employment in info-work-eligible groups.
    total_emp = sum(e for _, _, e in MS_TABLE_1)
    sorted_rows = sorted(MS_TABLE_1, key=lambda r: -r[1])

    # Accumulate from top until 25%, then 50%, then 75%.
    accum = 0.0
    top_count = 0.0
    mid_count = 0.0
    bot_count = 0.0
    for _, _, emp in sorted_rows:
        next_accum = accum + emp
        if accum < total_emp * 0.25 and next_accum <= total_emp * 0.25:
            top_count += emp
        elif accum < total_emp * 0.75:
            mid_count += emp
        else:
            bot_count += emp
        accum = next_accum

    top = top_count / total_emp
    mid = mid_count / total_emp
    bot = 1 - top - mid
    return {
        "deep_reskilling_pct": top,
        "upskilling_pct": mid,
        "partial_pct": bot,
    }


def triangulated_split(w_aei: float = 0.50, w_ms: float = 0.50) -> dict[str, float]:
    a = aei_split()
    m = microsoft_split()
    return {
        "deep_reskilling_pct": a["deep_reskilling_pct"] * w_aei
                             + m["deep_reskilling_pct"] * w_ms,
        "upskilling_pct":     a["upskilling_pct"] * w_aei
                             + m["upskilling_pct"] * w_ms,
        "partial_pct":        a["partial_pct"] * w_aei
                             + m["partial_pct"] * w_ms,
    }


def compute() -> list[dict]:
    a = aei_split()
    m = microsoft_split()
    t = triangulated_split()

    headline = {
        "deep_reskilling_pct": 7_550_000 / NET_NEED,
        "upskilling_pct":     15_000_000 / NET_NEED,
        "partial_pct":         7_500_000 / NET_NEED,
    }

    rows: list[dict] = []
    for name, split in [
        ("Layer 5 headline (25/50/25)", headline),
        ("Anthropic Economic Index only", a),
        ("Microsoft applicability only", m),
        ("Triangulated (50/50)", t),
    ]:
        rows.append({
            "method": name,
            "deep_reskilling_pct": round(split["deep_reskilling_pct"] * 100, 1),
            "upskilling_pct":     round(split["upskilling_pct"]     * 100, 1),
            "partial_pct":        round(split["partial_pct"]        * 100, 1),
            "deep_reskilling_abs": int(split["deep_reskilling_pct"] * NET_NEED),
            "upskilling_abs":     int(split["upskilling_pct"]     * NET_NEED),
            "partial_abs":        int(split["partial_pct"]        * NET_NEED),
        })

    print("\n--- Task coverage split derivation ---")
    print(f"Net reskilling need (2035): {NET_NEED:,}")
    print()
    print(f"{'method':<32} {'deep':>10} {'upskill':>10} {'partial':>10}")
    for row in rows:
        print(
            f"{row['method']:<32} "
            f"{row['deep_reskilling_abs']:>10,} "
            f"{row['upskilling_abs']:>10,} "
            f"{row['partial_abs']:>10,}"
        )
    print()
    print("Delta vs headline (triangulated - headline):")
    delta_deep = rows[3]['deep_reskilling_abs'] - rows[0]['deep_reskilling_abs']
    delta_up   = rows[3]['upskilling_abs']     - rows[0]['upskilling_abs']
    delta_part = rows[3]['partial_abs']         - rows[0]['partial_abs']
    print(f"  deep={delta_deep:+,}  upskill={delta_up:+,}  partial={delta_part:+,}")

    return rows


if __name__ == "__main__":
    rows = compute()
    write_csv(rows, "task_coverage_split.csv")
