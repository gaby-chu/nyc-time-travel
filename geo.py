"""Helpers, not research sources: neighborhood names and addresses -> NTAs and census tracts,
addresses -> BBLs, and links to the Municipal Archives' tax photos.

Informal names ("Koreatown", "Little Germany") aren't in any list here: the model turns them into an
official NTA name or a street address it knows is there, and neighborhood_at() checks the address
against the real NTA boundaries.

The neighborhood list is NYC Department of City Planning's 2020 Neighborhood Tabulation Areas (NTAs),
with the 2020 census tracts in each, from NYC Open Data. `uv run geo.py build` downloads them once
into data/ntas.json; the app only reads that file.
"""

import difflib
import html
import json
import re
import time
from pathlib import Path

import httpx

HERE = Path(__file__).parent
NTAS_FILE = HERE / "data" / "ntas.json"

NTA_URL = "https://data.cityofnewyork.us/resource/9nt8-h7nd.json"  # 2020 NTAs, with boundaries
TRACTS_URL = "https://data.cityofnewyork.us/resource/hm78-6dwm.json"  # 2020 tract -> NTA equivalency
GEOSEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"
# The Municipal Archives' tax photos, searchable by an identifier built from borough, block and lot.
TAX_SEARCH_URL = "https://nycrecords.access.preservica.com/?s={query}"
TAX_ITEM_URL = "https://nycrecords.access.preservica.com/uncategorized/{id}/"
TAX_THUMB_URL = "https://nycrecords.access.preservica.com/download/thumbnail/{id}"  # 400 px; ?size=large is bigger
TAX_FILE_URL = "https://nycrecords.access.preservica.com/download/file/{id}"  # the full scan, 0.4 to 3 MB
# A search result: <div ... onclick="window.location='.../IO_<uuid>/'" title="1000 Flatbush Avenue">
TAX_RESULT = re.compile(r"onclick=\"window\.location='[^']*/(IO_[0-9a-f-]{36})/'\" title=\"([^\"]*)\"")

HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
BOROUGH_CODES = {"Manhattan": "1", "Bronx": "2", "Brooklyn": "3", "Queens": "4", "Staten Island": "5"}
# NTA types: 0 is a residential neighborhood. The rest are parks, cemeteries, airports and the like.
NTA_TYPES = {"0": "neighborhood", "5": "rikers island", "6": "special use", "7": "cemetery",
             "8": "airport", "9": "park"}

_cache: dict[str, object] = {}


def _get_json(url: str, params: dict | None = None):
    key = url + json.dumps(params or {}, sort_keys=True)
    if key not in _cache:
        for attempt in range(4):
            response = httpx.get(url, params=params, headers=HEADERS, timeout=60)
            # NYC Open Data answers 503 now and then, and the same request works a moment later
            if response.status_code < 500 or attempt == 3:
                break
            time.sleep(2 ** attempt)
        response.raise_for_status()
        _cache[key] = response.json()
    return _cache[key]


# --- The lookup file: built once, read at startup ---


def build() -> None:
    """Download the 2020 NTAs and their tracts into data/ntas.json."""
    ntas = {}
    for row in _get_json(NTA_URL, {"$limit": 1000}):
        rings = [ring for polygon in row["the_geom"]["coordinates"] for ring in polygon]
        xs = [x for ring in rings for x, _ in ring]
        ys = [y for ring in rings for _, y in ring]
        ntas[row["nta2020"]] = {
            "code": row["nta2020"],
            "name": row["ntaname"],
            "borough": row["boroname"],
            "county": row["countyfips"],
            "type": NTA_TYPES.get(row["ntatype"], row["ntatype"]),
            "tracts": [],
            # [min lon, min lat, max lon, max lat], and the outline to test points against
            "bbox": [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)],
            "polygons": [[[[round(x, 6), round(y, 6)] for x, y in ring] for ring in polygon]
                         for polygon in row["the_geom"]["coordinates"]],
        }
    for row in _get_json(TRACTS_URL, {"$limit": 5000}):
        ntas[row["ntacode"]]["tracts"].append(row["ct2020"])
    NTAS_FILE.parent.mkdir(exist_ok=True)
    NTAS_FILE.write_text(json.dumps(ntas, separators=(",", ":")))
    print(f"Wrote {len(ntas)} NTAs, {sum(len(n['tracts']) for n in ntas.values())} tracts to {NTAS_FILE}")


