"""Ground the 6 system-model radar scores on 5 dimensions.

Dimensions, one observable indicator each:

* **Speed**   <- absolute non-formal training participation rate, adults
                25-64 (Eurostat trng_aes_100 NFE). Countries where adults
                participate heavily in non-formal learning have systems
                that can rapidly mobilise short, modular training
                (CPF / Bildungsgutschein / individual learning accounts).
                This is an imperfect proxy for the Skills2Capabilities
                2024 "VET responsiveness index" which is not locally
                accessible; flagged in the derivation appendix.
* **Scale**   <- total adult-learning participation rate 25-64 (Eurostat
                trng_aes_100 FE_NFE). Breadth of access.
* **Quality** <- share of enterprises providing continuing vocational
                training (Eurostat trng_cvt_01s TRNG). CVTS 2020 round.
                Quality proxy: high firm participation implies systematic
                training provision, not ad-hoc.
* **Equity**  <- ratio of low-education (ISCED 0-2) AES participation to
                high-education (ISCED 5-8) participation. Higher ratio =
                more equal access across education levels.
* **Funding** <- ALMP training spend % of GDP. Eurostat's open LMP table
                has been withdrawn from open dissemination; we fall back
                to the OECD SOCX / national ALMP tracker values already
                anchored in reskilling-data.json (systems[].almp_spend_gdp_pct).

Scoring
-------
For each dimension we compute each country's percentile rank within the
full set of available countries, then average ranks within each of the 6
system models. The resulting 0-1 percentile is mapped to a 1-10 score:

    score = 1 + 9 * avg_percentile

A perfect-top system (avg percentile 1.0) scores 10, a worst-ranked
system (avg percentile 0.0) scores 1. The ranking is relative, not
absolute -- consistent with the brief's "country-averaged percentile
rankings" instruction.
"""

from __future__ import annotations

import csv
import json
import pathlib
import statistics
import urllib.request
import urllib.error
import urllib.parse

from _common import DATA, EUROSTAT_BASE, write_csv

# System models and countries.
SYSTEMS: list[tuple[str, list[str]]] = [
    ("Nordic Flexicurity",        ["DK", "SE", "FI", "NO"]),
    ("Germanic Dual System",      ["DE", "AT", "CH"]),
    ("Continental Corporatist",   ["FR", "NL", "BE"]),
    ("Liberal Market",            ["UK", "IE"]),
    ("Central/Eastern European",  ["PL", "CZ", "HU", "RO"]),
    ("Southern European",         ["IT", "ES", "PT", "EL"]),  # EL = Greece
]

ALL_COUNTRIES = sorted({c for _, cs in SYSTEMS for c in cs})

# Eurostat has no UK data post-Brexit for most LFS-derived series. We fall
# back to OECD 2022 (closest adjacent source) for UK where needed.
UK_FALLBACK = {
    "aes_fe_nfe": 51.0,   # OECD Education at a Glance 2023, adults 25-64 participating in any formal or non-formal training
    "aes_fe":     13.0,   # share in formal tertiary adult learning
    "aes_nfe":    44.0,   # non-formal job-related learning
    "aes_low":    32.0,   # ISCED 0-2 participation
    "aes_high":   66.0,   # ISCED 5-8 participation
    "cvt_trng":   69.0,   # ONS 2021 equivalent (closest Employer Skills Survey figure)
}

# Cedefop / OECD-derived ALMP training spend % GDP (already in
# reskilling-data.json per-system). Country-level:
ALMP_TRAINING_GDP_PCT = {
    # Source: OECD SOCX 2022, plus Eurostat published LMP legacy tables.
    # For training (LMP category 2) only -- total ALMP is higher.
    "DK": 0.45, "SE": 0.20, "FI": 0.48, "NO": 0.35,
    "DE": 0.22, "AT": 0.51, "CH": 0.15,
    "FR": 0.31, "NL": 0.22, "BE": 0.21,
    "UK": 0.01, "IE": 0.15,
    "PL": 0.09, "CZ": 0.06, "HU": 0.14, "RO": 0.03,
    "IT": 0.20, "ES": 0.14, "PT": 0.28, "EL": 0.09,
}


def fetch_eurostat(table: str, params: dict, cache: str) -> dict | None:
    """Simplified fetch - returns None if live fetch fails and no cache."""
    cache_path = DATA / cache
    q = [("format", "JSON"), ("lang", "EN")]
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            for x in v:
                q.append((k, str(x)))
        else:
            q.append((k, str(v)))
    url = EUROSTAT_BASE + table + "?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.load(resp)
        cache_path.write_text(json.dumps(payload))
        print(f"[07] {table}: live ({len(json.dumps(payload)):,}B) -> {cache_path.name}")
        return payload
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        if cache_path.exists():
            print(f"[07] {table}: live failed ({exc}); using cache.")
            return json.loads(cache_path.read_text())
        print(f"[07] {table}: live failed and no cache.")
        return None


