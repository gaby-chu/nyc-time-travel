import asyncio
import concurrent.futures
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import uvicorn
from agents import Agent, ModelSettings, RunContextWrapper, Runner, function_tool, set_tracing_disabled
from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import census
import checker
import geo
import loc
import lpc
import nypl
import nyt
from context_panel import AgentContexts, PanelHooks, add_context_panel

# CENSUS_API_KEY, NYT_API_KEY and NYPL_API_KEY come from the .env file next to this one.
load_dotenv(Path(__file__).parent / ".env")

# Traces upload to OpenAI by default, which needs an OpenAI key. We're on Gemini.
set_tracing_disabled(True)

# LiteLLM routes the call to Gemini. api_key is unused: Vertex AI uses your gcloud credentials.
MODEL = LitellmModel(model="vertex_ai/gemini-3.5-flash", api_key="unused")
# Researchers only read and take notes: the cheaper model is enough.
RESEARCHER_MODEL = LitellmModel(model="vertex_ai/gemini-3.5-flash-lite", api_key="unused")
# A stalled model call would hang the page: give up after 90 s, and retry twice.
SETTINGS = ModelSettings(extra_args={"vertex_location": "global", "timeout": 90, "num_retries": 2})
# The Writer writes the whole report in one reply, which can take 2 to 3 minutes: 90 s cut it off mid-report.
WRITER_SETTINGS = ModelSettings(extra_args={"vertex_location": "global", "timeout": 240, "num_retries": 1})

# The Lead gets this many researchers in all, over at most this many rounds (the first, then two
# rounds for gaps), and each researcher reads at most MAX_READS pages or reports.
# Prompts ask for restraint; code enforces it.
MAX_RESEARCHERS = 10
MAX_ROUNDS = 3
MAX_READS = 5
# Each researcher gets at most this many searches of each slow source: loc.gov takes ~30 s a search,
# and NYT requests queue 12 s apart on one shared key, so one researcher's extra searches hold up the round.
MAX_SEARCHES = 3
# Each researcher gets this long. After it, every tool answers "time's up" and the researcher reports what
# it has. The Lead waits for the slowest researcher in a round, so one stuck on a slow archive held up the
# whole round (a 10-minute run became about 5).
RESEARCHER_SECONDS = 90
# The whole answer has to arrive within 5 minutes (graders wait that long). Research stops RESEARCH_SECONDS
# into the run, leaving the Writer ~50-100 s and usually time for one revision; a researcher gets 90 s or what's left of that, whichever is
# less, and no new round starts with under MIN_ROUND_SECONDS left. The citation revision (~40 s) runs only
# if it still fits in RUN_SECONDS; otherwise failing claims are marked "(unverified)" straight away.
RUN_SECONDS = 285
RESEARCH_SECONDS = 170
MIN_ROUND_SECONDS = 40
REVISION_SECONDS = 45
# Chronicling America has no NYC pages after 1954 (checked: 208 pages in 1953-54, none from 1955 on)
LAST_OLD_NEWSPAPER_YEAR = 1954

# The era anchors, and the years a researcher searches for each
ERAS = {"1900-1920": (1900, 1920), "1940": (1935, 1945), "1960": (1955, 1965),
        "1980": (1975, 1990), "today": (2000, 2026)}
QUESTION_TYPES = {"then_now": "Then & now", "settlement": "Who settled, and when", "remains": "What remains"}


@dataclass
class Research:
    """One run's state, shared by every agent and tool in it. The model never sees it."""

    hooks: PanelHooks
    nta: dict | None = None  # {"code", "name", "borough", "tracts", ...}
    question_types: list[str] = field(default_factory=list)  # some of then_now / settlement / remains
    eras: list[str] = field(default_factory=lambda: list(ERAS))
    researchers: int = 0  # how many researchers have started, to number them
    rounds: int = 0  # how many Lead turns have sent researchers
    lead_turns: int = 0  # how many times the Lead has called the model
    round_turn: int = -1  # the Lead turn the latest round started in
    reads: dict[str, int] = field(default_factory=dict)  # researcher -> pages and reports read
    searches: dict[str, int] = field(default_factory=dict)  # "researcher:tool" -> searches made
    deadlines: dict[str, float] = field(default_factory=dict)  # researcher -> time.monotonic() its time runs out
    run_started: float = field(default_factory=time.monotonic)

    def elapsed(self) -> float:
        return time.monotonic() - self.run_started

    def research_time_left(self) -> float:
        return RESEARCH_SECONDS - self.elapsed()
    findings: list[str] = field(default_factory=list)  # what each researcher reported, for the Writer
    plan: list[dict] = field(default_factory=list)
    timeline: dict = field(default_factory=dict)  # {"groups": [...], "eras": [...]}
    timelines: list[dict] = field(default_factory=list)  # every saved timeline: before and after gap rounds
    fetched: set[str] = field(default_factory=set)  # every URL a tool returned, for the citation check
    thumbnails: dict[str, dict] = field(default_factory=dict)  # NYPL item, newspaper page or tax photo URL -> {image, large, kind, caption, date, credit?}, for the web page
    tool_calls: list[dict] = field(default_factory=list)  # every agent's tool calls, for /chat
    checks: list[dict] = field(default_factory=list)  # citation check counts: first check, after revision


class TraceHooks(PanelHooks):
    """PanelHooks, plus what this app needs to know: when the Lead starts a new turn (a research round
    is the research calls of one Lead turn), and every tool call, tagged with its agent, for /chat."""

    async def on_llm_end(self, context, agent, response):
        await super().on_llm_end(context, agent, response)
        if agent.name == "Lead":
            context.context.lead_turns += 1

    async def on_tool_end(self, context, agent, tool, result):
        arguments = getattr(context, "tool_arguments", None)
        try:
            arguments = json.loads(arguments) if arguments else {}
        except ValueError:
            pass
        text = str(result)
        context.context.tool_calls.append({"agent": agent.name, "name": tool.name, "args": arguments,
                                           "result": text if len(text) <= 2000 else text[:2000] + "..."})


# --- Tools ---

URL = re.compile(checker.URL)  # allows the Census API's ...get=group(B05006)... parentheses


def remember(ctx: RunContextWrapper[Research], text: str) -> str:
    """Note every URL in a tool's result, so the citation check can tell a cited URL from an
    invented one. Returns text unchanged."""
    ctx.context.fetched.update(checker.clean_url(url) for url in URL.findall(text))
    return text


def tool_error(ctx: RunContextWrapper, error: Exception) -> str:
    """When the model's arguments don't fit a tool (a list where the tool takes one string, a missing
    argument), the SDK would only say "An error occurred". Tell the model what was wrong, so it can
    call the tool again correctly."""
    message = redact(str(error))
    if message.startswith("Invalid JSON input"):
        # The SDK leaves out which argument failed. The usual cause: a list where one string belongs.
        message += (". Check the argument types: each text argument (terms, query, keyword, address) is "
                    "one string, e.g. 'German Baptist 14th Street', never a list; years are whole numbers.")
    return json.dumps({"error": f"Bad arguments: {message[:500]}"})