NTAS: dict[str, dict] = json.loads(NTAS_FILE.read_text()) if NTAS_FILE.exists() else {}


def nta(code: str) -> dict:
    """The NTA with this code, without its outline."""
    if code not in NTAS:
        raise LookupError(f"No NTA with code {code!r}")
    return {k: v for k, v in NTAS[code].items() if k != "polygons"}


def contains(code: str, lon: float, lat: float) -> bool:
    """Is the point inside the NTA? Ray casting over each polygon's rings (holes flip it back)."""
    inside = False
    for polygon in NTAS[code]["polygons"]:
        for ring in polygon:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
    return inside


# --- Neighborhood names -> NTAs ---


def _normalize(text: str) -> str:
    """"Hell's Kitchen" -> "hells kitchen", "St. George" -> "st george"."""
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'", "")).split())


def resolve_neighborhood(name: str) -> list[dict]:
    """Candidate NTAs for an official neighborhood name, best first: NTAs whose name is it or
    contains it, then close spellings. Each candidate has its tracts. Informal names won't match:
    use neighborhood_at() with an address there instead."""
    query = _normalize(name)
    matches: dict[str, str] = {}  # code -> why it matched
    for code, n in NTAS.items():
        parts = [_normalize(p) for p in re.split(r"[-()]", n["name"]) if p.strip()]
        if query == _normalize(n["name"]) or query in parts:
            matches.setdefault(code, "official NTA name")
        elif re.search(rf"\b{re.escape(query)}\b", _normalize(n["name"])):
            matches.setdefault(code, "part of the official NTA name")
    if not matches:
        names = {_normalize(n["name"]): code for code, n in NTAS.items()}
        names.update({_normalize(p): code for code, n in NTAS.items() for p in re.split(r"[-()]", n["name"]) if p.strip()})
        for close in difflib.get_close_matches(query, names, n=5, cutoff=0.75):
            matches.setdefault(names[close], f"close spelling of '{close}'")
    return [{**nta(code), "match": why} for code, why in matches.items()]


# Words that don't tell two streets apart
STREET_WORDS = {"street", "st", "avenue", "ave", "av", "road", "rd", "place", "pl", "boulevard", "blvd",
                "east", "west", "north", "south", "e", "w", "n", "s", "the", "of", "new", "york", "ny", "nyc"}


def _street_words(text: str) -> set[str]:
    """'10 West 32nd Street, Manhattan' -> {'32'}: the words that name the street."""
    street = _normalize(text.split(",")[0])
    words = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", street).split()
    if words and re.fullmatch(r"[\d-]+", words[0]):
        words = words[1:]  # the house number
    return {w for w in words if w not in STREET_WORDS}


def neighborhood_at(address: str) -> dict:
    """The NTA a street address is in, with its tracts. Give a house number, street and borough,
    e.g. '10 West 32nd Street, Manhattan'. Intersections and place names don't geocode."""
    place = geosearch(address)
    # GeoSearch always returns its closest match, even for a street that doesn't exist:
    # reject a match on a different street or in a different borough.
    if not _street_words(address) & _street_words(place["label"]):
        raise LookupError(f"No address like {address!r}: the closest match was {place['label']}")
    named = [b for b in BOROUGH_CODES if _normalize(b) in _normalize(address)]
    if named and place["borough"] and named[0] != place["borough"]:
        raise LookupError(f"{address!r} matched {place['label']}, in {place['borough']}, not {named[0]}")
    codes = [code for code in NTAS if contains(code, place["lon"], place["lat"])]
    if not codes:
        raise LookupError(f"{place['label']} is not inside any NYC neighborhood (NTA)")
    return {**nta(codes[0]), "match": f"contains {place['label']}"}


# --- Addresses -> BBL, and tax photos ---


def geosearch(address: str) -> dict:
    """The best match for an NYC address: {label, borough, bbl, bin, lon, lat}."""
    body = _get_json(GEOSEARCH_URL, {"text": address, "size": 1})
    if not body.get("features"):
        raise LookupError(f"No NYC address matches {address!r}")
    feature = body["features"][0]
    pad = feature["properties"].get("addendum", {}).get("pad", {})
    lon, lat = feature["geometry"]["coordinates"]
    return {"label": feature["properties"]["label"], "borough": feature["properties"].get("borough"),
            "bbl": pad.get("bbl"), "bin": pad.get("bin"), "lon": lon, "lat": lat}


