"""The citation check: no model, just the report's text and the URLs the tools returned.

It splits a markdown report into claims (table rows, bullets, sentences), and finds:
  - uncited claims: a factual claim with no link;
  - unfetched links: a link to a URL no tool returned in this run (an invented or mangled URL).
It then marks the claims that still fail after the Writer's revision as "(unverified)".
It checks that sources exist, not that they say what the claim says.
"""

import re
from dataclasses import dataclass

# A URL may hold one level of balanced parentheses: the Census API's ...?get=group(B05006)&...
URL = r"https?://(?:[^\s()<>\"']|\([^\s()<>\"']*\))+"
LINK = re.compile(r"\[([^\]]*)\]\((" + URL + r")\)")
# Sections that report what the sources don't say: their sentences needn't cite anything
GAP_SECTION = re.compile(r"don.?t show|do not show|gaps|not found", re.I)
UNVERIFIED = " (unverified)"
ABBREVIATION = re.compile(r"\b(St|Ste|Ave|Av|Mt|Ft|No|Nos|Dr|Mr|Mrs|Ms|Rev|Gen|Jr|Sr|Co|Inc|Bros|c|ca|vs|"
                          r"[A-Z])\.$")


@dataclass
class Claim:
    text: str  # the claim as it appears in the report
    kind: str  # "row", "bullet" or "sentence"
    section: str  # the heading it's under
    links: list[str]  # the URLs it cites

    @property
    def needs_citation(self) -> bool:
        if GAP_SECTION.search(self.section):
            return False
        plain = LINK.sub("", self.text).strip()
        # A lead-in ("These buildings survive:") or a scrap isn't a factual claim
        return not plain.endswith(":") and len(plain) >= 40


def clean_url(url: str) -> str:
    return url.rstrip(".,;:")


def _sentences(paragraph: str) -> list[str]:
    """Split a paragraph into sentences without breaking inside a link (URLs are full of dots)."""
    links: list[str] = []

    def hide(m):
        links.append(m.group(0))
        return f"\x00{len(links) - 1}\x00"

    masked = LINK.sub(hide, paragraph)
    parts: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[\"*])", masked):
        # "St. Mark's Place", "No. 44 Hester St.", "c. 1840": an abbreviation, not a sentence's end
        if parts and ABBREVIATION.search(parts[-1]):
            parts[-1] += " " + part
        else:
            parts.append(part)
    return [re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], p).strip() for p in parts if p.strip()]


def claims(report: str) -> list[Claim]:
    lines = report.splitlines()
    found, section = [], ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or set(stripped) <= set("-*_ "):
            continue
        if stripped.startswith("#"):
            section = stripped.lstrip("# ").strip()
            continue
        if stripped.startswith("|"):
            is_separator = set(stripped) <= set("|-: ")
            is_header = i + 1 < len(lines) and set(lines[i + 1].strip()) <= set("|-: ") and lines[i + 1].strip()
            if not is_separator and not is_header:
                found.append(Claim(stripped, "row", section, [clean_url(u) for _, u in LINK.findall(stripped)]))
            continue
        if re.match(r"([-*+]|\d+\.)\s", stripped):
            found.append(Claim(stripped, "bullet", section, [clean_url(u) for _, u in LINK.findall(stripped)]))
            continue
        for sentence in _sentences(stripped):
            found.append(Claim(sentence, "sentence", section, [clean_url(u) for _, u in LINK.findall(sentence)]))
    return found


def code_check(report: str, fetched: set[str]) -> dict:
    """Returns {"claims", "uncited", "unfetched", "pairs"}: every claim, the claims with no link,
    the (claim, url) pairs whose URL no tool returned, and the pairs whose URL a tool did return."""
    all_claims = claims(report)
    uncited = [c for c in all_claims if c.needs_citation and not c.links]
    unfetched, pairs = [], []
    for c in all_claims:
        for url in dict.fromkeys(c.links):  # each URL once per claim, in order
            (pairs if url in fetched else unfetched).append((c, url))
    return {"claims": all_claims, "uncited": uncited, "unfetched": unfetched, "pairs": pairs}


def mark_unverified(report: str, failing: list[Claim]) -> str:
    """Add "(unverified)" to each failing claim: inside the last cell of a table row, else at the end."""
    for c in failing:
        if UNVERIFIED.strip() in c.text:
            continue
        if c.kind == "row" and c.text.rstrip().endswith("|"):
            marked = c.text.rstrip()[:-1].rstrip() + UNVERIFIED + " |"
        else:
            marked = c.text + UNVERIFIED
        report = report.replace(c.text, marked, 1)
    return report


if __name__ == "__main__":
    # Self-check: uv run checker.py
    census = "https://api.census.gov/data/2024/acs/acs5?get=group(B05006)&for=tract:000202&in=state:36%20county:061"
    nyt = "https://www.nytimes.com/1986/05/10/nyregion/new-asian-immigrants-new-garment-center.html"
    fetched = {census, nyt}
    report = f"""Chinese immigrants were the largest foreign-born group in 2020-2024 ([ACS 2020-2024]({census})). Garment shops shifted to Chinese owners by 1986 ([NYT, 1986]({nyt})).

### Who settled, and when

| Group | Arrived | Peak | Declined/moved | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| Chinese | 1960s (approximate) | 2000 (documented) | not found | Census figures ([Census]({census})) |
| Eastern European Jews | 1880s | 1900-1920 | 1940 | Press accounts document a large Jewish presence ([New-York Tribune, 1904](https://chroniclingamerica.loc.gov/)) |
| Italians | 1880s | 1900-1920 | 1950s | Italian families lived on Mulberry Street in great numbers |

These buildings survive:

- The Ottendorfer Library at 135 Second Avenue was built in 1883-84 ([LPC](https://s-media.nyc.gov/agencies/lpc/lp/924.pdf)).

### What the records don't show

No source gives population counts for the 1960s.
"""
    result = code_check(report, fetched)
    kinds = [c.kind for c in result["claims"]]
    assert kinds == ["sentence", "sentence", "row", "row", "row", "sentence", "bullet", "sentence"], kinds
    # The census URL survives its parentheses
    assert result["claims"][0].links == [census], result["claims"][0].links
    # The uncited row is caught; the lead-in and the gaps section are not flagged
    assert [c.text[:12] for c in result["uncited"]] == ["| Italians |"], [c.text for c in result["uncited"]]
    # The invented home-page link and the unread LPC report are caught as unfetched
    assert sorted(u for _, u in result["unfetched"]) == ["https://chroniclingamerica.loc.gov/",
                                                          "https://s-media.nyc.gov/agencies/lpc/lp/924.pdf"]
    assert len(result["pairs"]) == 3  # census twice (sentence, row), nyt once
    marked = mark_unverified(report, [c for c, _ in result["unfetched"]] + result["uncited"])
    assert "| 1940 | Press accounts document a large Jewish presence ([New-York Tribune, 1904](https://chroniclingamerica.loc.gov/)) (unverified) |" in marked
    assert "in great numbers (unverified) |" in marked
    assert "1883-84 ([LPC](https://s-media.nyc.gov/agencies/lpc/lp/924.pdf)). (unverified)" in marked
    print("ok")