# An HTTP error's message includes the request URL, and the NYT and Census keys are URL parameters.
# Error text goes to the model, the page and /chat, so take the keys out first.
SECRET_PARAM = re.compile(r"((?:api[-_]?)?key|token)=[^&\s'\"]+", re.IGNORECASE)


def redact(text: str) -> str:
    for name, value in os.environ.items():
        if value and len(value) >= 8 and any(w in name.upper() for w in ("KEY", "TOKEN", "SECRET")):
            text = text.replace(value, "***")
    return SECRET_PARAM.sub(r"\1=***", text)


def error_text(e: Exception, limit: int = 300) -> str:
    return f"{type(e).__name__}: {redact(str(e))[:limit]}"


def plain_error(e: Exception) -> str:
    """What went wrong, in a sentence the model can act on: no URLs, stack details or keys."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 429:
            return "the source is getting too many requests right now. Use another source."
        if code in (401, 403):
            return "the source refused the request (access denied). Use another source."
        if code == 404:
            return "that page or item doesn't exist. Check the link came from a search result."
        if code >= 500:
            return f"the source is having trouble (error {code}). Try once more later, or use another source."
        return f"the source rejected the request (error {code}). Check the arguments."
    if isinstance(e, httpx.TimeoutException):
        return "the source didn't answer in time. Use another source or other search words."
    if isinstance(e, httpx.TransportError):
        return "couldn't reach the source. Use another source."
    if isinstance(e, (KeyError, IndexError)):
        return "the source's answer wasn't in the expected shape. Use another source."
    if isinstance(e, json.JSONDecodeError):
        return "the source sent back something that isn't data (it may be down). Use another source."
    if isinstance(e, (TimeoutError, LookupError, ValueError, RuntimeError)):
        # Our own messages (out of time, NYT quota, no such address, bad year): already plain
        return redact(str(e))[:300]
    return f"something went wrong ({type(e).__name__}). Use another source."


def failed(what: str, e: Exception) -> str:
    # The model cannot see an exception. Return something it can reason about.
    return json.dumps({"error": f"{what} failed: {plain_error(e)}"})


def out_of_time(ctx: RunContextWrapper[Research]) -> str | None:
    """A refusal once the calling researcher has used its RESEARCHER_SECONDS, else None."""
    agent = getattr(ctx, "agent", None)
    deadline = ctx.context.deadlines.get(agent.name) if agent else None
    if deadline is None or time.monotonic() < deadline:
        return None
    return "Time's up: no more searches or reads. Reply with your findings now, from what you already have."


_archive_pool = concurrent.futures.ThreadPoolExecutor(max_workers=32)


def deadline_of(ctx: RunContextWrapper[Research]) -> float | None:
    """The calling researcher's deadline (time.monotonic()), or None if it isn't a researcher."""
    agent = getattr(ctx, "agent", None)
    return ctx.context.deadlines.get(agent.name) if agent else None


def budgeted(ctx: RunContextWrapper[Research], fn, *args):
    """fn(*args), but give up when the calling researcher's time runs out: a slow archive call already
    in progress would otherwise hold up the whole round. The abandoned call finishes in the background."""
    agent = getattr(ctx, "agent", None)
    deadline = ctx.context.deadlines.get(agent.name) if agent else None
    if deadline is None:  # not a researcher: no limit
        return fn(*args)
    left = max(deadline - time.monotonic(), 0) + 5
    try:
        return _archive_pool.submit(fn, *args).result(timeout=left)
    except concurrent.futures.TimeoutError:
        raise TimeoutError("this source was too slow and your time ran out. Reply with your findings now.") from None


def read_allowed(ctx: RunContextWrapper[Research]) -> str | None:
    """Count one read for the calling researcher. Returns a refusal once it has read MAX_READS or is out of time."""
    if late := out_of_time(ctx):
        return late
    agent = getattr(ctx, "agent", None)
    name = agent.name if agent else "unknown"
    if ctx.context.reads.get(name, 0) >= MAX_READS:
        return f"You've read {MAX_READS} items, the most allowed. Reply with your findings now."
    ctx.context.reads[name] = ctx.context.reads.get(name, 0) + 1
    return None


def search_allowed(ctx: RunContextWrapper[Research], tool: str) -> str | None:
    """Count one search of a slow source for the calling researcher. Returns a refusal past MAX_SEARCHES or out of time."""
    if late := out_of_time(ctx):
        return late
    agent = getattr(ctx, "agent", None)
    key = f"{agent.name if agent else 'unknown'}:{tool}"
    if ctx.context.searches.get(key, 0) >= MAX_SEARCHES:
        return f"You've made {MAX_SEARCHES} {tool} searches, the most allowed. Use another source or reply with your findings."
    ctx.context.searches[key] = ctx.context.searches.get(key, 0) + 1
    return None


YEAR = re.compile(r"\b(1[89]\d\d|20[0-2]\d)s?\b")


def without_years(query: str) -> tuple[str, str]:
    """Take years out of search words: "Little Italy 1960" matches any article that mentions 1960.
    The prompt says so, but models do it anyway. Returns (query, a note for the model, or "")."""
    cleaned = " ".join(YEAR.sub(" ", query).split())
    if not cleaned or cleaned == query:
        return query, ""
    return cleaned, f"(Years were taken out of your search words: '{cleaned}'. Use start_year and end_year.)\n\n"


@function_tool(failure_error_function=tool_error)
def census_profile(ctx: RunContextWrapper[Research], nta_code: str, year: int, topic: str) -> str:
    """Census figures for one neighborhood and year: the largest groups, with margins of error.
    Use it for numbers: who lives here today ('2024') and how that changed since 2000, for the
    "today" era and the settlement table. Only 2000 and 2010-2024 exist ('2024' is the ACS 2020-2024
    average). Nothing before 2000: for earlier eras, use the newspapers and landmark reports.

    Args:
        nta_code: The neighborhood's NTA code, e.g. 'MN0302'.
        year: 2000, or an ACS year from 2010 to 2024.
        topic: 'birthplace' (country of birth of the foreign-born), 'ancestry', or 'language'
            (spoken at home; not available for 2000).
    """
    if late := out_of_time(ctx):
        return late
    try:
        return remember(ctx, census.to_text(budgeted(ctx, census.profile, nta_code, year, topic)))
    except Exception as e:
        return failed(f"Census {topic} {year} for {nta_code}", e)


@function_tool(failure_error_function=tool_error)
def search_old_newspapers(ctx: RunContextWrapper[Research], terms: str, start_year: int, end_year: int) -> str:
    """Search NYC newspaper pages in Chronicling America (Library of Congress), 1900 to 1954 only:
    rich before 1923, thin after (some Yiddish dailies and the Daily Worker). Use it first for the
    1900-1920 era, and for 1940: eyewitness descriptions of streets, markets, churches, societies and
    events. Nothing from 1955 on: use search_nyt. Returns up to 5 pages with a matched snippet. Each search takes about 30 seconds,
    and you get 3 (MAX_SEARCHES): make each count.

    Args:
        terms: 2 or 3 words, e.g. 'Hester Street pushcart'. No years: use start_year and end_year.
        start_year: First year to search.
        end_year: Last year to search.
    """
    if start_year > LAST_OLD_NEWSPAPER_YEAR:
        # Answer at once instead of spending 30 s on a search that can only come back empty
        return (f"Chronicling America has no NYC pages after {LAST_OLD_NEWSPAPER_YEAR}. "
                "Use search_nyt, search_nypl or search_landmarks for this era.")
    if refusal := search_allowed(ctx, "search_old_newspapers"):
        return refusal
    terms, note = without_years(terms)
    try:
        end = min(end_year, LAST_OLD_NEWSPAPER_YEAR)
        pages = budgeted(ctx, loc.search, terms, start_year, end)
        # The page shows a scan of each newspaper page next to the era it's from
        ctx.context.thumbnails.update({p["url"]: {"image": p["image"], "large": p["large"], "kind": "page",
                                                  "caption": f"{p['paper']}, {p['date']}", "date": p["date"]}
                                       for p in pages if p["image"]})
        return remember(ctx, note + loc.search_to_text(pages))
    except Exception as e:
        return failed(f"Searching newspapers for {terms!r}", e)


@function_tool(failure_error_function=tool_error)
def read_old_newspaper_page(ctx: RunContextWrapper[Research], url: str, terms: str) -> str:
    """Read the OCR text of one newspaper page from search_old_newspapers, around your terms.
    Use it when a search snippet looks relevant: snippets are a line or two, and the page has the
    details. The OCR is noisy. Counts toward your 5 reads.

    Args:
        url: The page's Source URL from search_old_newspapers.
        terms: The words to center the text on, e.g. 'Hester Street pushcart'.
    """
    if refusal := read_allowed(ctx):
        return refusal
    try:
        return remember(ctx, loc.page_to_text(budgeted(ctx, loc.read_page, url, terms)))
    except Exception as e:
        return failed(f"Reading {url}", e)


@function_tool(failure_error_function=tool_error)
def search_nyt(ctx: RunContextWrapper[Research], query: str, start_year: int, end_year: int,
               place: str | None = None) -> str:
    """Search The New York Times archive (1851 to today). Use it for the 1960, 1980 and today eras,
    which have no old newspapers, and for when a group arrived or an institution opened or closed.
    Returns up to 5 articles: headline, date, abstract or snippet (many old articles have only a
    headline), and URL. Not the full text. You get 3 searches (MAX_SEARCHES), and they queue on a
    shared key: make each count.

    Args:
        query: 2 to 4 words, e.g. 'Lower East Side Puerto Rican'. No years: a year in the query
            matches any article that mentions it. Use start_year and end_year.
        start_year: First year to search.
        end_year: Last year to search.
        place: Optional NYT place tag for your own neighborhood, only for 1981 on. The NYT spells it
            'NAME (NYC)' in the 1980s-90s and 'Name (Borough, NY)' in recent years, e.g. 'EAST
            VILLAGE (NYC)' or 'East Village (Manhattan, NY)'. Never use another neighborhood's tag.
            If the tag finds nothing, the search is retried without it.
    """
    note = ""
    if place and end_year < 1981:
        # Nothing before 1981 has place tags: the filter would only return "No articles found."
        place, note = None, "(The place filter only works from 1981 on, so it was left out.)\n\n"
    if refusal := search_allowed(ctx, "search_nyt"):
        return refusal
    query, years_note = without_years(query)
    note += years_note
    try:
        articles = budgeted(ctx, nyt.search, query, start_year, end_year, place, deadline_of(ctx))
        if not articles and place:
            # A tag the NYT doesn't use finds nothing: try the words alone
            articles = budgeted(ctx, nyt.search, query, start_year, end_year, None, deadline_of(ctx))
            note += f"(No articles have the place tag {place!r}, so this searched without it.)\n\n"
        return remember(ctx, note + nyt.to_text(articles))
    except Exception as e:
        return failed(f"Searching the NYT for {query!r}", e)


@function_tool(failure_error_function=tool_error)
def search_nypl(ctx: RunContextWrapper[Research], query: str, start_year: int | None = None,
                end_year: int | None = None) -> str:
    """Search the New York Public Library's public-domain photos, maps and prints. Use it for what a
    place looked like (Then & now), mostly before 1950: the page shows each photo or map the report
    cites. Returns up to 5 items with title, date, collection and a link to the item's page.

    Args:
        query: A street or place name with its borough, e.g. 'Orchard Street Manhattan' or
            'Kensington Brooklyn': many NYC names (Kensington, Richmond, Jamaica) are also places
            elsewhere. Check each item's title and Places before using it.
        start_year: Optional first year: items dated earlier, or undated, are left out.
        end_year: Optional last year.
    """
    if late := out_of_time(ctx):
        return late
    query, note = without_years(query)
    try:
        items = budgeted(ctx, nypl.search, query, start_year, end_year)
        # The model doesn't need image URLs; the page shows each photo or map in the era it's from
        # (t=r is ~300 px; t=w, ~760 px, for the front page's lead picture)
        ctx.context.thumbnails.update({i["url"]: {"image": i["thumbnail"], "large": i["thumbnail"].replace("&t=r", "&t=w"),
                                                  "kind": "photo", "caption": f"{i['title']}, {i['date']}", "date": i["date"]}
                                       for i in items if i["thumbnail"]})
        return remember(ctx, note + nypl.to_text(items))
    except Exception as e:
        return failed(f"Searching NYPL for {query!r}", e)


@function_tool(failure_error_function=tool_error)
def search_landmarks(ctx: RunContextWrapper[Research], nta_code: str, keyword: str | None = None) -> str:
    """The designated landmarks and historic-district buildings in a neighborhood: names, dates built,
    original uses, notes, and links to designation reports. Use it for What remains (which buildings
    survive and who built them), and to find a report to read for any era. Only designated
    buildings are covered.

    Args:
        nta_code: The neighborhood's NTA code, e.g. 'MN0302'.
        keyword: Optional word to filter by, e.g. 'synagogue', 'church', 'German'.
    """
    if late := out_of_time(ctx):
        return late
    try:
        return remember(ctx, lpc.search_to_text(budgeted(ctx, lpc.search_landmarks, nta_code, keyword)))
    except Exception as e:
        return failed(f"Searching landmarks in {nta_code}", e)


@function_tool(failure_error_function=tool_error)
def read_landmark_report(ctx: RunContextWrapper[Research], url: str, terms: str) -> str:
    """Read a Landmarks Preservation Commission designation report (a PDF) around your terms, with
    page numbers. Use it for the history of who built and used a building, and for settlement
    history: historic-district reports often trace which groups lived in the area and when. Counts
    toward your 5 reads.

    Args:
        url: A report link from search_landmarks, e.g. 'https://s-media.nyc.gov/agencies/lpc/lp/1440.pdf'.
        terms: Words to find, e.g. 'German immigrants congregation'.
    """
    if refusal := read_allowed(ctx):
        return refusal
    try:
        return remember(ctx, lpc.report_to_text(budgeted(ctx, lpc.read_landmark_report, url, terms)))
    except Exception as e:
        return failed(f"Reading {url}", e)


@function_tool(failure_error_function=tool_error)
def tax_photo_links(ctx: RunContextWrapper[Research], address: str) -> str:
    """The city's tax photos of one building, taken about 1940 and about 1985: a link to each photo
    the archive has. Use it in the 1940 and 1980 eras for one or two addresses your other sources
    name, to show what the street looked like: the page shows each photo the report cites.

    Args:
        address: A street address with house number and borough, e.g. '97 Orchard Street, Manhattan'.
    """
    if late := out_of_time(ctx):
        return late
    try:
        links = budgeted(ctx, geo.tax_photo_links, address)
        place = links["address"] or address
        lines = [f"# Tax photos of {place} (block {links['block']}, lot {links['lot']})"]
        for year in ("1940", "1985"):
            photo = links[f"photo_{year}"]
            if photo:
                lines.append(f"About {year}: {photo['title']}: {photo['url']}")
                # The page shows the archive's thumbnail in the era that cites this link
                ctx.context.thumbnails[photo["url"]] = {
                    "image": photo["image"], "large": photo["large"], "kind": "photo", "date": year,
                    "caption": f"{photo['title']}, about {year} (city tax photo)", "credit": "NYC Municipal Archives"}
            else:
                lines.append(f"About {year}: no photo found for this lot. The archive's search: {links[f'search_{year}']}")
        return remember(ctx, "\n".join(lines))
    except Exception as e:
        return failed(f"Tax photos for {address!r}", e)


RESEARCH_TOOLS = [census_profile, search_old_newspapers, read_old_newspaper_page, search_nyt, search_nypl,
                  search_landmarks, read_landmark_report, tax_photo_links]


class PlanRow(BaseModel):
    question_type: str  # then_now, settlement or remains
    era: str  # one of the eras
    task: str  # what to find out


class GroupRow(BaseModel):
    group: str  # e.g. 'Italian', 'Chinese', 'Puerto Rican'
    arrived: str  # e.g. '1880s', or 'not found'
    peak: str
    declined_or_moved: str
    evidence: str  # the findings behind the dates, each with its exact URL from the findings


class EraRow(BaseModel):
    era: str
    what_it_looked_like: str  # with links
    whats_happening: str  # with links


@function_tool(failure_error_function=tool_error)
def save_plan(ctx: RunContextWrapper[Research], rows: list[PlanRow]) -> str:
    """Save your research plan: one row per question type and era worth researching. Use it once,
    before sending any researchers.

    Args:
        rows: The plan's rows.
    """
    ctx.context.plan = [r.model_dump() for r in rows]
    return f"Saved a plan of {len(rows)} rows."


@function_tool(failure_error_function=tool_error)
def save_timeline(ctx: RunContextWrapper[Research], groups: list[GroupRow], eras: list[EraRow]) -> str:
    """Save the timeline you've built from the findings, replacing any saved before. Use it after each
    round of research, before deciding whether to send more: the writer writes the report from it.

    Args:
        groups: For each group: when it arrived, peaked, and declined or moved, and the evidence.
        eras: For each era: what the place looked like and what was happening. Empty if not asked.
    """
    ctx.context.timeline = {"groups": [g.model_dump() for g in groups], "eras": [e.model_dump() for e in eras],
                            "after_round": ctx.context.rounds}
    ctx.context.timelines.append(ctx.context.timeline)
    return f"Saved a timeline of {len(groups)} groups and {len(eras)} eras."


# --- The clarifier: which neighborhood, which questions, and is it in scope ---


def nta_text(n: dict) -> str:
    return f"{n['code']}: {n['name']}, {n['borough']} ({n['type']}, {len(n['tracts'])} census tracts) — {n['match']}"


@function_tool(failure_error_function=tool_error)
def resolve_neighborhood(ctx: RunContextWrapper[Research], name: str) -> str:
    """Find NYC neighborhoods (official NTAs) by their official name, e.g. 'Lower East Side',
    'Sunset Park', 'Little Italy'. Informal names that aren't part of an official name won't match:
    use neighborhood_at with an address there instead.

    Args:
        name: A neighborhood name.
    """
    try:
        found = geo.resolve_neighborhood(name)
        return "\n".join(nta_text(n) for n in found) if found else f"No official NTA name matches {name!r}."
    except Exception as e:
        return failed(f"Looking up {name!r}", e)


@function_tool(failure_error_function=tool_error)
def neighborhood_at(ctx: RunContextWrapper[Research], address: str) -> str:
    """Find which NYC neighborhood (official NTA) a street address is in. Use it for informal names:
    pick an address you know is in the place, e.g. Koreatown -> '10 West 32nd Street, Manhattan'.
    Give a house number, street and borough. Intersections and place names don't work.

    Args:
        address: e.g. '150 Mulberry Street, Manhattan'.
    """
    try:
        return nta_text(geo.neighborhood_at(address))
    except Exception as e:
        return failed(f"Locating {address!r}", e)


class Clarify(BaseModel):
    ready: bool
    nta_code: str | None
    question_types: list[str]  # some of then_now / settlement / remains
    eras: list[str]  # some of the era anchors; empty means all
    group: str | None  # e.g. "Italian" if the user named one
    note: str | None  # for the writer, e.g. "Koreatown is a few blocks of this larger NTA"
    question: str | None  # asked when not ready
    options: list[str]  # candidate neighborhoods or questions, as the user would click them
    out_of_scope: bool


clarifier = Agent(
    name="Clarifier",
    instructions=f"""\
