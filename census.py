"""Who lives in a neighborhood now, and since 2000: ancestry, birthplace of the foreign-born, and
language spoken at home, from the Census API, summed over the neighborhood's census tracts.

Sources: the 2000 Census long form (SF3), and the American Community Survey 5-year estimates
(2010 on; "2015" means 2011-2015). The 1990 long form is not in the Census API, and the 2010 Census
asked none of these questions. Only these three topics: this project is about who settled where,
not rents or incomes.

Neighborhoods are 2020 NTAs, built from 2020 tracts. Older years use older tracts, so we match each
2020 tract to the older tract it was split from (or the tracts merged into it), and say how good the
match is. Figures for older years are approximate for that reason.
"""

import math
import os
import time

import httpx

from cache import BoundedCache

import geo

API = "https://api.census.gov/data"
HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
# 2010, not 2009: the 2009 5-year tables aren't on data.census.gov, which the citations link to
FIRST_ACS, LAST_ACS = 2010, 2024
# topic -> (2000 SF3 table, ACS table). 2000 language is only published crossed with age: not used.
TABLES = {
    "ancestry": ("PCT018", "B04006"),  # people reporting each ancestry (a person can report two)
    "birthplace": ("PCT019", "B05006"),  # place of birth of the foreign-born
    "language": (None, "B16001"),  # language spoken at home, ages 5 and up (see _table)
}
# Tract-level language data is B16001 through 2015; from 2016 B16001 is blank for tracts and the
# shorter C16001 has the same languages, grouped.
LANGUAGE_SWITCH = 2016
MAX_GROUPS = 15
# An ACS estimate whose margin of error is this large relative to it is too noisy to lean on:
# coefficient of variation = (MOE / 1.645) / estimate, and 0.3 is the usual "use with caution" line.
NOISY_CV = 0.3

_cache = BoundedCache(200)  # newest entries only: see cache.py


def _get_json(url: str, params: dict | None = None, key: bool = True):
    cache_key = url + repr(sorted((params or {}).items()))
    if cache_key in _cache:
        return _cache[cache_key]
    if key and not os.environ.get("CENSUS_API_KEY"):
        raise RuntimeError("Set CENSUS_API_KEY in this project's .env file.")
    full = {**(params or {}), **({"key": os.environ["CENSUS_API_KEY"].strip()} if key else {})}
    for attempt in range(3):
        response = httpx.get(url, params=full, headers=HEADERS, timeout=60, follow_redirects=True)
        if response.status_code < 500 or attempt == 2:
            break
        time.sleep(2 ** attempt)
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", ""):
        # The API answers a bad key with a 200 HTML page titled "Invalid Key"
        raise RuntimeError("The Census API rejected the request (is CENSUS_API_KEY activated?)")
    _cache[cache_key] = response.json()
    return _cache[cache_key]


def _dataset(year: int) -> str:
    if year == 2000:
        return "2000/dec/sf3"
    if FIRST_ACS <= year <= LAST_ACS:
        return f"{year}/acs/acs5"
    raise ValueError(f"No tract-level ancestry, birthplace or language data for {year}: "
                     f"use 2000 or an ACS 5-year from {FIRST_ACS} to {LAST_ACS}.")


def _tract_vintage(year: int) -> int:
    """Which decade's tracts a year's data uses."""
    return 2020 if year >= 2020 else 2010 if year >= 2010 else 2000


def _labels(dataset: str, table: str) -> dict[str, str]:
    """Estimate variable -> its label path, e.g. 'Total!!Europe!!Northern Europe!!Ireland'."""
    variables = _get_json(f"{API}/{dataset}/groups/{table}.json", key=False)["variables"]
    labels = {}
    for name, v in variables.items():
        if name.startswith(table) and (name.endswith("E") or dataset.startswith("2000")):
            labels[name] = v["label"].replace("Estimate!!", "").replace(":", "")
    return labels


def _categories(labels: dict[str, str], topic: str) -> dict[str, str]:
    """The variables to report: the most detailed groups (labels nothing else nests under).
    For language, the table splits each language by how well people speak English: report the language."""
    paths = set(labels.values())
    leaves = {}
    for name, label in labels.items():
        if any(other.startswith(label + "!!") for other in paths):
            if topic == "language" and all("Speak English" in other.rsplit("!!", 1)[-1]
                                           for other in paths if other.startswith(label + "!!")):
                leaves[name] = label  # a language, split only by English ability
            continue
        if topic == "language" and "Speak English" in label.rsplit("!!", 1)[-1]:
            continue
        leaves[name] = label
    return leaves


def _match_tracts(tracts_2020: list[str], available: set[str]) -> tuple[list[str], dict]:
    """The older tracts that cover the same ground as these 2020 tracts. A split tract keeps its
    number with a suffix (001400 -> 001401, 001402), so match on the number before the suffix."""
    matched, exact, approximate, missing = [], 0, 0, []
    for tract in tracts_2020:
        if tract in available:
            choice, exact = [tract], exact + 1
        elif (parent := tract[:4] + "00") in available:
            choice, approximate = [parent], approximate + 1
        else:
            choice = sorted(t for t in available if t[:4] == tract[:4])
            approximate += bool(choice)
            if not choice:
                missing.append(tract)
        matched += [t for t in choice if t not in matched]
    return matched, {"exact": exact, "approximate": approximate, "missing": missing}


