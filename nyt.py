"""Search The New York Times archive (September 1851 to today) through the NYT Article Search API.

It returns each article's headline, abstract and snippet, its date and its nytimes.com URL. It does
not return the full text, and many archive articles have only a headline. Quote only what it returns.
"""

import os
import threading
import time

import httpx

SEARCH_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
HEADERS = {"User-Agent": "nyc-time-travel/0.1 (Columbia IEOR 4570 class project)"}
MAX_RESULTS = 5
# The NYT asks for a 12-second pause between requests (5 a minute, 500 a day). Researchers run in parallel
# threads and share this key, so every request waits its turn here: one every 12 s across the whole process.
MIN_INTERVAL = 12.0

_lock = threading.Lock()
_last_request = [0.0]
_cache: dict[tuple, list[dict]] = {}


# When the key's daily quota is used up, every request fails until it resets: stop asking for a while,
# so researchers don't spend their time on retries that can't work.
QUOTA_PAUSE = 15 * 60
_quota_out_until = [0.0]


class QuotaExceeded(RuntimeError):
    pass


def _get(params: dict, deadline: float | None = None) -> dict:
    """deadline: a time.monotonic() after which the caller no longer wants the answer. A request that
    would have to wait in the queue past it is dropped without being sent, so it costs no quota."""
    if not os.environ.get("NYT_API_KEY"):
        raise RuntimeError("Set NYT_API_KEY in this project's .env file.")
    for attempt in range(2):
        if time.monotonic() < _quota_out_until[0]:
            raise QuotaExceeded("The NYT key's daily request limit is used up. Use other sources.")
        with _lock:
            wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
            if deadline is not None and time.monotonic() + max(wait, 0) > deadline:
                raise TimeoutError("the NYT queue is too long for the time you have left. Use other sources.")
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
            response = httpx.get(SEARCH_URL, params={**params, "api-key": os.environ["NYT_API_KEY"].strip()},
                                 headers=HEADERS, timeout=30)
        if response.status_code != 429:
            break
        # "QuotaViolation" is the daily limit; anything else is the per-minute one, worth one more try
        if "QuotaViolation" in response.text:
            _quota_out_until[0] = time.monotonic() + QUOTA_PAUSE
            raise QuotaExceeded("The NYT key's daily request limit is used up. Use other sources.")
        if attempt == 0:
            time.sleep(MIN_INTERVAL)
    response.raise_for_status()
    return response.json()


def search(query: str, start_year: int | None = None, end_year: int | None = None,
           place: str | None = None, deadline: float | None = None) -> list[dict]:
    """Up to 5 articles matching query, most relevant first, as {headline, date, abstract, snippet, places, url}.

    place: an NYT location tag, to keep only articles the Times tagged with that place. Tags start in
    the 1980s and their spelling changed: 'LOWER EAST SIDE (NYC)' for the 1980s-90s, 'Lower East Side
    (Manhattan, NY)' for recent years. Before the 1980s, leave place out and put the name in query.
    deadline: see _get.
    """
    key = (query, start_year, end_year, place)
    if key in _cache:
        return _cache[key]
    params = {"q": query, "sort": "relevance"}
    if start_year:
        params["begin_date"] = f"{start_year}0101"
    if end_year:
        params["end_date"] = f"{end_year}1231"
    if place:
        # The filter syntax changed in 2025: glocations:(...) now matches nothing.
        params["fq"] = f'timesTag.location:"{place}"'
    docs = (_get(params, deadline).get("response") or {}).get("docs") or []
    articles = [{
        "headline": (doc.get("headline") or {}).get("main", ""),
        "date": (doc.get("pub_date") or "")[:10],
        "abstract": doc.get("abstract") or "",
        "snippet": doc.get("snippet") if doc.get("snippet") != doc.get("abstract") else "",
        "places": [k["value"] for k in doc.get("keywords", []) if k.get("name") == "Location"],
        "url": doc.get("web_url", ""),
    } for doc in docs[:MAX_RESULTS]]
    _cache[key] = articles
    return articles


def to_text(articles: list[dict]) -> str:
    """Articles -> text the model can read, one block per article with its Source line."""
    if not articles:
        return "No articles found."
    blocks = []
    for a in articles:
        lines = [f"## {a['headline']}", f"Date: {a['date']}"]
        if a["abstract"]:
            lines.append(f"Abstract: {a['abstract']}")
        if a["snippet"]:
            lines.append(f"Snippet: {a['snippet']}")
        if not a["abstract"] and not a["snippet"]:
            lines.append("(The archive has only the headline for this article.)")
        if a["places"]:
            lines.append(f"Places: {', '.join(a['places'])}")
        lines.append(f"Source: {a['url']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


if __name__ == "__main__":
    # Smoke test: uv run nyt.py "Orchard Street pushcart" 1900 1920
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    args = sys.argv[1:] or ["pushcart market", "1900", "1920"]
    found = search(args[0], int(args[1]) if len(args) > 1 else None, int(args[2]) if len(args) > 2 else None)
    assert found, "no articles"
    print(to_text(found)[:1500])
    tagged = search("Chinese", 1990, 2025, place="Sunset Park (Brooklyn, NY)")
    assert tagged and all("Sunset Park (Brooklyn, NY)" in a["places"] for a in tagged), "place filter failed"
    print(f"\nPlace filter: {len(tagged)} articles tagged Sunset Park, e.g. {tagged[0]['date']} {tagged[0]['headline'][:70]}")
