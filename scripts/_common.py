"""Shared helpers for the four derivation scripts.

Each script is designed to be runnable with or without network access: if the
Eurostat JSON-stat endpoint is unreachable, the script falls back to a cached
pull in ``data/``. The cached pulls are committed so the computation is fully
reproducible offline.
"""

from __future__ import annotations

import json
import pathlib
import typing as t
import urllib.request
import urllib.parse
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)

EUROSTAT_BASE = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
)

COUNTRIES = [
    ("EU27_2020", "EU27", "EU-27"),
    ("DE", "DE", "Germany"),
    ("FR", "FR", "France"),
    ("IT", "IT", "Italy"),
    ("ES", "ES", "Spain"),
    ("UK", "UK", "United Kingdom"),
    ("AT", "AT", "Austria"),
    ("CH", "CH", "Switzerland"),
]


def fetch_eurostat(
    table: str,
    params: dict[str, t.Any],
    cache_name: str | None = None,
    timeout: int = 30,
) -> dict:
    """Fetch an Eurostat JSON-stat table, falling back to a cached file.

    Parameters
    ----------
    table : dataset code, e.g. ``"lfsa_egai2d"``
    params : query parameters. Multi-valued params may be supplied as lists.
    cache_name : basename used under ``data/`` for offline fallback.
    timeout : seconds before giving up on the live fetch.
    """
    cache_name = cache_name or f"{table}.json"
    cache_path = DATA / cache_name

    query_parts: list[tuple[str, str]] = [("format", "JSON"), ("lang", "EN")]
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            for v in value:
                query_parts.append((key, str(v)))
        else:
            query_parts.append((key, str(value)))

    url = EUROSTAT_BASE + table + "?" + urllib.parse.urlencode(query_parts)

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.load(resp)
        cache_path.write_text(json.dumps(payload))
        print(f"[fetch] {table}: live {len(json.dumps(payload))} bytes -> {cache_path}")
        return payload
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        if cache_path.exists():
            print(f"[fetch] {table}: live failed ({exc}); using cache {cache_path}")
            return json.loads(cache_path.read_text())
        raise RuntimeError(
            f"Live fetch failed and no cache at {cache_path}: {exc}"
        ) from exc


def jsonstat_value(payload: dict, coords: dict[str, str]) -> float | None:
    """Look up a single value in a JSON-stat v2 payload by coordinate names."""
    dims = payload["id"]
    sizes = [payload["size"][i] for i in range(len(dims))]
    strides: list[int] = []
    stride = 1
    for size in reversed(sizes):
        strides.insert(0, stride)
        stride *= size

    idx = 0
    for i, dim in enumerate(dims):
        cat_idx = payload["dimension"][dim]["category"]["index"]
        want = coords[dim]
        if want not in cat_idx:
            return None
        idx += cat_idx[want] * strides[i]

    raw = payload.get("value", {})
    if isinstance(raw, dict):
        return raw.get(str(idx))
    try:
        return raw[idx]
    except (IndexError, TypeError):
        return None


def write_csv(rows: list[dict], name: str) -> pathlib.Path:
    """Write a list of dicts to ``output/<name>.csv`` and return the path."""
    out = OUTPUT / name
    if not rows:
        out.write_text("")
        return out
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    out.write_text("\n".join(lines) + "\n")
    print(f"[write] {out}")
    return out