def jsonstat_geo_values(payload: dict, fixed_coords: dict[str, str]) -> dict[str, float]:
    """Iterate a JSON-stat payload over the `geo` dimension, returning
    {geo_code: value} with all other dims pinned by fixed_coords.
    """
    if not payload or "dimension" not in payload:
        return {}
    dims = payload["id"]
    sizes = [payload["size"][i] for i in range(len(dims))]
    strides: list[int] = []
    stride = 1
    for size in reversed(sizes):
        strides.insert(0, stride)
        stride *= size

    geo_cat = payload["dimension"]["geo"]["category"]["index"]
    raw = payload.get("value", {})
    out: dict[str, float] = {}
    for geo, geo_idx in geo_cat.items():
        idx = 0
        ok = True
        for i, dim in enumerate(dims):
            if dim == "geo":
                idx += geo_idx * strides[i]
            else:
                cat = payload["dimension"][dim]["category"]["index"]
                want = fixed_coords.get(dim)
                if want is None:
                    # Unspecified dim with size >1: skip.
                    if sizes[i] != 1:
                        ok = False
                        break
                    # Size 1 -> take the only index.
                    idx += 0
                else:
                    if want not in cat:
                        ok = False
                        break
                    idx += cat[want] * strides[i]
        if not ok:
            continue
        v = raw.get(str(idx)) if isinstance(raw, dict) else (
            raw[idx] if idx < len(raw) else None
        )
        if v is not None:
            out[geo] = float(v)
    return out


def pull_aes_base() -> tuple[dict, dict, dict]:
    """Pull AES 2022 participation rates: FE_NFE, FE, NFE."""
    payload = fetch_eurostat(
        "trng_aes_100",
        {"time": 2022, "age": "Y25-64", "sex": "T", "unit": "PC"},
        "aes_100_2022.json",
    )
    if not payload:
        return {}, {}, {}
    fe_nfe = jsonstat_geo_values(payload, {"training": "FE_NFE",
                                           "freq": "A",
                                           "age": "Y25-64",
                                           "sex": "T",
                                           "unit": "PC",
                                           "time": "2022"})
    fe = jsonstat_geo_values(payload, {"training": "FE",
                                       "freq": "A",
                                       "age": "Y25-64",
                                       "sex": "T",
                                       "unit": "PC",
                                       "time": "2022"})
    nfe = jsonstat_geo_values(payload, {"training": "NFE",
                                        "freq": "A",
                                        "age": "Y25-64",
                                        "sex": "T",
                                        "unit": "PC",
                                        "time": "2022"})
    return fe_nfe, fe, nfe


def pull_aes_by_isced(isced_code: str, cache: str) -> dict:
    payload = fetch_eurostat(
        "trng_aes_102",
        {"time": 2022, "age": "Y25-64", "unit": "PC",
         "training": "FE_NFE", "isced11": isced_code},
        cache,
    )
    if not payload:
        return {}
    return jsonstat_geo_values(
        payload,
        {"training": "FE_NFE", "freq": "A",
         "age": "Y25-64", "unit": "PC",
         "isced11": isced_code, "time": "2022"},
    )


def pull_cvt_trng() -> dict:
    """CVTS 2020: % of enterprises providing continuing vocational training
    (courses or other forms, all size classes).
    """
    payload = fetch_eurostat(
        "trng_cvt_01s",
        {"time": 2020, "training": "CO_OF", "size_emp": "TOTAL", "unit": "PC"},
        "cvt_01s_2020.json",
    )
    if not payload:
        return {}
    return jsonstat_geo_values(
        payload,
        {"training": "CO_OF", "size_emp": "TOTAL",
         "unit": "PC", "time": "2020", "freq": "A"},
    )


def percentile_rank(value: float, series: list[float]) -> float:
    """Return percentile (0-1) of value in series. Ties averaged."""
    clean = [v for v in series if v is not None]
    if not clean:
        return 0.5
    below = sum(1 for v in clean if v < value)
    equal = sum(1 for v in clean if v == value)
    return (below + 0.5 * equal) / len(clean)


def score_from_percentile(pct: float) -> float:
    return round(1.0 + 9.0 * pct, 1)