You decide whether a question about an NYC neighborhood's history is ready to research.

This app reconstructs, for one NYC neighborhood: what it looked like across eras (then_now), which
immigrant communities settled there and when (settlement), and what traces of them remain (remains).
Eras: {', '.join(ERAS)}.

1. Find the neighborhood with your tools. Never guess a code: use only codes a tool returned.
   - Official names: resolve_neighborhood.
   - Informal or historic names ("Koreatown", "Little Germany", "Five Points"): from what you know,
     pick a street address with a house number in each place the name could mean, and call
     neighborhood_at for each. E.g. "Little Italy" could mean Mulberry Street in Manhattan or
     Arthur Avenue in the Bronx: check both. "Chinatown" alone means three places, even though
     one official name matches it. Check these three addresses and ask which:
     '70 Mott Street, Manhattan', '5802 8th Avenue, Brooklyn' (Sunset Park), and
     '136-20 Roosevelt Avenue, Queens' (Flushing).
   - A street ("Hester Street", "Arthur Avenue"): check one address on it. Use the neighborhood
     the address is in, even if you expected another: today's official boundaries don't always
     follow historic names, and the writer can say so in note. At most 3 neighborhood_at calls for
     one place; if they land in different neighborhoods, ask which.
2. Ready when exactly one neighborhood fits and the question is in scope. Then set nta_code,
   question_types ("tell me the story" or a broad question means all three), eras (empty for
   all), and group if the user named one. If the place is a small part of a larger neighborhood
   (Koreatown in Midtown South), say so in note, so the writer can warn that census figures cover
   the whole area.