def _tax_photo(search_url: str) -> dict | None:
    """The first photo the archive's search finds for one lot, as {url, image, large, title}, or None."""
    try:
        response = httpx.get(search_url, headers=HEADERS, timeout=30, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        return None  # the link to the search still works for the reader
    match = TAX_RESULT.search(response.text)
    if not match:
        return None
    photo_id, title = match.groups()
    image, large = TAX_THUMB_URL.format(id=photo_id), TAX_THUMB_URL.format(id=photo_id) + "?size=large"
    try:
        # Some photos have no thumbnail (404): show the full scan instead
        if httpx.head(image, headers=HEADERS, timeout=15).status_code != 200:
            image = large = TAX_FILE_URL.format(id=photo_id)
    except httpx.HTTPError:
        image = large = TAX_FILE_URL.format(id=photo_id)
    return {"url": TAX_ITEM_URL.format(id=photo_id), "image": image, "large": large, "title": html.unescape(title)}


def tax_photo_links(address_or_bbl: str) -> dict:
    """The Municipal Archives' ~1940 and ~1985 tax photos of one tax lot. A 10-digit BBL
    (borough, 5-digit block, 4-digit lot) is used as is; anything else is looked up as an address.
    For each year: the photo's page and thumbnail if the archive has one (photo_1940, photo_1985,
    else None), and the archive's search for that lot (search_1940, search_1985).
    We link to the photos and show the archive's own thumbnails; we don't copy them."""
    bbl = address_or_bbl.strip()
    label = None
    if not re.fullmatch(r"[1-5]\d{9}", bbl):
        place = geosearch(address_or_bbl)
        if not place["bbl"]:
            raise LookupError(f"No tax lot (BBL) for {address_or_bbl!r}")
        bbl, label = place["bbl"], place["label"]
    borough, block, lot = bbl[0], bbl[1:6], bbl[6:]
    search_1940 = TAX_SEARCH_URL.format(query=f"nynyma_rec0040_{borough}_{block}_{lot}")
    search_1985 = TAX_SEARCH_URL.format(query=f"REC0041_{borough}_{block}_{lot}")
    return {
        "address": label,
        "bbl": bbl,
        "block": int(block),
        "lot": int(lot),
        "search_1940": search_1940,
        "search_1985": search_1985,
        "photo_1940": _tax_photo(search_1940),
        "photo_1985": _tax_photo(search_1985),
    }

if __name__ == "__main__":
    # Build the lookup file: uv run geo.py build
    # Smoke test:            uv run geo.py "Little Italy"
    import sys

    if sys.argv[1:] == ["build"]:
        build()
        sys.exit()
    assert NTAS, "data/ntas.json is missing: run `uv run geo.py build` first"
    name = sys.argv[1] if len(sys.argv) > 1 else "Lower East Side"
    candidates = resolve_neighborhood(name)
    assert candidates, f"no NTA for {name!r}"
    for c in candidates:
        print(c["code"], "|", c["name"], "|", c["borough"], "|", c["type"], "|", len(c["tracts"]), "tracts |", c["match"])
    assert [c["code"] for c in resolve_neighborhood("Little Italy")] == ["MN0201"]
    assert not resolve_neighborhood("Koreatown"), "informal names should not match: use neighborhood_at"
    assert neighborhood_at("10 West 32nd Street, Manhattan")["code"] == "MN0501"  # Koreatown
    assert neighborhood_at("2344 Arthur Avenue, Bronx")["code"] == "BX0603"  # the Bronx's Little Italy
    for bad in ("1 Fake Street, Manhattan", "100 Avenue A, Brooklyn"):
        try:
            neighborhood_at(bad)
            raise AssertionError(f"{bad!r} should not resolve")
        except LookupError as e:
            print("rejected:", e)
    assert contains("MN0302", -73.990251, 40.718545), "97 Orchard St should be in the Lower East Side"
    assert not contains("MN0302", -73.9857, 40.7484), "the Empire State Building is not in the Lower East Side"
    print(tax_photo_links("97 Orchard Street, Manhattan"))