def profile(nta_code: str, year: int, topic: str) -> dict:
    """The largest groups for one topic in one NTA and year, summed over its tracts.
    Returns {nta, year, topic, total, groups: [{group, estimate, moe, share, noisy}], tracts, source}."""
    if topic not in TABLES:
        raise ValueError(f"topic must be one of {sorted(TABLES)}")
    nta = geo.nta(nta_code)
    dataset = _dataset(year)
    table = TABLES[topic][0] if year == 2000 else TABLES[topic][1]
    if topic == "language" and year >= LANGUAGE_SWITCH:
        table = "C16001"
    if not table:
        raise ValueError(f"No tract-level {topic} table for {year}: try an ACS year ({FIRST_ACS}-{LAST_ACS}).")
    labels = _labels(dataset, table)
    params = {"get": f"group({table})", "for": "tract:*", "in": f"state:36 county:{nta['county']}"}
    rows = _get_json(f"{API}/{dataset}", params)
    header, data = rows[0], rows[1:]
    # The 2000 data names a tract without a suffix by 4 digits ('0012' for 001200): pad to 6
    by_tract = {row[header.index("tract")].ljust(6, "0"): dict(zip(header, row)) for row in data}

    if _tract_vintage(year) == 2020:
        tracts, match = list(nta["tracts"]), {"exact": len(nta["tracts"]), "approximate": 0, "missing": []}
        tracts = [t for t in tracts if t in by_tract]
    else:
        tracts, match = _match_tracts(nta["tracts"], set(by_tract))

    def number(row: dict, name: str) -> float:
        try:
            value = float(row.get(name) or 0)
        except ValueError:
            return 0.0
        return value if value >= 0 else 0.0  # negative values are the API's "no data" codes

    categories = _categories(labels, topic)
    total_name = min(labels, key=lambda n: labels[n].count("!!"))  # 'Total'
    acs = year != 2000
    groups = []
    for name, label in categories.items():
        estimate = sum(number(by_tract[t], name) for t in tracts)
        if not estimate:
            continue
        moe = math.sqrt(sum(number(by_tract[t], name[:-1] + "M") ** 2 for t in tracts)) if acs else None
        groups.append({"group": label.split("!!", 1)[-1].replace("!!", " > "), "estimate": round(estimate),
                       "moe": round(moe) if moe is not None else None,
                       "noisy": bool(acs and (moe / 1.645) / estimate > NOISY_CV)})
    total = sum(number(by_tract[t], total_name) for t in tracts)
    groups.sort(key=lambda g: -g["estimate"])
    for g in groups:
        g["share"] = round(g["estimate"] / total, 3) if total else None
    # Cite the table on data.census.gov, the Census Bureau's public viewer, for these tracts. The API URL
    # we fetched can't be cited: it needs our key, and without one the API answers "Missing Key".
    survey_id = "DECENNIALSF32000" if year == 2000 else f"ACSDT5Y{year}"
    # The viewer takes several tracts as one prefix, then the others' IDs: 1400000US36047050801,36047050803
    geos = "1400000US" + ",".join(f"36{nta['county']}{t}" for t in tracts)
    source = f"https://data.census.gov/table/{survey_id}.{table}?g={geos}"
    return {
        "nta": {k: nta[k] for k in ("code", "name", "borough")},
        "year": year,
        "survey": "2000 Census (SF3)" if year == 2000 else f"ACS 5-year {year - 4}-{year}",
        "topic": topic,
        "table": table,
        "total": round(total),
        "total_label": labels[total_name],
        "groups": groups[:MAX_GROUPS],
        "tracts": {"used": tracts, "vintage": _tract_vintage(year), **match},
        "source": source,
    }


def to_text(p: dict) -> str:
    nta = p["nta"]
    lines = [f"# {p['topic'].title()} in {nta['name']} ({nta['code']}, {nta['borough']}), {p['survey']}",
             f"Table {p['table']}. Total ({p['total_label']}): {p['total']:,}"]
    if p["topic"] == "ancestry":
        lines.append("A person can report up to two ancestries, so shares can add to more than 100%. "
                     "The table has no separate entry for most Asian and Hispanic origins (e.g. Chinese, "
                     "Dominican): they fall under 'Other groups'. Use birthplace for those.")
    t = p["tracts"]
    if t["vintage"] != 2020:
        rough = t["approximate"] or t["missing"]
        lines.append(f"{'Approximate' if rough else 'Close'}: {t['vintage']} tracts matched to today's neighborhood "
                     f"({t['exact']} exact, {t['approximate']} approximate"
                     + (f", {len(t['missing'])} with no match" if t["missing"] else "") + ").")
    lines.append("\nGroup | Estimate | MOE | Share")
    for g in p["groups"]:
        moe = f"±{g['moe']:,}" if g["moe"] is not None else "n/a"
        flag = " (small, uncertain)" if g["noisy"] else ""
        share = f"{g['share']:.1%}" if g["share"] is not None else ""
        lines.append(f"{g['group']} | {g['estimate']:,} | {moe} | {share}{flag}")
    lines.append(f"\nSource: {p['source']}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test: uv run census.py MN0302 2024 ancestry
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    code = sys.argv[1] if len(sys.argv) > 1 else "MN0302"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    topic = sys.argv[3] if len(sys.argv) > 3 else "birthplace"
    p = profile(code, year, topic)
    assert p["total"] > 0 and p["groups"], "no data"
    print(to_text(p))
    old = profile(code, 2000, "birthplace")
    assert old["tracts"]["used"], "no 2000 tracts matched"
    print("\n" + to_text(old)[:900])
