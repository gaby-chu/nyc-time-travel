"""Search the New York Public Library's Digital Collections: historic photos, maps and prints.

We return each item's title, date, collection, its public page on digitalcollections.nypl.org, and
a thumbnail URL on NYPL's image server. We link to the images; we never copy them. Only public-domain items are searched.
"""

import os
import re
import time

import httpx

SEARCH_URL = "https://api.repo.nypl.org/api/v2/items/search"
MODS_URL = "https://api.repo.nypl.org/api/v2/items/mods/{uuid}"
ITEM_PAGE = "https://digitalcollections.nypl.org/items/{uuid}"
# NYPL's image server: t=r is a ~300 px JPEG. The page shows it next to the item it links to.
THUMBNAIL = "https://images.nypl.org/index.php?id={image_id}&t=r"
PICTURE_TYPES = {"still image", "cartographic"}
HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
MAX_RESULTS = 5
# Search results have no dates, so we read each candidate's record and filter by year:
# look at this many candidates to find 5 in the years asked for.
MAX_CANDIDATES = 25

_cache: dict[str, dict] = {}


def _get_json(url: str, params: dict | None = None) -> dict:
    key = url + repr(sorted((params or {}).items()))
    if key in _cache:
        return _cache[key]
    if not os.environ.get("NYPL_API_KEY"):
        raise RuntimeError("Set NYPL_API_KEY in this project's .env file.")
    headers = {**HEADERS, "Authorization": f'Token token="{os.environ["NYPL_API_KEY"]}"'}
    for attempt in range(3):
        response = httpx.get(url, params=params, headers=headers, timeout=30)
        if response.status_code < 500 or attempt == 2:
            break
        time.sleep(2 ** attempt)
    response.raise_for_status()
    _cache[key] = response.json()["nyplAPI"]["response"]
    return _cache[key]


def _text(value) -> str:
    """MODS values are {"$": text}, a list of those, or nested further."""
    if isinstance(value, dict):
        return value.get("$", "")
    if isinstance(value, list):
        return "; ".join(t for t in (_text(v) for v in value) if t)
    return str(value or "")


def _year_range(origin) -> tuple[int | None, int | None]:
    """The earliest and latest four-digit years in a MODS originInfo, e.g. 1938-05-03 -> (1938, 1938)."""
    years = [int(y) for y in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", repr(origin))]
    return (min(years), max(years)) if years else (None, None)


def _collection(related) -> str:
    """The outermost collection an item belongs to: MODS relatedItem hosts nest inside each other."""
    title = ""
    while isinstance(related, (dict, list)):
        related = related[0] if isinstance(related, list) and related else related
        if not isinstance(related, dict) or related.get("type") != "host":
            break
        title = _text((related.get("titleInfo") or {}).get("title")) or title
        related = related.get("relatedItem")
    return title


def _details(uuid: str) -> dict:
    mods = _get_json(MODS_URL.format(uuid=uuid)).get("mods", {})
    start, end = _year_range(mods.get("originInfo"))
    subjects = mods.get("subject") or []
    places: list[str] = []  # the item's place subjects, most specific last, without repeats
    for s in subjects if isinstance(subjects, list) else [subjects]:
        if isinstance(s, dict) and s.get("geographic"):
            for place in _text(s["geographic"]).split("; "):
                if place and place not in places:
                    places.append(place)
    return {"start": start, "end": end, "collection": _collection(mods.get("relatedItem")), "places": places}


def search(query: str, start_year: int | None = None, end_year: int | None = None) -> list[dict]:
    """Up to 5 public-domain items matching query, as {title, date, type, collection, places, url,
    thumbnail} (thumbnail only for photos and maps).
    With years, only items dated in that range (undated items are left out)."""
    found = _get_json(SEARCH_URL, {"q": query, "publicDomainOnly": "true", "per_page": MAX_CANDIDATES})
    results = found.get("result") or []
    if isinstance(results, dict):  # a single result comes back as an object, not a list
        results = [results]
    items, seen = [], set()
    for r in results:
        # The same photo often has several captures (front, back, crops) with one title: keep the first
        if r.get("title") in seen:
            continue
        details = _details(r["uuid"])
        if start_year or end_year:
            if details["start"] is None:
                continue
            if (end_year and details["start"] > end_year) or (start_year and details["end"] < start_year):
                continue
        date = "undated" if details["start"] is None else (
            str(details["start"]) if details["start"] == details["end"] else f"{details['start']}-{details['end']}")
        seen.add(r.get("title"))
        items.append({"title": r.get("title", ""), "date": date, "type": r.get("typeOfResource", ""),
                      "collection": details["collection"], "places": details["places"],
                      "url": ITEM_PAGE.format(uuid=r["uuid"]),
                      # Only photos and maps: a "text" item's image is a catalog card or a document page
                      "thumbnail": THUMBNAIL.format(image_id=r["imageID"])
                      if r.get("imageID") and r.get("typeOfResource") in PICTURE_TYPES else None})
        if len(items) == MAX_RESULTS:
            break
    return items


def to_text(items: list[dict]) -> str:
    if not items:
        return "No items found."
    return "\n\n".join(
        f"## {i['title']}\nDate: {i['date']}\nType: {i['type']}\nCollection: {i['collection'] or 'unknown'}\n"
        + (f"Places: {', '.join(i['places'])}\n" if i["places"] else "")
        + f"Source: {i['url']}"
        for i in items)


if __name__ == "__main__":
    # Smoke test: uv run nypl.py "Orchard Street" 1930 1945
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    args = sys.argv[1:] or ["Orchard Street", "1930", "1945"]
    start, end = (int(args[1]), int(args[2])) if len(args) > 2 else (None, None)
    found = search(args[0], start, end)
    assert found, "no items"
    if start:
        assert all(i["date"] != "undated" for i in found), "an undated item passed the year filter"
    print(to_text(found))
