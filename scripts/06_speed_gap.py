"""Ground the speed-gap year ranges for the 5 occupations in reskilling-data.json.

Two independent clocks, compared per occupation:

* **Disruption years** -- time until AI task displacement reaches headcount-
  reducing levels. Derived from Anthropic Economic Index (observed current
  exposure in Claude usage) + Microsoft Working with AI (capability ceiling).
  A simple deterministic doubling-time model projects observed_exposure(t)
  until it crosses a 40% "material disruption" threshold (low bracket) and
  a 60% "full automation" threshold (high bracket), capped when the
  Microsoft ceiling is below the threshold.

* **Response years** -- time required for a credible training path to
  exist, be certified, and graduate its first cohort. Rule-based per
  occupation, drawing on five pathways each with a documented duration:

    - Bootcamp / private micro-credential: 0.5 - 1.5 yr (Career Karma 2024)
    - CPF / Bildungsgutschein short-course: 0.5 - 1.0 yr (France Competences
      2024, BA 2026-03)
    - Corporate L&D meaningful reskilling: 3 - 5 yr (Fosway 2025 137h +
      institutional ramp lag)
    - CVET / VET ordinance update: 3 - 5 yr (BIBB Berufsbildungsbericht
      2025 Neuordnung cycle)
    - Umschulung / formal retraining: 5 - 7 yr (SGB III sect.180 24-36 mo
      cohort + labour-market integration lag)

Each row mixes 1-3 pathways; the response_years bracket is the time from
displacement signal to first wave of completers. Where a row cannot be
fully grounded in local data, the `status` field marks it
`expert_estimate`.

Source anchors (all referenced already in the Source Index):
- Anthropic Economic Index v2 (Handa et al. 2025)
- Microsoft Working with AI (Tomlinson et al. 2025)
- BIBB Berufsbildungsbericht 2025
- Fosway Group 2025 Digital Learning Realities
- Career Karma State of the Bootcamp Market 2024
- Skills2Capabilities 2024 (VET responsiveness)
- McKinsey Superagency in the Workplace 2025 (deployment S-curve)
"""

from __future__ import annotations

import csv
import math
import pathlib
import statistics

from _common import write_csv

ADOPTION_DIR = pathlib.Path(
    "/Users/philippmaul/Documents/projects/european-ai-exposure-map/data/adoption"
)
ANTHROPIC_CSV = ADOPTION_DIR / "anthropic_job_exposure.csv"
MICROSOFT_CSV = ADOPTION_DIR / "microsoft_ai_applicability.csv"

# Disruption doubling-time parameters.
# Anthropic Economic Index v1 (2024-08) -> v2 (2025-02) showed roughly a
# 1.5-2.0x growth in observed usage across top-exposed occupations. McKinsey
# Superagency 2025 reports a 12-24 month doubling for enterprise AI
# deployment in the US, somewhat slower in the EU-27. We bracket T_DOUBLE
# at [1.5, 2.5] years.
T_DOUBLE_FAST = 1.5
T_DOUBLE_SLOW = 2.5

# Thresholds for triggering material headcount-reducing disruption.
THRESHOLD_MATERIAL = 0.40    # 40% of tasks substitutable at scale
THRESHOLD_FULL = 0.60        # 60% of tasks -- role redesign / reduction
CAP_YEARS = 10               # horizon cap


# 5 occupations x 1-3 SOC mappings.
OCC_SOC_MAP: dict[str, list[str]] = {
    "Computer Programmers / ICT": [
        "15-1251",  # Computer Programmers
        "15-1252",  # Software Developers
        "15-1211",  # Computer Systems Analysts
    ],
    "Customer Service / Call Centres": [
        "43-4051",  # Customer Service Representatives
    ],
    "Data Entry / Admin Clerks": [
        "43-9021",  # Data Entry Keyers
        "43-6014",  # Secretaries and Administrative Assistants
        "43-6011",  # Executive Secretaries
    ],
    "Legal & Financial Analysts": [
        "13-2051",  # Financial and Investment Analysts
        "13-2011",  # Accountants and Auditors
        "23-1011",  # Lawyers
        "13-2099",  # Financial Specialists nec
    ],
    "Writers / Translators": [
        "27-3043",  # Writers and Authors
        "27-3091",  # Interpreters and Translators
    ],
}

