"""What remains: NYC Landmarks Preservation Commission records, from NYC Open Data, and the
designation reports behind them.

Two datasets: Individual Landmark Sites (buis-pvji), which carries each site's NTA, and the
Individual Landmark and Historic District Building Database (gpmc-yuvp): every designated building
with its construction date, architect, style and original use. Each designation has a report, a PDF
with the building's or district's history, at s-media.nyc.gov under its LP number.
Landmark records cover only designated buildings and historic districts.
"""

import io
import re
import time
from collections import Counter

import httpx

from cache import BoundedCache
from pypdf import PdfReader

import geo

SITES_URL = "https://data.cityofnewyork.us/resource/buis-pvji.json"  # Individual Landmark Sites
BUILDINGS_URL = "https://data.cityofnewyork.us/resource/gpmc-yuvp.json"  # Building Database
DISTRICTS_URL = "https://data.cityofnewyork.us/resource/skyk-mpzq.json"  # Historic Districts
# LP-02694 -> .../lp/2694.pdf: the number without its leading zeros
REPORT_URL = "https://s-media.nyc.gov/agencies/lpc/lp/{number}.pdf"
HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
# Districts the Historic Districts dataset leaves out (it has 141), each checked against the title
# page of its report. Add more only after checking the PDF.
MISSING_DISTRICTS = {"East Village / Lower East Side Historic District": "LP-02491"}
# The building database files individual landmarks under this "district"
NOT_A_DISTRICT = "Individual Landmark"
MAX_RESULTS = 5
MAX_CHARS = 10_000
# Text on each side of a match in a report
CONTEXT_CHARS = 700

_cache = BoundedCache(20)  # newest entries only: see cache.py


def _get(url: str, params: dict | None = None) -> httpx.Response:
    for attempt in range(4):
        response = httpx.get(url, params=params, headers=HEADERS, timeout=90, follow_redirects=True)
        # NYC Open Data answers 503 now and then, and the same request works a moment later
        if response.status_code < 500 or attempt == 3:
            break
        time.sleep(2 ** attempt)
    response.raise_for_status()
    return response


def _query(url: str, params: dict) -> list[dict]:
    key = url + repr(sorted(params.items()))
    if key not in _cache:
        _cache[key] = _get(url, params).json()
    return _cache[key]


def report_url(lp_number: str) -> str | None:
    digits = re.sub(r"\D", "", lp_number or "")
    # Report files are named with at least 4 digits: LP-00187 is 0187.pdf (187.pdf is a 404)
    return REPORT_URL.format(number=f"{int(digits):04d}") if digits else None


def _point(geometry: dict) -> tuple[float, float] | None:
    """One point of a building's footprint (its first corner), enough to tell which NTA it's in."""
    try:
        coords = geometry["coordinates"]
        while isinstance(coords[0][0], list):
            coords = coords[0]
        return coords[0][0], coords[0][1]
    except (KeyError, IndexError, TypeError):
        return None


def _matches(record: dict, keyword: str | None, fields: list[str]) -> bool:
    if not keyword:
        return True
    text = " ".join(str(record.get(f, "")) for f in fields).lower()
    return all(w in text for w in keyword.lower().split())