3. Not ready, so ask one short question and give options (2 to 5) the user can click, when:
   - no place is given ("Tell me about immigrants in NYC"): suggest neighborhoods;
   - the name fits more than one neighborhood, or the place spans several ("Little Italy",
     "the Village", "Sunset Park"): give one option per neighborhood, written as its official
     name and borough, like "Belmont, Bronx". No NTA codes in the question or options: users
     don't know them.
4. Out of scope (set out_of_scope, explain why politely in question, and suggest in-scope
   questions as options): places outside the five boroughs; rents, business turnover, storefronts
   or displacement economics; genealogy or any specific private person.

If you're given an earlier clarification and the user's answer, use the answer: a chosen option
names the neighborhood. Look it up with resolve_neighborhood to get its NTA code.""",
    model=MODEL,
    model_settings=SETTINGS,
    tools=[resolve_neighborhood, neighborhood_at],
    output_type=Clarify,
)


NTA_CODE = re.compile(r"\s*\((?:MN|BX|BK|QN|SI)\d{4}\)|\b(?:MN|BX|BK|QN|SI)\d{4}\b:?\s*")


def without_codes(text: str) -> str:
    """Take NTA codes ("Belmont, Bronx (BX0603)") out of what the user sees: they mean nothing to users."""
    return NTA_CODE.sub("", text).strip()


def check_clarify(c: Clarify, state: Research) -> Clarify:
    """Code, not the model, has the last word on the neighborhood: a 'ready' answer must name an NTA
    one of the Clarifier's tools returned in this run."""
    if not c.ready:
        return c
    # Each line of a lookup's result starts with an NTA code: "MN0302: Lower East Side, ..."
    returned = {line.split(":", 1)[0] for call in state.tool_calls if call["agent"] == "Clarifier"
                for line in call["result"].splitlines()}
    if c.nta_code not in geo.NTAS or c.nta_code not in returned:
        return c.model_copy(update={"ready": False, "question": "Which neighborhood do you mean?", "options": []})
    types = [t for t in c.question_types if t in QUESTION_TYPES] or list(QUESTION_TYPES)
    eras = [e for e in c.eras if e in ERAS] or list(ERAS)
    return c.model_copy(update={"question_types": types, "eras": eras})


