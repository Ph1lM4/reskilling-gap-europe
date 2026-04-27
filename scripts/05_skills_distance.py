"""Ground the skills-distance 0-10 scores for the 16 transition pairs.

Method
------
1. Load the ESCO occupation-skill relations matrix and the ESCO skill pillar
   hierarchy (local paths per DATA-REGISTRY.md).
2. Aggregate each leaf skill to its Level-2 ESCO skill group (156 buckets,
   down from ~14K raw skills). This reduces vector sparsity: at raw-skill
   resolution almost every A->C pair has cosine 0, which collapses the
   metric; at Level-2 the cosine has meaningful gradient.
3. For each occupation, build a Level-2 bucket vector: essential = 1.0,
   optional = 0.5 (max over duplicate edges). Knowledge-type and
   skill/competence-type relations are both retained.
4. Map each transition label to a pool of ISCO 4-digit codes. Every ESCO
   occupation whose iscoGroup starts with any code in the pool is pulled
   into the cluster (stub occupations with <5 bucketed skills are dropped).
5. Compute all pairwise cosine similarities over the src x dst cross-product
   and take the median (the median is robust to outlier role pairs that
   happen to share idiosyncratic skills -- per the session brief).
6. Skills distance = round(10 * (1 - median_cosine), 1).

Calibration note
----------------
ESCO raw cosine has a systematic floor: because the ESCO skill taxonomy is
fine-grained, even within-zone transitions do not approach cosine 1. The
resulting absolute distances (6-10 range) run higher than the human-anchored
0-10 scores already on transitions.html (2-9 range). The rank-ORDER across
the 16 pairs is what is grounded here; the absolute calibration shift is
flagged in the delta table and not overwritten.
"""

from __future__ import annotations

import csv
import math
import pathlib
import statistics
from collections import defaultdict

from _common import write_csv

ESCO_DIR = pathlib.Path(
    "/Users/philippmaul/Documents/projects/european-ai-exposure-map/data/esco"
)
OCC_SKILL_REL = ESCO_DIR / "occupationSkillRelations_en.csv"
OCCUPATIONS = ESCO_DIR / "occupations_en.csv"
BROADER_REL = ESCO_DIR / "broaderRelationsSkillPillar_en.csv"
HIERARCHY = ESCO_DIR / "skillsHierarchy_en.csv"

WEIGHT_ESSENTIAL = 1.0
WEIGHT_OPTIONAL = 0.5
MIN_BUCKETS_PER_OCC = 5
WALK_MAX_STEPS = 6


ISCO_ANCHOR: dict[str, list[str]] = {
    "admin_secretarial":     ["4110", "4120"],
    "customer_service":      ["4222", "4229"],
    "numerical_clerk":       ["4311", "4312"],
    "general_clerk":         ["4110", "4120"],
    "business_admin_prof":   ["2421", "2411"],
    "legal_prof":            ["2611"],
    "legal_social_prof":     ["2611", "2635"],
    "care_assistant":        ["5321", "5322"],
    "registered_nurse":      ["2221"],
    "electrician":           ["7411", "7412"],
    "plumber_hvac":          ["7126"],
    "ece_educator":          ["2342"],
    "construction":          ["7112", "7113", "7114", "7119", "9313"],
    "truck_driver":          ["8332"],
    "compliance_spec":       ["2422", "2411", "2619"],
    "ai_governance":         ["2619", "2422"],
    "ai_ops_coordinator":    ["2421", "1213"],
    "service_designer":      ["2166", "2423", "2513"],
    "data_engineer_ai":      ["2511", "2512"],
    "data_analyst":          ["2511"],
    "data_ai_specialist":    ["2511", "2512"],
}

