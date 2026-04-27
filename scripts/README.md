# Layer 5 — Derivation scripts

Reproducible computations that ground the eight inferred numbers on the reskilling site:

1. `01_retirement_offset.py` — 8.67M retirement offset by 2035
2. `02_task_coverage_split.py` — 7.55M / 15M / 7.5M deep reskilling / upskilling / partial split
3. `03_channel_throughput.py` — 3.34M annual channel throughput (university, VET, corporate L&D, ALMP, bootcamps)
4. `04_net_new_capacity.py` — 450K net new throughput after baseline churn
5. `05_skills_distance.py` — skills distance 0–10 for the 16 transition pairs (ESCO cosine, L2-bucketed)
6. `06_speed_gap.py` — disruption / response year brackets for the 5 speed-gap occupations
7. `07_system_radar.py` — 1–10 scores on Speed / Scale / Quality / Equity / Funding for 6 system models
8. `08_a_to_c_rates.py` — cross-zone A→C transition rates for 6 system models

Each script is self-documenting: it fetches the underlying Eurostat / OECD / Anthropic / Microsoft / ESCO / Bertheau data, prints the computation steps, and writes a CSV to `output/`.

## Data sources

| Script | Primary source | Endpoint / local path |
| --- | --- | --- |
| 01 | Eurostat lfsa_egai2d | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsa_egai2d |
| 01 | Eurostat lfsi_emp_a | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_a |
| 01 | National statutory retirement schedules (compiled, see `data/statutory_retirement_2025_2035.csv`) | — |
| 02 | Anthropic Economic Index v2 | https://huggingface.co/datasets/Anthropic/EconomicIndex |
| 02 | Microsoft Working with AI SOC applicability (Table 1) | https://arxiv.org/abs/2507.07935 |
| 03 | Eurostat educ_uoe_enra02 | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/educ_uoe_enra02 |
| 03 | Cedefop Key Indicators on VET | https://www.cedefop.europa.eu/en/tools/key-indicators-on-vet |
| 03 | Eurostat trng_cvt_12s (CVTS 2020) | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/trng_cvt_12s |
| 03 | Technavio Europe Corporate Training 2025-2029 | https://www.technavio.com/report/europe-corporate-training-market-industry-analysis |
| 03 | Career Karma State of the Bootcamp Market 2024 | https://careerkarma.com/blog/state-of-the-bootcamp-market-report-2024/ |
| 04 | Eurostat lfsa_etpgan (tenure < 1 year, job-to-job proxy) | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsa_etpgan |
| 05 | ESCO v1.1 occupationSkillRelations + skillsHierarchy + broaderRelationsSkillPillar + occupations | `/Users/philippmaul/Documents/projects/european-ai-exposure-map/data/esco/` |
| 06 | Anthropic Economic Index (observed exposure) | `/Users/philippmaul/Documents/projects/european-ai-exposure-map/data/adoption/anthropic_job_exposure.csv` |
| 06 | Microsoft Working with AI applicability | `/Users/philippmaul/Documents/projects/european-ai-exposure-map/data/adoption/microsoft_ai_applicability.csv` |
| 06 | BIBB Berufsbildungsbericht 2025 (Neuordnung cycle, referenced) | — |
| 06 | Fosway 2025 + Career Karma 2024 + SGB III §180 (pathway durations) | — |
| 07 | Eurostat trng_aes_100 (AES 2022) | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/trng_aes_100 |
| 07 | Eurostat trng_aes_102 (by ISCED) | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/trng_aes_102 |
| 07 | Eurostat trng_cvt_01s (CVTS 2020 enterprise share) | https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/trng_cvt_01s |
| 07 | OECD SOCX 2022 ALMP training-category (Eurostat open LMP withdrawn) | — |
| 08 | Bertheau et al. 2022 (IZA DP 15033) | `data/bertheau/iza_dp15033.pdf` (fetched 2026-04-21 from docs.iza.org) |
| 08 | National stats agencies (IAB, ONS, CSO, CBS, Statbel, GUS, CZSO, KSH, INS, ELSTAT) for non-Bertheau countries | — |

## How to run

```bash
pip install -r requirements.txt
python3 01_retirement_offset.py
python3 02_task_coverage_split.py
python3 03_channel_throughput.py
python3 04_net_new_capacity.py
python3 05_skills_distance.py
python3 06_speed_gap.py
python3 07_system_radar.py
python3 08_a_to_c_rates.py
```

Each script writes a CSV to `output/` and prints a per-country or per-source summary to stdout. If the Eurostat API is unavailable, the script falls back to the cached pull in `data/` so the computation is still reproducible offline.

## Country coverage

Seven headline countries (DE, FR, IT, ES, UK, AT, CH) plus EU-27 aggregate. Extending to the full 36-country scope used in Layers 1 and 4 requires only broadening the `COUNTRIES` list at the top of each script.

## Licence

CC-BY 4.0. Attribution: Philipp Maul / Nexalps.