# --- The researcher: one task, in one era, using the sources ---

researcher = Agent(
    name="Researcher",
    instructions=f"""\
You research one task about one NYC neighborhood in one era, using the tools you have.

1. Search first, then read the most relevant results. Read at most {MAX_READS} items in all.
   Snippets are short: when a search finds a relevant newspaper page or landmark report, read it.
   - Search with 2 or 3 words: street names, group names, institutions. Long queries find nothing.
   - Stay inside the neighborhood: a hit about a street in a nearby neighborhood isn't evidence.
   - Put years in start_year and end_year, never in the search words: "Little Italy 1960" finds
     articles that mention 1960, not ones about Little Italy then.
   - Search for what papers wrote about: streets, groups, churches, societies, events. Not
     "population" or "demographics": newspapers rarely use those words; census_profile has the numbers.
   - Which sources cover your era:
     1900-1920: old newspapers (the richest), the NYT, NYPL, landmark reports.
     1940: old newspapers (thinner), the NYT, NYPL, tax photos, landmark reports.
     1960 and 1980: the NYT, NYPL, landmark reports (and tax photos for 1980). No old newspapers.
     today: census_profile (2000, 2010-2024), the NYT, landmark reports.
   - search_old_newspapers and search_nyt are slow: {MAX_SEARCHES} searches of each at most.
   - You have about {RESEARCHER_SECONDS} seconds in all; then the tools stop answering. Start with
     the search most likely to answer your task, and call several tools at once when you can.
   By question type:
   - Who settled, and when: newspapers and the NYT for which groups lived there and their
     institutions (churches, synagogues, societies, newspapers); census_profile for 2000 on.
   - Then & now: search_nypl with the era's years for photos and maps of its streets (Type
     "still image" or "cartographic"; a "text" item is a document or catalog card and doesn't
     show what the place looked like); newspaper
     descriptions of streets, buildings and markets; for the 1940 and 1980 eras, tax_photo_links
     for one or two addresses your sources name (tax photos exist only for about 1940 and 1985).
     Describe what the place looked like: buildings, streets, markets, signs, how crowded.
     Give each photo or map of the place you found its own bullet (title, date, link), so the
     report can show it.
   - What remains: search_landmarks (with a keyword like 'church', 'synagogue' or a group name)
     and read_landmark_report for the one or two most relevant, for who built and used each
     building; the NYT with a recent place tag for institutions still there today. Say what
     survives and, where the sources say so, what was lost or changed use.
2. Reply with at most 8 bullets of facts that answer your task. End each bullet with its source
   link, copied exactly from a Source or Report line, and where possible a short exact quote
   (under 20 words) or the census figure with its year. A fact you can't link to a result you
   got is not a finding: leave it out. Only the last, "not found" bullet goes without a link.
3. Use only what the sources say, never outside knowledge. If the sources don't answer part of
   the task, say so in a last bullet, and name the searches you tried.
   Hints are search ideas, not facts, and can be wrong. Report a result only if it is about your
   neighborhood: drop one about a different neighborhood or street elsewhere, even if it matches
   your search words, and say in the last bullet which hints led elsewhere.
4. Historic sources may use slurs or stereotypes: report what they show in neutral terms. Quote
   offensive wording only if it is itself the evidence, and mark it as the source's language.
5. Rents, gentrification, business turnover and displacement economics are out of scope: skip them.""",
    model=RESEARCHER_MODEL,
    model_settings=SETTINGS,
    tools=RESEARCH_TOOLS,
)


def research_left(ctx: RunContextWrapper[Research], agent) -> bool:
    """research disappears from the Lead's tools once the rounds, the researchers or the time run out."""
    state = ctx.context
    return (state.rounds < MAX_ROUNDS and state.researchers < MAX_RESEARCHERS
            and state.research_time_left() >= MIN_ROUND_SECONDS)


@function_tool(is_enabled=research_left, failure_error_function=tool_error)
async def research(ctx: RunContextWrapper[Research], task: str, era: str, question_type: str, hints: str) -> str:
    """Send a researcher to answer one task about the neighborhood in one era.
    Returns its findings, each with its source link. Use it for each row of your plan, all in the
    same turn so they run in parallel, and again for gaps the timeline shows.

    Args:
        task: One specific thing to find out.
        era: One of '1900-1920', '1940', '1960', '1980', 'today'.
        question_type: 'then_now', 'settlement' or 'remains', or two joined with '+',
            e.g. 'settlement+then_now'.
        hints: Search hints: street names, group names, institutions, other spellings.
    """
    state = ctx.context
    if state.round_turn != state.lead_turns:  # the first research call of this Lead turn
        if state.rounds >= MAX_ROUNDS or state.research_time_left() < MIN_ROUND_SECONDS:
            return "No researchers left. Reply DONE."
        state.rounds += 1
        state.round_turn = state.lead_turns
    if state.researchers >= MAX_RESEARCHERS:
        return "No researchers left. Reply DONE."
    # What researcher.as_tool() does: run the researcher in a fresh context and return its answer.
    # Written out so each run gets a numbered copy, and its own column in the context panel.
    state.researchers += 1
    agent = researcher.clone(name=f"Researcher {state.researchers}")
    state.deadlines[agent.name] = time.monotonic() + min(RESEARCHER_SECONDS, max(state.research_time_left(), 15))
    start, end = ERAS.get(era, (1850, 2026))
    nta = state.nta
    prompt = (f"Neighborhood: {nta['name']}, {nta['borough']} (NTA {nta['code']}, "
              f"{len(nta['tracts'])} census tracts)\n"
              f"Era: {era} (search {start}-{end})\n"
              f"Question type: {' and '.join(QUESTION_TYPES.get(t, t) for t in question_type.split('+'))}\n"
              f"Task: {task}\nHints: {hints}")
    result = await Runner.run(agent, prompt, context=state, hooks=state.hooks, max_turns=12)
    output = str(result.final_output or "").strip()
    if not output:
        # A researcher whose searches all came back empty sometimes replies with nothing: say so,
        # so the Lead sees a gap rather than a silent success.
        searches = [c["args"] for c in state.tool_calls if c["agent"] == agent.name]
        output = f"- No findings: the sources returned nothing for this task. Searches tried: {searches}"
    state.findings.append(f"{agent.name} ({question_type}, {era}): {task}\n\n{output}")
    return output