TRANSITIONS: list[tuple[str, str, str, str, float | None]] = [
    # (kind, from_label, to_label, display, headline_transitions.html distance)
    ("a_to_c",      "admin_secretarial",   "care_assistant",       "Admin/secretarial -> Care assistant",                         6),
    ("a_to_c",      "customer_service",    "care_assistant",       "Customer service clerk -> Care assistant",                    5),
    ("a_to_c",      "admin_secretarial",   "registered_nurse",     "Admin/secretarial -> Registered nurse",                       8),
    ("a_to_c",      "business_admin_prof", "electrician",          "Business admin prof -> Electrician",                          8),
    ("a_to_c",      "general_clerk",       "plumber_hvac",         "General clerk -> Plumber/HVAC",                               8),
    ("a_to_c",      "legal_social_prof",   "ece_educator",         "Legal/social prof -> Early childhood educator",               5),
    ("a_to_c",      "admin_secretarial",   "construction",         "Admin/secretarial -> Construction worker",                    9),
    ("a_to_c",      "numerical_clerk",     "truck_driver",         "Numerical clerk -> Truck/logistics driver",                   6),
    ("a_to_aplus",  "business_admin_prof", "compliance_spec",      "Business admin prof -> Compliance/regulatory specialist",     2),
    ("a_to_aplus",  "legal_prof",          "ai_governance",        "Legal professional -> AI governance specialist",              2),
    ("a_to_aplus",  "business_admin_prof", "ai_ops_coordinator",   "Business admin prof -> AI-augmented ops coordinator",         2),
    ("a_to_aplus",  "admin_secretarial",   "ai_ops_coordinator",   "Admin/secretarial -> AI-augmented ops coordinator",           3),
    ("a_to_aplus",  "customer_service",    "service_designer",     "Customer service clerk -> AI-human hybrid service designer",  5),
    ("a_to_aplus",  "business_admin_prof", "data_engineer_ai",     "Business admin prof -> Data engineer/AI specialist",          5),
    ("a_to_aplus",  "numerical_clerk",     "data_analyst",         "Numerical clerk -> Data analyst",                             5),
    ("a_to_aplus",  "admin_secretarial",   "data_ai_specialist",   "Admin/secretarial -> Data/AI specialist",                     6),
]


def load_level2_uris() -> set[str]:
    uris: set[str] = set()
    with HIERARCHY.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            uri = row.get("Level 2 URI") or ""
            if uri:
                uris.add(uri)
    return uris


def load_broader_relations() -> tuple[dict[str, str], dict[str, str]]:
    """Return (leaf_parent, group_parent) from broaderRelationsSkillPillar."""
    leaf_parent: dict[str, str] = {}
    group_parent: dict[str, str] = {}
    with BROADER_REL.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["conceptType"] == "KnowledgeSkillCompetence":
                leaf_parent[row["conceptUri"]] = row["broaderUri"]
            elif row["conceptType"] == "SkillGroup":
                group_parent[row["conceptUri"]] = row["broaderUri"]
    return leaf_parent, group_parent


def build_leaf_to_l2(
    leaf_parent: dict[str, str],
    group_parent: dict[str, str],
    l2_uris: set[str],
) -> dict[str, str]:
    """Map each leaf skill URI to its Level-2 ancestor in the skill pillar.

    Walk the broader chain until we hit a Level-2 URI; if that fails within
    WALK_MAX_STEPS, fall back to the direct parent group.
    """
    leaf_bucket: dict[str, str] = {}
    for leaf, parent in leaf_parent.items():
        cur = parent
        hit = None
        for _ in range(WALK_MAX_STEPS):
            if cur in l2_uris:
                hit = cur
                break
            if cur not in group_parent:
                break
            cur = group_parent[cur]
        leaf_bucket[leaf] = hit or parent
    return leaf_bucket


def load_occupations() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    with OCCUPATIONS.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            out[row["conceptUri"]] = (str(row["iscoGroup"]), row["preferredLabel"])
    return out


def build_bucket_vectors(
    leaf_bucket: dict[str, str],
) -> dict[str, dict[str, float]]:
    vectors: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with OCC_SKILL_REL.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            occ = row["occupationUri"]
            skill = row["skillUri"]
            rel = row.get("relationType", "").strip()
            w = WEIGHT_ESSENTIAL if rel == "essential" else WEIGHT_OPTIONAL
            bucket = leaf_bucket.get(skill, skill)
            if vectors[occ][bucket] < w:
                vectors[occ][bucket] = w
    # Collapse defaultdicts.
    return {k: dict(v) for k, v in vectors.items()}


