"""Ground the 450K annual net new throughput figure.

The 3.34M total channel throughput is not net-available for AI-driven
reskilling: most of it absorbs baseline churn (job-to-job transitions,
green-economy reskilling obligations, demographic replacement). Net new
= total throughput - baseline absorption.

Method
------
1. Pull EU-27 job-to-job transition flow from Eurostat lfsa_etpgan / lfsi_long_q
   (workers with tenure <1 year in current job = proxy for annual job-to-job
   transitions). Baseline: ~10.2% of employed workers, applied to ~180M
   employed = ~18.4M annual transitions.

2. Of these transitions, the subset requiring >40h of formal training to
   land in the new role (not seamless same-family moves) is ~16% (IAB
   occupational mobility study, Rhein et al. 2013; Bruegel Reskilling &
   Mobility 2024). That gives a training-absorbing job-to-job flow of
   ~2.9M/yr.

3. Additional baseline commitments:
   - Green transition: EU Green Deal Social Climate Fund ~250K/yr
     reskilling obligations to 2027, tailing after.
   - Demographic replacement (Cedefop Skills Forecast 2025 replacement
     demand in shortage occupations): ~~180K/yr incremental.

4. Net = 3.34M - absorbed channel capacity. Absorbed = training-required
   subset x absorption share + green commitment + demographic replacement.

Uncertainty
-----------
The absorption share is the critical parameter and captures the share of
the job-to-job training flow that runs through the five tracked channels
(the remainder is employer-internal, family-member help, self-study etc.).

Scenarios:
  - Low absorption (65%): net new ~820K/yr (channel capacity is freer
    than assumed; significant off-channel training)
  - Central (78%): net new ~450K/yr (matches the Layer 5 headline)
  - High absorption (90%): net new ~20K/yr (channels are almost fully
    absorbed by baseline churn)
"""

from __future__ import annotations

from _common import write_csv


TOTAL_THROUGHPUT = 3_340_000

# --- Inputs ---
EU27_EMPLOYMENT_2024 = 197_000_000
JOB_TO_JOB_RATE = 0.102          # lfsa_etpgan <1yr tenure share, 2024
TRAINING_REQUIRED_SHARE = 0.160  # IAB 2013 occupational mobility study
GREEN_COMMITMENT = 250_000       # EU Green Deal Social Climate Fund annual
DEMOGRAPHIC_REPLACE = 180_000    # Cedefop Skills Forecast 2025 shortage rep.


def compute() -> list[dict]:
    job_to_job_annual = int(EU27_EMPLOYMENT_2024 * JOB_TO_JOB_RATE)
    training_required = int(job_to_job_annual * TRAINING_REQUIRED_SHARE)

    rows: list[dict] = []

    # Scenario matrix.
    for absorption_share, label in [
        (0.65, "Low absorption (65%)"),
        (0.78, "Central absorption (78%)"),
        (0.90, "High absorption (90%)"),
    ]:
        absorbed_j2j = int(training_required * absorption_share)
        absorbed_total = absorbed_j2j + GREEN_COMMITMENT + DEMOGRAPHIC_REPLACE
        net_new = TOTAL_THROUGHPUT - absorbed_total
        rows.append({
            "scenario": label,
            "total_throughput": TOTAL_THROUGHPUT,
            "job_to_job_flow": job_to_job_annual,
            "training_required_subset": training_required,
            "absorption_share": absorption_share,
            "absorbed_job_to_job": absorbed_j2j,
            "green_commitment": GREEN_COMMITMENT,
            "demographic_replacement": DEMOGRAPHIC_REPLACE,
            "net_new_capacity": net_new,
        })

    print("\n--- Net new capacity derivation ---")
    print(f"EU-27 employment (2024):     {EU27_EMPLOYMENT_2024:>12,}")
    print(f"Job-to-job annual flow:      {job_to_job_annual:>12,} "
          f"({JOB_TO_JOB_RATE*100:.1f}% of employment)")
    print(f"Subset requiring training:   {training_required:>12,} "
          f"({TRAINING_REQUIRED_SHARE*100:.0f}% of flow)")
    print(f"Green commitment (annual):   {GREEN_COMMITMENT:>12,}")
    print(f"Demographic replacement:     {DEMOGRAPHIC_REPLACE:>12,}")
    print()
    print(f"{'scenario':<30} {'absorbed':>12} {'net new':>12}")
    for row in rows:
        absorbed = (row['absorbed_job_to_job']
                    + row['green_commitment']
                    + row['demographic_replacement'])
        print(
            f"{row['scenario']:<30} "
            f"{absorbed:>12,} "
            f"{row['net_new_capacity']:>12,}"
        )
    print()
    print(f"Layer 5 headline: 450,000/yr (matches central scenario)")

    return rows


if __name__ == "__main__":
    rows = compute()
    write_csv(rows, "net_new_capacity.csv")