# --- The census core: the same numbers in every run ---

async def census_core(state: Research) -> str:
    """Fetch the neighborhood's birthplace figures for 2000 and the latest ACS in code, before research,
    so every run's settlement table rests on the same numbers (the researchers' own searches vary from
    run to run). Added to the findings as from the "Census desk". Returns a note for the Lead."""
    code, texts = state.nta["code"], []
    results = await asyncio.gather(*[asyncio.to_thread(census.profile, code, year, "birthplace")
                                     for year in (2000, census.LAST_ACS)], return_exceptions=True)
    for year, result in zip((2000, census.LAST_ACS), results):
        text = failed(f"Census birthplace {year} for {code}", result) if isinstance(result, Exception) \
            else census.to_text(result)
        state.fetched.update(checker.clean_url(url) for url in URL.findall(text))
        state.tool_calls.append({"agent": "Census desk", "name": "census_profile",
                                 "args": {"nta_code": code, "year": year, "topic": "birthplace"}, "result": text[:2000]})
        texts.append(text)
    state.findings.append("Census desk (settlement, today): the largest birthplace groups of the foreign-born, "
                          "in 2000 and today, fetched for every run\n\n" + "\n\n".join(texts))
    return ("The census birthplace figures for 2000 and today are already in the findings (from the Census desk): "
            "don't send a researcher just for those.")


# --- The lead: plans, fans out to researchers, and checks for gaps ---

lead = Agent(
    name="Lead",
    instructions=f"""\
You lead a research team reconstructing the history of one NYC neighborhood.
You're given the neighborhood (with its census tracts), the question types and eras to cover.

1. Save a plan with save_plan: one row per (question type × era) worth researching.
2. Call research once per independent task, all in the same turn, so the researchers work in
   parallel. Typical split:
   - settlement: one task per era for newspaper and NYT evidence of which groups lived there,
     plus one task for census figures 2000-today;
   - then_now: one task per era for photos, maps and descriptions;
   - remains: one task for landmark records, one for recent coverage of surviving institutions.
   Give each a specific task, era, and search hints (street names, group names, institutions).
   Every street and institution in the hints must be inside this neighborhood: a well-known place
   in another neighborhood (even one tied to the same group) sends the researcher to the wrong
   place. If you aren't sure a street or institution is there, leave it out and give the group and
   neighborhood names instead. In later rounds, prefer streets and institutions the findings name.
   You have {MAX_RESEARCHERS} researchers in all: use at most 7 in this first round. With more
   than one question type, combine them so you stay within 7: e.g. one task per era covering both
   settlement and then_now (question_type 'settlement+then_now'), and one remains task for today.
3. Read the findings and save a timeline with save_timeline, before any more research: for each
   group, arrival, peak and decline, with the evidence for each; for each era asked about, what
   the place looked like. Use only what the findings say; write "not found" where they don't.
   In evidence, keep each finding's exact URL next to what it shows: the writer cites only URLs
   you and the researchers pass on.
4. If an era has no evidence, or two sources disagree (e.g. newspapers vs. census), call research
   again for just that gap. Then save the timeline again. A gap task must try something the first
   researcher didn't: each researcher's last bullet names the searches it tried. Name a different
   source in the task (e.g. NYPL photos or a landmark report instead of old newspapers again), or
   different search terms (nearby streets, institution names, other spellings). If the era's
   sources have all been tried, don't retry it: put "not found" in the timeline, and the writer
   will report it as a gap. Population counts exist only from 2000 (census_profile): for older
   eras, don't ask for numbers; ask for the groups, institutions and events the sources record.
   The ~1960 era is often thin: one retry is enough.
5. When everything the sources allow is covered, reply DONE and nothing else: a writer writes the report.
   If research is no longer in your tools, your researchers are used up: save the timeline with
   everything found so far, then reply DONE.

Stay on who settled, what the place looked like, and what remains. Rents, gentrification, business
turnover and displacement economics are out of scope: don't research them or put them in the timeline.""",
    model=MODEL,
    model_settings=SETTINGS,
    tools=[save_plan, research, save_timeline],
)

# --- The writer: one call, after the research ends ---

writer = Agent(
    name="Writer",
    instructions="""\
Write the report in markdown using only the timeline and findings you're given.
Write only the sections for the question types you're given, plus the overview and the last section,
in this order and with exactly these headings (the page lays the report out by them):

## Overview
## Then & now            (if requested; one "### <era>" per era, e.g. "### 1900-1920", "### Today")
## Who settled, and when (if requested)
## What remains          (if requested)
## What the records don't show

- Overview: one paragraph answering the question.
- Then & now: under each era heading, what it looked like, what was happening, photo/map links.
  Never leave an era heading empty: if the findings have nothing for an era, write one sentence
  saying what the researchers looked for and didn't find.
  A photo or map link shows only that an item exists, with its title and date:
  describe what it shows only if a finding says so. Tax-photo links open the photo of one lot
  ("about-1940 tax photo of 100 Avenue A"); never claim what the photo shows.
  Cite photos and maps of the place; don't list archive records or documents just because they exist.
  Cite every NYPL photo or map and every tax photo of the place that the findings list, under its
  era (tax photos of about 1985 go under the 1980s): the page shows each cited item's thumbnail.
  Cite a photo or map only if its title names this neighborhood or a street or building in it:
  leave out views of other parts of the borough. Name it plainly ("a 1936 photo of the Third Avenue
  car barn"), not "An item exists".
- Who settled, and when: a table — Group | Arrived | Peak | Declined/moved | Evidence.
  Mark each date "(documented)" or "(approximate)", e.g. "1980s (approximate)"; when there is no
  date, write just "Not found".
  One row per community of people by origin (Dutch, Irish, Chinese, Puerto Rican, Koreans), never
  per religion or institution: a Quaker meeting house or a Methodist church is evidence for the
  community that built it (put it in that row's Evidence), not a row of its own.
  Rows: the groups the question asks about, the groups the findings date, and the three or four
  largest groups in the Census desk's figures, with their shares in 2000 and today (a share that
  fell or rose says something about Peak and Declined/moved). Leave out a group whose only evidence is a small census share
  (under 5%) with every date "Not found": mention it in the Today era instead.
- What remains: surviving buildings, institutions, names, and what's gone.
- What the records don't show: thin eras, missing groups, approximate census boundaries.
- Every factual sentence and table row ends with a markdown link to the finding's source, named
  for the source, e.g. ([New-York Tribune, 1904](https://www.loc.gov/resource/...)) or
  ([Census 2000](https://api.census.gov/...)). Copy URLs exactly from the findings or timeline.
  Cite a source only for what that source's finding says. Never link to a site's home page or
  make up a URL: a fact with no URL in the findings stays out of the report.
- Rents, gentrification, business turnover and displacement economics are out of scope: leave them out.
- Plain, specific, respectful sentences about communities; present-day group names; no stereotypes;
  no "vibrant", "rich tapestry", "melting pot", "it is worth noting".""",
    model=MODEL,
    model_settings=WRITER_SETTINGS,
)