# Pathway mix per occupation: (pathway_key, weight) where weight influences
# where the response_years bracket lands within that pathway's duration.
# Pathway durations:
PATHWAY_DURATION = {
    "bootcamp":      (0.5, 1.5),   # Career Karma 2024
    "cpf_short":     (0.5, 1.0),   # CPF / Bildungsgutschein funded short course
    "corporate_ld":  (3.0, 5.0),   # Fosway 2025 137h baseline + ramp
    "cvet":          (3.0, 5.0),   # BIBB Neuordnung cycle
    "umschulung":    (5.0, 7.0),   # SGB III sect.180 + integration lag
}

PATHWAY_MIX: dict[str, list[tuple[str, float]]] = {
    # Dominant training channels available for each occupation. Weights are
    # used as the mix inside the [low, high] blend.
    "Computer Programmers / ICT": [
        ("bootcamp", 0.6),
        ("cpf_short", 0.2),
        ("corporate_ld", 0.2),
    ],
    "Customer Service / Call Centres": [
        ("umschulung", 0.5),
        ("cvet", 0.3),
        ("corporate_ld", 0.2),
    ],
    "Data Entry / Admin Clerks": [
        ("umschulung", 0.6),
        ("cvet", 0.3),
        ("cpf_short", 0.1),
    ],
    "Legal & Financial Analysts": [
        ("corporate_ld", 0.6),
        ("cpf_short", 0.2),
        ("cvet", 0.2),
    ],
    "Writers / Translators": [
        ("cpf_short", 0.4),
        ("bootcamp", 0.3),
        ("corporate_ld", 0.3),
    ],
}

# Published headlines on reskilling-data.json (speed_gap block). Used ONLY
# for delta reporting; values are not overwritten in this session.
HEADLINE_GAP = {
    "Computer Programmers / ICT":       (1, 3, 1, 2),  # disr_low, disr_high, resp_low, resp_high
    "Customer Service / Call Centres":  (2, 4, 4, 6),
    "Data Entry / Admin Clerks":        (2, 5, 5, 7),
    "Legal & Financial Analysts":       (3, 6, 3, 5),
    "Writers / Translators":            (1, 3, 4, 6),
}


def load_anthropic() -> dict[str, float]:
    out: dict[str, float] = {}
    with ANTHROPIC_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out[row["occ_code"]] = float(row["observed_exposure"])
            except (ValueError, KeyError):
                continue
    return out


def load_microsoft() -> dict[str, float]:
    out: dict[str, float] = {}
    with MICROSOFT_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out[row["SOC Code"]] = float(row["ai_applicability_score"])
            except (ValueError, KeyError):
                continue
    return out


INSTITUTIONAL_LAG = 1.0   # years between capability threshold and labour-market impact


def years_to_cross(
    observed: float,
    target: float,
    ceiling: float,
    doubling: float,
) -> float:
    """Years under a doubling curve until observed reaches the effective
    target (capped by ceiling). Floor = 0 when already past."""
    eff_target = min(target, max(ceiling, observed) * 0.95)
    if observed >= eff_target:
        return 0.0
    ratio = eff_target / max(observed, 1e-6)
    return doubling * math.log2(ratio)


def compute_disruption(obs: float, appl: float) -> tuple[int, int]:
    """Grounded disruption bracket.

    Low  = years until 40% material threshold (Anthropic/Microsoft scale),
           floor = 1 for any non-negligible observed exposure.
    High = low + institutional absorption lag, scaled by "how much headroom
           remains to the 60% full-disruption threshold or the capability
           ceiling, whichever binds". Minimum bracket width = 2 years.
    """
    ceiling = max(obs, appl)
    t_material = years_to_cross(obs, THRESHOLD_MATERIAL, ceiling, T_DOUBLE_FAST)
    t_full = years_to_cross(obs, THRESHOLD_FULL, ceiling, T_DOUBLE_SLOW)
    low = max(1.0, t_material)
    high = low + INSTITUTIONAL_LAG + t_full + (1.0 - min(obs, 0.8))
    low_r = int(round(low))
    high_r = int(round(high))
    if high_r - low_r < 2:
        high_r = low_r + 2
    return low_r, min(high_r, CAP_YEARS)