def cluster_vectors(
    prefixes: list[str],
    occ_meta: dict[str, tuple[str, str]],
    vectors: dict[str, dict[str, float]],
) -> list[tuple[str, dict[str, float]]]:
    out: list[tuple[str, dict[str, float]]] = []
    for uri, (isco, label) in occ_meta.items():
        if not any(isco.startswith(p) for p in prefixes):
            continue
        vec = vectors.get(uri, {})
        if len(vec) < MIN_BUCKETS_PER_OCC:
            continue
        out.append((label, vec))
    return out


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def compute() -> list[dict]:
    l2_uris = load_level2_uris()
    leaf_parent, group_parent = load_broader_relations()
    leaf_bucket = build_leaf_to_l2(leaf_parent, group_parent, l2_uris)
    occ_meta = load_occupations()
    vectors = build_bucket_vectors(leaf_bucket)

    print(f"[05] Hierarchy: {len(l2_uris)} Level-2 URIs.")
    print(f"[05] Skills:    {len(leaf_parent):,} leaves mapped to "
          f"{len(set(leaf_bucket.values())):,} distinct buckets.")
    print(f"[05] Occupations: {len(occ_meta):,} rows, "
          f"{len(vectors):,} with skill vectors.")

    clusters: dict[str, list[tuple[str, dict[str, float]]]] = {}
    for label, prefixes in ISCO_ANCHOR.items():
        clusters[label] = cluster_vectors(prefixes, occ_meta, vectors)
        if not clusters[label]:
            print(f"[05] WARNING: empty cluster for '{label}' (ISCO {prefixes})")

    rows: list[dict] = []
    for kind, src_label, dst_label, display, headline in TRANSITIONS:
        src = clusters[src_label]
        dst = clusters[dst_label]
        if not src or not dst:
            continue
        sims = [cosine(sv, dv) for _, sv in src for _, dv in dst]
        if not sims:
            continue
        med = statistics.median(sims)
        mean_ = statistics.fmean(sims)
        distance = round(10.0 * (1.0 - med), 1)
        delta = round(distance - headline, 1) if headline is not None else None
        rows.append({
            "kind": kind,
            "transition": display,
            "from_isco": "+".join(ISCO_ANCHOR[src_label]),
            "to_isco": "+".join(ISCO_ANCHOR[dst_label]),
            "n_from_esco": len(src),
            "n_to_esco": len(dst),
            "pair_count": len(sims),
            "cosine_median": round(med, 4),
            "cosine_mean": round(mean_, 4),
            "distance_0_10": distance,
            "headline_distance": headline,
            "delta": delta,
        })

    print("\n--- Skills distance (ESCO cosine, L2-bucketed, median-aggregated) ---")
    print(f"{'Transition':<62} {'ESCO':>10} {'Cosine':>8} {'Dist':>5} {'Head':>5} {'Delta':>6}")
    for r in rows:
        h = f"{r['headline_distance']}" if r['headline_distance'] is not None else "-"
        d = f"{r['delta']:+.1f}" if r['delta'] is not None else "-"
        print(f"{r['transition']:<62} "
              f"{r['n_from_esco']}x{r['n_to_esco']:<5} "
              f"{r['cosine_median']:>7.3f}  "
              f"{r['distance_0_10']:>4.1f}  "
              f"{h:>4}  "
              f"{d:>5}")

    # Rank-order correlation with headline (Spearman, computed manually).
    paired = [(r["distance_0_10"], r["headline_distance"]) for r in rows
              if r["headline_distance"] is not None]
    spearman = _spearman(paired)
    print(f"\nSpearman rank correlation with transitions.html headlines: {spearman:.3f}")

    return rows


def _spearman(pairs: list[tuple[float, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    rx = _rank(x)
    ry = _rank(y)
    n = len(pairs)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mean_rx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - mean_ry) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else 0.0


def _rank(xs: list[float]) -> list[float]:
    sorted_idx = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[sorted_idx[j + 1]] == xs[sorted_idx[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[sorted_idx[k]] = avg_rank
        i = j + 1
    return ranks


if __name__ == "__main__":
    rows = compute()
    write_csv(rows, "skills_distance.csv")