# --- The citation check: code, not a model, after the Writer ---


def check_report(report: str, state: Research) -> dict:
    """Every factual claim cites a link, and every link is a URL a research tool returned in this run.
    Returns {"failing": [Claim], "problems": [str], "counts": {...}}. It checks that sources exist,
    not what they say: a real URL cited for something it doesn't say gets through."""
    found = checker.code_check(report, state.fetched)
    problems = [f'Uncited: "{c.text}" -> cite its source from the findings, or cut it' for c in found["uncited"]]
    problems += [f'Cites a URL no research tool returned ({url}): "{c.text}" -> use a URL from the findings, or cut it'
                 for c, url in found["unfetched"]]
    failing = {id(c): c for c in found["uncited"]} | {id(c): c for c, _ in found["unfetched"]}
    counts = {"claims": len(found["claims"]), "cited_links": len(found["pairs"]) + len(found["unfetched"]),
              "uncited": len(found["uncited"]), "unfetched": len(found["unfetched"]), "failing": len(failing)}
    return {"failing": list(failing.values()), "problems": problems, "counts": counts}


BARE_URL = re.compile(r"(?<!\]\()(?<![<(])\bhttps?://[^\s)<>\]\"']+")
SOURCE_NAMES = {"s-media.nyc.gov": "Landmarks Preservation Commission", "www.nytimes.com": "New York Times",
                "www.loc.gov": "Chronicling America", "digitalcollections.nypl.org": "NYPL Digital Collections",
                "data.census.gov": "Census Bureau", "data.cityofnewyork.us": "NYC Open Data",
                "nycrecords.access.preservica.com": "NYC Municipal Archives"}


def link_bare_urls(text: str) -> str:
    """Researchers cite sources as bare URLs: make each a markdown link named after its source."""
    def link(m):
        url = m.group(0).rstrip(".,;:")
        host = url.split("/")[2]
        return f"[{SOURCE_NAMES.get(host, host)}]({url})" + m.group(0)[len(url):]
    return BARE_URL.sub(link, text)


FINDING_HEAD = re.compile(r"^([^()\n]+) \(([^,]+), ([^)]+)\): (.*)$", re.MULTILINE)


def findings_report(state: Research) -> str:
    """The report when the Writer can't finish in time: the researchers' own cited findings, by era,
    under the headings the page lays out. Plainer than the Writer's, but every bullet keeps its link."""
    by_era: dict[str, list[str]] = {}
    for finding in state.findings:
        head = FINDING_HEAD.match(finding)
        era = head.group(3) if head else "Other"
        by_era.setdefault(era, []).append(link_bare_urls(finding.split("\n\n", 1)[-1].strip()))
    order = [e for e in ERAS if e in by_era] + [e for e in by_era if e not in ERAS]
    parts = ["## Overview\n\nThe write-up ran out of time, so these are the researchers' findings as they "
             "filed them, by era. Each one links to its source.", "## Then & now"]
    parts += [f"### {era if era != 'today' else 'Today'}\n\n" + "\n".join(by_era[era]) for era in order]
    parts.append("## What the records don't show\n\nThe findings above weren't combined into a single "
                 "account, so gaps between eras aren't summarized here. Bullets saying a search found "
                 "nothing are the gaps the researchers reported.")
    return "\n\n".join(parts)


async def write_in_time(prompt: str, state: Research) -> str | None:
    """One Writer run, or None if it can't finish before RUN_SECONDS (Vertex is sometimes slow)."""
    left = max(RUN_SECONDS - state.elapsed(), 30)
    try:
        result = await asyncio.wait_for(
            Runner.run(writer, prompt, context=state, hooks=state.hooks, max_turns=2), timeout=left)
        return str(result.final_output)
    except TimeoutError:
        return None


async def write_and_check(prompt: str, state: Research) -> str:
    """Python, not an agent, runs this loop: write, check, one revision with the problems listed,
    check again, and mark whatever still fails as (unverified). If the Writer can't finish within
    the 5 minutes, the researchers' findings go out instead."""
    report = await write_in_time(prompt, state)
    if report is None:
        state.hooks.activity("Writer", "ran out of time: sending the researchers' findings instead")
        report = findings_report(state)
        found = check_report(report, state)
        state.checks.append(found["counts"])
        return checker.mark_unverified(report, found["failing"])
    first = check_report(report, state)
    state.checks.append(first["counts"])
    state.hooks.activity("Citation check", f"first check: {first['counts']}")
    if not first["failing"]:
        return report
    if state.elapsed() > RUN_SECONDS - REVISION_SECONDS:
        # No time for a revision: the answer has to arrive within 5 minutes
        state.hooks.activity("Citation check", "no time for a revision: marking what fails as unverified")
        return checker.mark_unverified(report, first["failing"])

    problems = "\n".join(f"- {p}" for p in first["problems"])
    revision = (f"{prompt}\n\nYour report:\n\n{report}\n\nA citation check found these problems:\n{problems}\n\n"
                "Revise the report: fix each problem by citing the right source from the findings, "
                "or cut the claim. Keep everything else as it is. Reply with the whole report.")
    revised = await write_in_time(revision, state)
    if revised is None:
        state.hooks.activity("Citation check", "the revision ran out of time: marking what fails as unverified")
        return checker.mark_unverified(report, first["failing"])
    report = revised
    final = check_report(report, state)
    state.checks.append(final["counts"])
    state.hooks.activity("Citation check", f"after revision: {final['counts']}")
    return checker.mark_unverified(report, final["failing"])