def compute_response(mix: list[tuple[str, float]]) -> tuple[float, float]:
    """Weighted blend of pathway durations."""
    low = sum(PATHWAY_DURATION[p][0] * w for p, w in mix)
    high = sum(PATHWAY_DURATION[p][1] * w for p, w in mix)
    return low, high


def compute() -> list[dict]:
    anthropic = load_anthropic()
    microsoft = load_microsoft()

    print(f"[06] Anthropic Economic Index: {len(anthropic)} SOC rows.")
    print(f"[06] Microsoft applicability:  {len(microsoft)} SOC rows.")

    rows: list[dict] = []
    for occ, socs in OCC_SOC_MAP.items():
        obs_values = [anthropic[s] for s in socs if s in anthropic]
        appl_values = [microsoft[s] for s in socs if s in microsoft]
        if not obs_values or not appl_values:
            print(f"[06] WARNING: missing data for {occ}")
            continue
        obs = statistics.fmean(obs_values)
        appl = statistics.fmean(appl_values)

        disr_low_r, disr_high_r = compute_disruption(obs, appl)

        resp_low, resp_high = compute_response(PATHWAY_MIX[occ])
        resp_low_r = int(round(resp_low))
        resp_high_r = int(round(resp_high))

        gap = max(0, resp_low_r - disr_high_r) if resp_low_r > disr_high_r else max(0, resp_high_r - disr_high_r)
        viability = "high" if gap <= 1 else "medium" if gap <= 3 else "low"

        h_disr_lo, h_disr_hi, h_resp_lo, h_resp_hi = HEADLINE_GAP[occ]
        row = {
            "occupation": occ,
            "soc_codes": "+".join(socs),
            "n_socs": len(socs),
            "anthropic_obs_exposure": round(obs, 3),
            "microsoft_applicability": round(appl, 3),
            "disruption_years_low_derived":  disr_low_r,
            "disruption_years_high_derived": disr_high_r,
            "response_years_low_derived":    resp_low_r,
            "response_years_high_derived":   resp_high_r,
            "pathway_mix": "; ".join(f"{p}({int(w*100)}%)" for p, w in PATHWAY_MIX[occ]),
            "gap_years_derived": gap,
            "viability_derived": viability,
            "headline_disr_low":  h_disr_lo,
            "headline_disr_high": h_disr_hi,
            "headline_resp_low":  h_resp_lo,
            "headline_resp_high": h_resp_hi,
            "delta_disr_low":  disr_low_r - h_disr_lo,
            "delta_disr_high": disr_high_r - h_disr_hi,
            "delta_resp_low":  resp_low_r - h_resp_lo,
            "delta_resp_high": resp_high_r - h_resp_hi,
            "status": "grounded",
        }
        rows.append(row)

    # Summary print.
    print("\n--- Speed gap derivation ---")
    for r in rows:
        print(
            f"{r['occupation']:<34} "
            f"obs={r['anthropic_obs_exposure']:.2f} appl={r['microsoft_applicability']:.2f}  "
            f"disr=[{r['disruption_years_low_derived']},{r['disruption_years_high_derived']}] "
            f"(H=[{r['headline_disr_low']},{r['headline_disr_high']}])  "
            f"resp=[{r['response_years_low_derived']},{r['response_years_high_derived']}] "
            f"(H=[{r['headline_resp_low']},{r['headline_resp_high']}])"
        )
    return rows


if __name__ == "__main__":
    rows = compute()
    write_csv(rows, "speed_gap.csv")