def search_landmarks(nta_code: str, keyword: str | None = None) -> dict:
    """The designated landmarks and historic-district buildings in one NTA.

    Returns {nta, landmarks, districts, buildings, summary}: up to 5 individual landmarks and 5
    district buildings (those matching keyword, if given), every historic district with buildings
    here, and counts of construction decades, original uses and building types for all of them.
    """
    nta = geo.nta(nta_code)
    sites = _query(SITES_URL, {"$where": f"nta2020='{nta_code}'", "$limit": 1000,
                               "$select": "lpc_name,address,desdate,lpc_lpnumb,landmarkty,lpc_sitest,bbl"})
    landmark_fields = ["lpc_name", "address", "landmarkty"]
    landmarks = [{
        "name": s.get("lpc_name"), "address": s.get("address"), "type": s.get("landmarkty"),
        "status": s.get("lpc_sitest"), "designated": s.get("desdate"), "lp_number": s.get("lpc_lpnumb"),
        "report": report_url(s.get("lpc_lpnumb")),
    } for s in sites if _matches(s, keyword, landmark_fields)]

    # The building database has no NTA field: take its buildings in the NTA's bounding box, then
    # keep those inside the NTA's outline.
    west, south, east, north = nta["bbox"]
    box = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
    rows = _query(BUILDINGS_URL, {
        "$where": f"intersects(the_geom,'{box}') AND hist_dist IS NOT NULL AND hist_dist != '0'",
        "$select": "the_geom,bbl,des_addres,date_combo,date_low,arch_build,own_devel,style_prim,"
                   "use_orig,build_type,build_nme,hist_dist,notes",
        "$limit": 20000,
    })
    inside = [r for r in rows if (p := _point(r.get("the_geom") or {})) and geo.contains(nta_code, *p)]
    building_fields = ["des_addres", "build_nme", "use_orig", "build_type", "style_prim", "arch_build",
                       "own_devel", "notes", "hist_dist"]

    def clean(value):
        return None if value in (None, "0", "") else value

    buildings = [{
        "address": r.get("des_addres"), "name": clean(r.get("build_nme")), "built": clean(r.get("date_combo")),
        "architect": clean(r.get("arch_build")), "original_owner": clean(r.get("own_devel")),
        "style": clean(r.get("style_prim")), "original_use": clean(r.get("use_orig")),
        "building_type": clean(r.get("build_type")), "district": r.get("hist_dist"),
        "notes": clean(r.get("notes")),
    } for r in inside if _matches(r, keyword, building_fields)]

    decades = Counter(f"{int(r['date_low']) // 10 * 10}s" for r in inside
                      if (r.get("date_low") or "0").isdigit() and int(r["date_low"]) > 1600)
    district_names = Counter(r["hist_dist"] for r in inside if r["hist_dist"] != NOT_A_DISTRICT)
    return {
        "nta": {k: nta[k] for k in ("code", "name", "borough")},
        "keyword": keyword,
        "landmarks": landmarks[:MAX_RESULTS],
        "landmarks_total": len(landmarks),
        "districts": [{"name": name, "buildings_here": count, **_district(name)}
                      for name, count in district_names.most_common()],
        "buildings": buildings[:MAX_RESULTS],
        "buildings_total": len(buildings),
        "summary": {
            "district_buildings_here": len(inside),
            "built_by_decade": dict(sorted(decades.items())),
            "original_use": dict(Counter(clean(r.get("use_orig")) or "not recorded" for r in inside).most_common(8)),
            "building_type": dict(Counter(clean(r.get("build_type")) or "not recorded" for r in inside).most_common(8)),
        },
        "source": BUILDINGS_URL,
    }


def _district(name: str) -> dict:
    """A historic district's LP number, designation date and report, looked up by its name."""
    rows = _query(DISTRICTS_URL, {"$select": "lp_number,area_name,desdate", "$limit": 1000})
    for row in rows:
        if row.get("area_name", "").lower().replace(" ", "") == name.lower().replace(" ", ""):
            return {"lp_number": row.get("lp_number"), "designated": (row.get("desdate") or "")[:10],
                    "report": report_url(row.get("lp_number"))}
    if name in MISSING_DISTRICTS:
        return {"lp_number": MISSING_DISTRICTS[name], "designated": None,
                "report": report_url(MISSING_DISTRICTS[name])}
    return {"lp_number": None, "designated": None, "report": None}