async def deep_research(question: str, hooks: PanelHooks, asked: str | None = None,
                        answer: str | None = None, state: "Research | None" = None) -> tuple[dict, Research]:
    """Clarify, then research and write. Returns ({"type": "clarify", ...} or {"type": "done",
    "markdown": ...}, the run's state). The server keeps nothing between requests: to answer a
    clarifying question, the page sends the original question, the question asked, and the answer.
    Pass state to keep hold of the tool calls even if the run fails."""
    research_run = state or Research(hooks=hooks)

    # 0. Clarify: which neighborhood, which question types, and is it in scope?
    prompt = f"Question: {question}"
    if asked and answer:
        prompt += f"\n\nEarlier you asked: {asked}\nThe user answered: {answer}"
    try:
        clarified = await Runner.run(clarifier, prompt, context=research_run, hooks=hooks, max_turns=12)
    except MaxTurnsExceeded:
        # It kept looking up addresses without settling: ask the user instead of failing the run
        return {"type": "clarify", "out_of_scope": False,
                "question": "Which neighborhood do you mean? Name it, or give a street address there.",
                "options": []}, research_run
    c = check_clarify(clarified.final_output, research_run)
    if not c.ready:
        return {"type": "clarify", "question": without_codes(c.question or "Which neighborhood do you mean?"),
                "options": [without_codes(o) for o in c.options], "out_of_scope": c.out_of_scope}, research_run

    research_run.nta, research_run.question_types, research_run.eras = geo.nta(c.nta_code), c.question_types, c.eras
    nta = research_run.nta
    about = (f"Neighborhood: {nta['name']}, {nta['borough']} (NTA {nta['code']}; census tracts "
             f"{', '.join(nta['tracts'])})\n"
             f"Question types: {', '.join(QUESTION_TYPES[t] + f' ({t})' for t in c.question_types)}\n"
             f"Eras: {', '.join(c.eras)}"
             + (f"\nGroup the user asked about: {c.group}" if c.group else "")
             + (f"\nNote: {c.note}" if c.note else ""))
    hooks.activity("Clarifier", f"ready: {nta['name']} ({nta['code']}), {', '.join(c.question_types)}")
    about += "\n" + await census_core(research_run)
    hooks.activity("Census desk", "fetched the birthplace figures for 2000 and today")

    # 1. Research: plan, fan out, check for gaps
    try:
        # Backstop: researchers stop on their own by RESEARCH_SECONDS; this stops a Lead that keeps going
        await asyncio.wait_for(
            Runner.run(lead, f"Question: {question}\n{about}", context=research_run, hooks=hooks, max_turns=15),
            timeout=max(research_run.research_time_left(), 0) + 30)
    except TimeoutError:
        hooks.activity("Lead", "ran out of research time. Writing up the findings.")
    except (ModelBehaviorError, MaxTurnsExceeded) as e:
        # Once the rounds run out, research is gone from the Lead's tools, but the model sometimes
        # calls it anyway, which the SDK treats as fatal. Either way the research is over: write it up.
        # The SDK words this as "Tool research not found in agent Lead" or "Tool research is
        # currently disabled for agent Lead", depending on the version and the turn.
        if isinstance(e, ModelBehaviorError) and not re.search(r"Tool '?research'? (not found|is currently disabled)", str(e)):
            raise
        if isinstance(e, MaxTurnsExceeded):
            reason = "used all its turns"
        elif research_run.research_time_left() < MIN_ROUND_SECONDS:
            reason = "asked for more research after the research time ran out"
        elif research_run.researchers >= MAX_RESEARCHERS:
            reason = f"asked for more research after all {MAX_RESEARCHERS} researchers were used"
        else:
            reason = f"asked for more research after all {MAX_ROUNDS} rounds were used"
        hooks.activity("Lead", f"{reason}, so research is over. Writing up the findings.")

    # 2. Write and check, outside the research loop. The Writer sees only the question, the timeline
    # and the findings; code checks its citations.
    findings = "\n\n---\n\n".join(research_run.findings)
    timeline = json.dumps(research_run.timeline, indent=1)
    prompt = f"Question: {question}\n{about}\n\nTimeline:\n{timeline}\n\nFindings:\n\n{findings}"
    report = await write_and_check(prompt, research_run)
    return {"type": "done", "markdown": report, "checks": research_run.checks,
            "neighborhood": f"{nta['name']}, {nta['borough']}"}, research_run


# --- FastAPI App ---

HERE = Path(__file__).parent

# run_id -> every agent's context, in order. In-memory, single process. The context panel reads it.
sessions: dict[str, AgentContexts] = {}
MAX_SESSIONS = 5

app = FastAPI()
add_context_panel(app, sessions)


@app.get("/")
def index():
    # no-cache: browsers otherwise keep serving an old page after a redeploy
    return FileResponse(HERE / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/run")
async def run(question: str, asked: str | None = None, answer: str | None = None):
    """Research one question and stream what happens as Server-Sent Events. Ends with a "clarify"
    event (a question and options) or a "done" event (the report). To answer a clarifying question,
    call again with the original question, the question asked, and the answer."""
    run_id = str(uuid.uuid4())
    sessions[run_id] = AgentContexts()
    # Keep the newest runs' contexts only: each holds every agent's full context, and keeping all of
    # them would grow the server's memory with every question
    while len(sessions) > MAX_SESSIONS:
        sessions.pop(next(iter(sessions)))
    queue: asyncio.Queue = asyncio.Queue()
    hooks = TraceHooks(sessions[run_id], queue.put_nowait)

    async def work():
        try:
            result, state = await deep_research(question, hooks, asked, answer)
            queue.put_nowait({**result, "tool_calls": state.tool_calls, "thumbnails": state.thumbnails})
        except Exception as e:
            # Auth, quota, a model that won't stop: show it on the page, not as a dropped stream.
            queue.put_nowait({"type": "error", "message": error_text(e, 500)})

    task = asyncio.create_task(work())

    async def events():
        try:
            yield f"data: {json.dumps({'type': 'start', 'run_id': run_id})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
                if event["type"] in ("done", "clarify", "error"):
                    break
        finally:
            task.cancel()  # the page closed the stream: stop spending tokens

    return StreamingResponse(events(), media_type="text/event-stream")


# --- /chat: the Project 1 shape. One request runs the whole pipeline and returns the report (or
# a clarifying question) with every agent's tool calls. ---


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]  # each {"agent", "name", "args", "result"}


# session_id -> the clarification waiting for an answer: {"question", "asked"}. In-memory, single
# process, like pam's sessions. If it's gone (a new instance), the answer is treated as a new question.
pending: dict[str, dict] = {}


def clarify_text(result: dict) -> str:
    return result["question"] + "".join(f"\n- {option}" for option in result["options"])


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    waiting = pending.pop(session_id, None)
    if waiting:  # this message answers the clarifying question
        question, asked, answer = waiting["question"], waiting["asked"], request.message
    else:
        question, asked, answer = request.message, None, None

    sessions[session_id] = AgentContexts()  # the context panel can show this run too
    hooks = TraceHooks(sessions[session_id], lambda event: None)
    state = Research(hooks=hooks)
    try:
        result, _ = await deep_research(question, hooks, asked, answer, state)
        if result["type"] == "clarify":
            if not result["out_of_scope"]:
                pending[session_id] = {"question": question, "asked": result["question"]}
            response = clarify_text(result)
        else:
            response = result["markdown"]
    except Exception as e:
        # Auth, quota, a model that won't stop: show it in the chat, not as a 500
        response = f"Research failed: {error_text(e)}"
    # every agent's tool calls, including the ones before a failure
    return ChatResponse(response=response, session_id=session_id, tool_calls=state.tool_calls)


@app.post("/clear")
def clear(session_id: str | None = None):
    pending.pop(session_id, None)
    sessions.pop(session_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    # Cloud Run tells us which port to use with $PORT (locally it's just 8000)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