def compute() -> list[dict]:
    # --- pull ---
    fe_nfe, fe, nfe = pull_aes_base()
    aes_low = pull_aes_by_isced("ED0-2", "aes_102_low.json")
    aes_high = pull_aes_by_isced("ED5-8", "aes_102_high.json")
    cvt = pull_cvt_trng()

    # Apply UK fallback.
    if "UK" not in fe_nfe:
        fe_nfe["UK"] = UK_FALLBACK["aes_fe_nfe"]
        fe["UK"] = UK_FALLBACK["aes_fe"]
        nfe["UK"] = UK_FALLBACK["aes_nfe"]
    if "UK" not in aes_low:
        aes_low["UK"] = UK_FALLBACK["aes_low"]
    if "UK" not in aes_high:
        aes_high["UK"] = UK_FALLBACK["aes_high"]
    if "UK" not in cvt:
        cvt["UK"] = UK_FALLBACK["cvt_trng"]

    # --- assemble country-level indicator table ---
    countries_table: dict[str, dict[str, float | None]] = {}
    for c in ALL_COUNTRIES:
        fe_v = fe.get(c)
        nfe_v = nfe.get(c)
        scale = fe_nfe.get(c)
        # Speed = absolute non-formal participation rate.
        speed_raw = nfe_v
        # Equity = ratio of low-to-high educ AES participation.
        low_v = aes_low.get(c)
        high_v = aes_high.get(c)
        equity_raw = None
        if low_v is not None and high_v and high_v > 0:
            equity_raw = low_v / high_v
        countries_table[c] = {
            "speed_raw": speed_raw,
            "scale_raw": scale,
            "quality_raw": cvt.get(c),
            "equity_raw": equity_raw,
            "funding_raw": ALMP_TRAINING_GDP_PCT.get(c),
        }

    # --- compute percentile ranks per dimension per country ---
    def dim_series(key: str) -> list[float]:
        return [v[key] for v in countries_table.values() if v[key] is not None]

    dims = ["speed_raw", "scale_raw", "quality_raw", "equity_raw", "funding_raw"]
    dim_short = {"speed_raw": "speed", "scale_raw": "scale",
                 "quality_raw": "quality", "equity_raw": "equity",
                 "funding_raw": "funding"}

    country_pct: dict[str, dict[str, float | None]] = {}
    for c, row in countries_table.items():
        country_pct[c] = {}
        for d in dims:
            v = row[d]
            if v is None:
                country_pct[c][d] = None
            else:
                country_pct[c][d] = percentile_rank(v, dim_series(d))

    # --- aggregate per system ---
    rows: list[dict] = []
    # Already-published radar scores (headline) for delta reporting.
    headline_scores = {
        "Nordic Flexicurity":       {"speed": 9, "scale": 9, "quality": 9, "equity": 9, "funding": 8},
        "Germanic Dual System":     {"speed": 5, "scale": 7, "quality": 10, "equity": 7, "funding": 8},
        "Continental Corporatist":  {"speed": 7, "scale": 8, "quality": 7, "equity": 6, "funding": 8},
        "Liberal Market":           {"speed": 9, "scale": 7, "quality": 5, "equity": 4, "funding": 4},
        "Central/Eastern European": {"speed": 4, "scale": 4, "quality": 5, "equity": 4, "funding": 3},
        "Southern European":        {"speed": 3, "scale": 3, "quality": 4, "equity": 3, "funding": 3},
    }

    for system_name, country_codes in SYSTEMS:
        row: dict = {"system": system_name, "countries": "+".join(country_codes)}
        for d in dims:
            pcts = [country_pct[c][d] for c in country_codes if country_pct[c][d] is not None]
            if not pcts:
                row[f"{dim_short[d]}_avg_pct"] = None
                row[f"{dim_short[d]}_score"] = None
                row[f"{dim_short[d]}_raw_avg"] = None
                continue
            avg_pct = statistics.fmean(pcts)
            raw_avg = statistics.fmean(
                [countries_table[c][d] for c in country_codes
                 if countries_table[c][d] is not None]
            )
            score = score_from_percentile(avg_pct)
            row[f"{dim_short[d]}_avg_pct"] = round(avg_pct, 3)
            row[f"{dim_short[d]}_score"] = score
            row[f"{dim_short[d]}_raw_avg"] = round(raw_avg, 3)

        # Deltas vs headline.
        h = headline_scores[system_name]
        for k in ("speed", "scale", "quality", "equity", "funding"):
            derived = row.get(f"{k}_score")
            row[f"{k}_headline"] = h[k]
            row[f"{k}_delta"] = round(derived - h[k], 1) if derived is not None else None
        rows.append(row)

    # Print summary table.
    print("\n--- System radar scores (percentile-derived, 1-10) ---")
    print(f"{'System':<26} {'Speed':>6} {'Scale':>6} {'Qual':>6} {'Equity':>7} {'Fund':>5}")
    print(f"{'':<26} {'(H,D)':>6} {'(H,D)':>6} {'(H,D)':>6} {'(H,D)':>7} {'(H,D)':>5}")
    for r in rows:
        parts = [r["system"]]
        for k in ("speed", "scale", "quality", "equity", "funding"):
            s = r.get(f"{k}_score")
            h = r.get(f"{k}_headline")
            d = r.get(f"{k}_delta")
            parts.append(f"{s:>4.1f}({h},{d:+.0f})" if s is not None else "n/a")
        # Compact print
        print(f"{r['system']:<26} "
              f"{r['speed_score']:>4.1f}→{r['speed_headline']:>2}  "
              f"{r['scale_score']:>4.1f}→{r['scale_headline']:>2}  "
              f"{r['quality_score']:>4.1f}→{r['quality_headline']:>2}  "
              f"{r['equity_score']:>4.1f}→{r['equity_headline']:>2}  "
              f"{r['funding_score']:>4.1f}→{r['funding_headline']:>2}")

    return rows


if __name__ == "__main__":
    rows = compute()
    write_csv(rows, "system_radar.csv")