def read_landmark_report(url: str, terms: str = "") -> dict:
    """A designation report's text around terms, with page numbers: {url, pages, text}.
    Without terms, the first pages (the summary and history usually come first)."""
    if not re.match(r"https?://s-media\.nyc\.gov/agencies/lpc/lp/\d+\.pdf$", url):
        raise ValueError(f"Not an LPC designation report URL: {url}")
    if url not in _cache:
        reader = PdfReader(io.BytesIO(_get(url).content))
        _cache[url] = [(page.extract_text() or "") for page in reader.pages]
    pages: list[str] = _cache[url]
    words = [w for w in re.findall(r"[a-z0-9]+", terms.lower()) if len(w) > 2]
    chunks, used = [], 0
    if words:
        # Pages with the most matched terms first; on each, the text around each match
        scored = sorted(((sum(p.lower().count(w) for w in words), i) for i, p in enumerate(pages)), reverse=True)
        for score, i in scored:
            if not score or used >= MAX_CHARS:
                break
            text = re.sub(r"\s+", " ", pages[i])
            lower = text.lower()
            spans = []
            for w in words:
                for m in re.finditer(re.escape(w), lower):
                    start, end = max(0, m.start() - CONTEXT_CHARS), m.end() + CONTEXT_CHARS
                    if spans and start <= spans[-1][1]:
                        spans[-1] = (spans[-1][0], max(spans[-1][1], end))
                    else:
                        spans.append((start, end))
            spans.sort()
            for start, end in spans:
                piece = text[start:end]
                chunks.append((i + 1, piece))
                used += len(piece)
                if used >= MAX_CHARS:
                    break
    if not chunks:
        for i, page in enumerate(pages):
            if used >= MAX_CHARS:
                break
            piece = re.sub(r"\s+", " ", page)[:MAX_CHARS - used]
            chunks.append((i + 1, piece))
            used += len(piece)
    chunks.sort()
    return {
        "url": url,
        "page_count": len(pages),
        "matched": bool(words) and any(True for _ in chunks),
        "text": "\n\n".join(f"[p. {n}] {piece}" for n, piece in chunks),
    }


def search_to_text(found: dict) -> str:
    nta = found["nta"]
    lines = [f"# Landmark records in {nta['name']} ({nta['code']}, {nta['borough']})"
             + (f", matching '{found['keyword']}'" if found["keyword"] else "")]
    lines.append(f"\n## Individual landmarks ({found['landmarks_total']} found, {len(found['landmarks'])} shown)")
    for l in found["landmarks"]:
        lines.append(f"- {l['name']}, {l['address']} ({l['type']}, {l['status']} {l['designated']}). "
                     f"Report: {l['report']}")
    lines.append(f"\n## Historic districts with buildings here")
    for d in found["districts"]:
        lines.append(f"- {d['name']}: {d['buildings_here']} buildings here"
                     + (f", designated {d['designated']}" if d["designated"] else "")
                     + f". Report: {d['report'] or 'not found'}")
    if not found["districts"]:
        lines.append("- None.")
    s = found["summary"]
    lines.append(f"\n## All {s['district_buildings_here']} designated buildings here (districts and landmarks)")
    lines.append(f"Built, by decade: {s['built_by_decade']}")
    lines.append(f"Original use: {s['original_use']}")
    lines.append(f"Building type: {s['building_type']}")
    lines.append(f"\n## District buildings ({found['buildings_total']} found, {len(found['buildings'])} shown)")
    for b in found["buildings"]:
        details = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in b.items() if v and k != "address")
        lines.append(f"- {b['address']}: {details}")
    lines.append(f"\nSource: {found['source']} and {SITES_URL}")
    return "\n".join(lines)


def report_to_text(report: dict) -> str:
    note = "" if report["matched"] else "\n(No page mentions the search terms: showing the first pages.)"
    return f"# Designation report ({report['page_count']} pages)\nSource: {report['url']}{note}\n\n{report['text']}"


if __name__ == "__main__":
    # Smoke test: uv run lpc.py MN0302 synagogue
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "MN0302"
    keyword = sys.argv[2] if len(sys.argv) > 2 else None
    found = search_landmarks(code, keyword)
    assert found["landmarks_total"] or found["summary"]["district_buildings_here"], "no landmark records"
    print(search_to_text(found)[:3000])
    url = next((l["report"] for l in found["landmarks"] if l["report"]), None)
    assert url, "no report link"
    report = read_landmark_report(url, keyword or "immigrant")
    assert report["text"], "empty report"
    print("\n" + report_to_text(report)[:1200])
