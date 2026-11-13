"""Search and read historic newspapers in Chronicling America, through the loc.gov JSON API.

Since 2025 Chronicling America is only on loc.gov. A search returns newspaper pages; reading one
returns its OCR text, which is noisy. NYC coverage is mostly English-language dailies before 1923,
plus Yiddish dailies and the Daily Worker into the 1940s and 50s.
"""

import re
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

SEARCH_URL = "https://www.loc.gov/collections/chronicling-america/"
HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
MAX_RESULTS = 5
# Enough of a page to judge it. A whole newspaper page is often 50k+ characters of OCR.
MAX_CHARS = 10_000
SNIPPET_CHARS = 300
# Only NYC papers. The loc.gov facets are lowercase names.
NYC_FACET = "location_state:new york|location_city:new york"

_cache: dict[str, object] = {}


def _get_json(url: str, params: dict | None = None):
    if params:
        # Add to the URL's own query, don't replace it: httpx's params= would drop a page's ?sp=
        url += ("&" if "?" in url else "?") + urlencode(params)
    if url not in _cache:
        # Two tries of 20 s at most: a researcher has 90 s in all (RESEARCHER_SECONDS in app.py),
        # and a search that slow is better given up than waited on.
        for attempt in range(2):
            try:
                response = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
            except httpx.TransportError:
                # loc.gov sometimes drops the connection mid-response, or doesn't answer: try once more
                if attempt == 1:
                    raise
                time.sleep(3)
                continue
            # loc.gov rate-limits with 429 and has the odd 5xx: wait and try again
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == 1:
                break
            time.sleep(3)
        response.raise_for_status()
        _cache[url] = response.json()
    return _cache[url]


def _words(terms: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", terms.lower()) if len(w) > 2]


def _around(text: str, terms: str, size: int) -> str:
    """size characters of text, centered on where most of the terms appear close together."""
    if len(text) <= size:
        return text
    lower = text.lower()
    hits = sorted(m.start() for w in _words(terms) for m in re.finditer(re.escape(w), lower))
    if not hits:
        return text[:size]
    # The window of size characters that holds the most hits
    best, start = 0, hits[0]
    for i, hit in enumerate(hits):
        count = sum(1 for h in hits[i:] if h < hit + size)
        if count > best:
            best, start = count, hit
    start = max(0, start - 200)  # a little context before the first hit
    return ("..." if start else "") + text[start:start + size] + ("..." if start + size < len(text) else "")


def _page_url(url: str) -> str:
    """Drop the search-terms parameter, keeping the page (?sp=): one URL per page, to cite and cache."""
    parts = urlparse(url)
    query = {k: v for k, v in parse_qs(parts.query).items() if k != "q"}
    return urlunparse(parts._replace(scheme="https", query=urlencode(query, doseq=True)))


def _scan(result: dict, percent: str) -> str | None:
    """A scan of the page from loc.gov's image server, at percent of full size (6.25 is ~500 px wide)."""
    for url in result.get("image_url") or []:
        if "/image-services/iiif/" in url:
            return re.sub(r"/full/pct:[\d.]+/", f"/full/pct:{percent}/", url.split("#")[0])
    return None


def search(terms: str, start_year: int, end_year: int) -> list[dict]:
    """Up to 5 NYC newspaper pages matching terms, as {paper, date, language, snippet, url, image, large}
    (image and large are scans of the page, for the web page to show; the model doesn't need them)."""
    body = _get_json(SEARCH_URL, {
        "q": terms,
        "dates": f"{start_year}/{end_year}",
        "fa": NYC_FACET,
        "fo": "json",
        "c": MAX_RESULTS,
        "at": "results,pagination",
    })
    pages = []
    for r in body.get("results", [])[:MAX_RESULTS]:
        pages.append({
            "paper": (r.get("partof_title") or [r.get("title", "")])[0],
            "date": r.get("date", ""),
            "language": ", ".join(r.get("language") or []),
            "snippet": _snippet(r, terms),
            "url": _page_url(r["url"]),
            "image": _scan(r, "6.25"),
            "large": _scan(r, "12.5"),
        })
    return pages


def _snippet(result: dict, terms: str) -> str:
    """The passage that matched. The result's description is only the top of the page, so ask the
    word-coordinates service for the relevant snippet, and fall back to the description."""
    try:
        if result.get("word_coordinates_url"):
            body = _get_json(result["word_coordinates_url"])
            snippet = " ".join(v.get("relevant_snippet", "") for v in body.values() if isinstance(v, dict))
            snippet = snippet.replace("[[tag]]", "").replace("[[/tag]]", "").strip()
            if snippet:
                return snippet[:SNIPPET_CHARS]
    except httpx.HTTPError:
        pass
    return _around(" ".join(result.get("description") or []), terms, SNIPPET_CHARS)


def read_page(url: str, terms: str = "") -> dict:
    """The OCR text of one newspaper page, as {paper, date, url, text}, trimmed around terms."""
    url = _page_url(url)
    if "loc.gov/resource/" not in url:
        raise ValueError(f"Not a Chronicling America page URL: {url}")
    page = _get_json(url, {"fo": "json"})
    fulltext_url = (page.get("resource") or {}).get("fulltext_file")
    if not fulltext_url:
        raise LookupError(f"No OCR text for {url}")
    # {segment path: {"full_text": "..."}}
    text = " ".join(v.get("full_text", "") for v in _get_json(fulltext_url).values() if isinstance(v, dict))
    text = re.sub(r"[ \t]+", " ", text).strip()
    item = page.get("item") or {}
    trimmed = _around(text, terms, MAX_CHARS) if terms else text[:MAX_CHARS]
    if len(trimmed) < len(text):
        trimmed += f"\n\n[Page truncated: {MAX_CHARS:,} of {len(text):,} characters shown.]"
    return {
        "paper": (item.get("partof_title") or [item.get("title", "")])[0] if item else "",
        "date": item.get("date", ""),
        "url": url,
        "text": trimmed,
    }


def search_to_text(pages: list[dict]) -> str:
    if not pages:
        return "No newspaper pages found."
    return "\n\n".join(
        f"## {p['paper']}, {p['date']} ({p['language']})\nSnippet (OCR, noisy): {p['snippet']}\nSource: {p['url']}"
        for p in pages)


def page_to_text(page: dict) -> str:
    return f"# {page['paper']}, {page['date']}\nSource: {page['url']}\n\nOCR text (noisy):\n{page['text']}"


if __name__ == "__main__":
    # Smoke test: uv run loc.py "Orchard Street pushcart" 1900 1920
    import sys

    args = sys.argv[1:] or ["Orchard Street pushcart", "1900", "1920"]
    terms, start, end = args[0], int(args[1]) if len(args) > 1 else 1900, int(args[2]) if len(args) > 2 else 1920
    found = search(terms, start, end)
    assert found, "no pages"
    assert all(start <= int(p["date"][:4]) <= end for p in found), "a page outside the years"
    print(search_to_text(found)[:1200])
    page = read_page(found[0]["url"], terms)
    assert page["text"], "empty page"
    print("\n" + page_to_text(page)[:800])
