# Neighborhood Time Machine

## Description + Target Audience
The Neighborhood Time Machine is a deep research agent: ask it what a neighborhood in NYC looked like around 1900–1920, 1940, 1960, 1980 and today, which immigrant communities settled there and when, or which of their buildings and institutions remain. It searches historical newspapers, the New York Times archive, the New York Public Library's digital
collections, NYC landmark designation reports and the census, and writes a report where every fact links to the record it came from. If the records have little coverage of a specific time, it says so. 

The Neighborhood Time Machine is built for anyone interested in the history of NYC, especially in the deeply immigrant influenced neighborhoods. It is for anyone curious about what their current neighborhood looked like throughout the 20th century until now and who may have lived on their block before them.

It is built on FastAPI + the OpenAI Agents SDK + LiteLLM + Gemini on Vertex AI (`vertex_ai/gemini-3.5-flash` for the Clarifier, Lead and Writer;
`vertex_ai/gemini-3.5-flash-lite` for the Researchers).

## How to use the deployed agent

Open https://nyc-time-travel-git-484339235648.europe-west1.run.app/ in a browser.

- Type a question, or click one of the example questions under the box.
- Name the neighborhood any way you like: official names ("Sunset Park"), informal ones ("Koreatown", "Little Germany"), or ones that mean several places ("Chinatown", "Little Italy"). If the name is ambiguous or the question is vague, the agent will ask a follow up question, and you can click an option.
- The finished report goes to press as the front page: the overview as the lead story, with a lead picture. Below it is a timeline of the eras (Then & now). After that comes the settlement table (Who settled, and when; "The Record"), what remains ("Still Standing") and what the records don't show ("Corrections & Omissions"). Every fact ends with a link to its source.

## Data: sources, how to load it, and limits

There are several datasets in use; one small file is in the repo, and everything else is accessed through public APIs when someone asks a question, and the report links to each record it used.

**In the repo: `data/ntas.json` (2.6 MB).** NYC's 262 official neighborhoods (2020 Neighborhood
Tabulation Areas, NTAs), each with its code, name, borough, county, type (neighborhood, park, cemetery,
airport…), the 2020 census tracts inside it, a bounding box and its boundary polygons. The Clarifier
uses it to match names and to check that an address falls inside a neighborhood. It's built from two NYC Open Data datasets (Department of City Planning):

- 2020 NTAs with boundaries: <https://data.cityofnewyork.us/resource/9nt8-h7nd.json>
- 2020 census tract to NTA equivalency: <https://data.cityofnewyork.us/resource/hm78-6dwm.json>

To load it: it's plain JSON keyed by NTA code (`json.load(open("data/ntas.json"))["BK0702"]`). To rebuild it from the source: `uv run geo.py build`.

**Fetched through APIs, done when question is called.** Each can be tried in a browser or with `curl`:

| Source | What part is used | How to load it | Key |
| --- | --- | --- | --- |
| US Census Bureau API | 2000 Census SF3 (tables PCT018 ancestry, PCT019 birthplace) and ACS 5-year 2010–2024 (B04006 ancestry, B05006 birthplace, B16001/C16001 language), by tract | `https://api.census.gov/data/2024/acs/acs5?get=group(B05006)&for=tract:*&in=state:36%20county:047&key=YOUR_KEY`; or browse the same tables at data.census.gov | Free: [sign up](https://api.census.gov/data/key_signup.html) |
| Library of Congress, Chronicling America | Digitized NYC newspaper pages, 1900–1954: search hits, OCR text, page scans | `https://www.loc.gov/collections/chronicling-america/?q=hester+street&dates=1900/1910&fa=location_state:new+york\|location_city:new+york&fo=json` | None |
| New York Times Article Search API | Headlines, abstracts, dates and links, 1851–today | `https://api.nytimes.com/svc/search/v2/articlesearch.json?q=sunset+park&begin_date=19800101&end_date=19891231&api-key=YOUR_KEY` | Free: [developer.nytimes.com](https://developer.nytimes.com) |
| NYPL Digital Collections API | Public-domain photos, maps and prints: titles, dates, places, thumbnails | `https://api.repo.nypl.org/api/v2/items/search?q=orchard+street` with the header `Authorization: Token token="YOUR_KEY"` | Free: [sign up](https://api.repo.nypl.org/sign_up) |
| NYC Landmarks Preservation Commission (NYC Open Data) | Individual landmarks (`buis-pvji`), the building database (`gpmc-yuvp`), historic districts (`skyk-mpzq`), and designation report PDFs | `https://data.cityofnewyork.us/resource/gpmc-yuvp.json?$limit=5`; reports at `https://s-media.nyc.gov/agencies/lpc/lp/2622.pdf` | None |
| NYC Municipal Archives | ~1940 and ~1985 tax photos, found by borough, block and lot | `https://nycrecords.access.preservica.com/?s=nynyma_rec0040_1_00414_0056` (~1940; `REC0041_…` for ~1985) | None |
| NYC GeoSearch (helper) | Street address to coordinates and borough-block-lot | `https://geosearch.planninglabs.nyc/v2/search?text=97+Orchard+Street+Manhattan` | None |

### Limits

- **Chronicling America data stop in 1954.** Chronicling America only has public-domain papers. For NYC that's rich before 1923 (the Tribune, the Sun, the Evening World) and thin through the 1940s (some Yiddish dailies, the Daily Worker). For 1960, 1980 and today the newspaper source is the NYT.
- **The NYT search returns headlines, abstracts and snippets, not full text,** Many old articles have
  only a headline. Its place tags exist only from 1981. The API allows about 500 requests a day, so heavy use runs out of quota quickly.
- **Census numbers start in 2000.** The 1990 long form isn't in the Census API, and the 2010 census didn't
  ask about ancestry, birthplace or language. Tract boundaries change between decades, so older totals
  for today's neighborhoods are approximate.
- **Neighborhoods are 2020 NTAs.** A historic neighborhood like Koreatown is a few blocks of a larger NTA
  (Midtown South), so its census figures cover the whole NTA; the report says so.
- **NYPL's openly available material skews old** In addition, coverage of any one block is hit or miss.
- **Coverage varies a lot by neighborhood**, and the ~1960 era is thin almost everywhere. Thinly
  documented places get thinner answers by design.
- **The time limits trade some depth for speed.** A loc.gov newspaper search takes about 30 seconds,
  and NYT requests are spaced 12 seconds apart (the NYT's recommended pause), so a run gets about 14 NYT searches. So that every answer arrives within 5
  minutes, research stops 170 seconds into a run, each researcher gets at most 90 seconds before it
  reports what it has, and the citation revision runs only if it still fits (otherwise failing claims
  are marked "(unverified)" straight away). If the Writer itself is slow (Vertex sometimes is), the page
  gets the researchers' cited findings by era instead of a written report, so an answer still arrives
  in time. The NYT key also has a daily request limit: once it's used up, researchers
  skip the NYT until it resets, and the reports lean on the other sources.
  

## Sample queries

Three test queries. For each: the expected answer, checked at the source before running the agent; an
excerpt of the agent's answer; and the same model with no tools or system prompt
(`vertex_ai/gemini-3.5-flash`, sent only the question). Full answers are in [samples/](samples/).

### 1. "What happened to Little Germany in the East Village after the General Slocum disaster?"

- **Expected:** the 1904 *General Slocum* fire killed over 1,000 residents, 784 of them from St. Mark's
  Lutheran Church. It was the "symbolic end" of a community already moving uptown to Yorkville; St.
  Mark's later became a synagogue. Source: LPC report [LP-2491](https://s-media.nyc.gov/agencies/lpc/lp/2491.pdf).
- **Agent** (241 s, 7 researchers, 81 links): matches on every point, each linked to the landmark report,
  a 1904 newspaper page or the NYT, and follows the neighborhood through all five eras.
  [Full answer](samples/1-little-germany.md)
- **No tools:** "Within just a few years of the tragedy, the neighborhood virtually vanished."
- **Difference:** the model gets the date and names right but overstates the fire's effect, with no
  sources. The agent matches the record.

### 2. "What did the Lower East Side's pushcart markets look like around 1910?"

- **Expected:** carts lining both sides of the street, women shopping for the Sabbath, barrels of
  herring, peddlers calling in Yiddish. Source: The Evening World, April 14, 1905
  ([page](https://www.loc.gov/resource/sn83030193/1905-04-14/ed-1/?sp=19)), and The Sun, April 12, 1908.
- **Agent** (189 s, 1 researcher, 17 links): "Shoppers were overwhelmingly female, particularly on Friday
  mornings as women prepared for the Sabbath by purchasing fish, fowl, fruits, vegetables, and challah"
  ([The Evening World, 1905](https://www.loc.gov/resource/sn83030193/1905-04-14/ed-1/?sp=19)).
  [Full answer](samples/2-pushcart-markets.md)
- **No tools:** a vivid scene with cart rental prices and quoted cries ("Hees! Hees!") that no source
  supports.
- **Difference:** the agent's scene is plainer, but every detail comes from a reporter who was there.

### 3. "How did Brighton Beach become 'Little Odessa'?"

- **Expected:** Soviet immigration, above all from Ukraine. Ukraine-born residents are the largest
  foreign-born group: 28.1% in 2000, 24.3% in 2020–2024, with Russia second and Uzbekistan now third.
  Source: census birthplace tables for
  [2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047036001,36047036002,36047036200,36047036400,36047036600,36047061002,36047061001)
  and [2020–2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047036001,36047036002,36047036200,36047036400,36047036600,36047061002,36047061003,36047061004).
- **Agent** (467 s, 8 researchers, 57 links; 2 claims marked "(unverified)"): the 1970s–80s Soviet wave
  (NYT, 1985) and today's figures, Ukraine 24.3% and Russia 14.3%. [Full answer](samples/3-little-odessa.md)
- **No tools:** the same story, including recent Central Asian arrivals, but no numbers or sources.
- **Difference:** the closest pair; the agent adds the figures and a dated source for each step.

The page's example buttons are listed under [Example queries](#example-queries).

## How it works

```text
question ─► CLARIFIER ─► which neighborhood? which question types and eras? in scope?
              │            (not sure: reply with a question and options, and stop)
              ▼
            LEAD ─► save_plan ─► research ×N in ONE turn ─► Researchers 1..N run in parallel,
              ▲                                             each in a fresh context
              │                                                   │
              └── save_timeline ◄── findings ◄────────────────────┘
                  gaps or contradictions? ─► research again (up to 2 more rounds)
              ▼
            WRITER ─► report from the timeline and findings only
              ▼
            CITATION CHECK (code) ─► every claim cites a link? every link came from a tool?
                                     no: one Writer revision, then mark what still fails "unverified"
```

| Agent | Job | Tools |
| --- | --- | --- |
| Clarifier | Turns the question into one official neighborhood (an NYC Neighborhood Tabulation Area, NTA), question types and eras; asks when the name is ambiguous or the question vague; turns away out-of-scope questions. For informal names it picks a street address it knows is there, and code checks the address against the real NTA boundaries | `resolve_neighborhood`, `neighborhood_at` |
| Lead | Plans era × question type, sends Researchers (all in one turn so they run in parallel), saves a timeline, and sends more Researchers for gaps | `save_plan`, `research`, `save_timeline` |
| Researcher (clones "Researcher 1", "Researcher 2", …) | One task, one era, in a fresh context: searches, reads the most relevant pages, and replies with cited bullets | the research tools below |
| Writer | Writes the report from the question, timeline and findings only | none |

Before the Lead starts, code fetches the neighborhood's census birthplace figures for 2000 and today
and adds them to the findings (the "Census desk" on the page), so every run's settlement table rests on
the same numbers; what the Researchers find in the archives still varies from run to run.

Caps are enforced in code, not just asked for in prompts: at most 10 Researchers and 3 rounds per run
(`research` disappears from the Lead's tools when they run out), at most 5 page/report reads and
3 searches of each slow archive and 90 seconds per Researcher.

The citation check is code, not a model ([checker.py](checker.py)). We built an LLM Checker that
judged each claim against its source, and dropped it: on our test runs it flagged many correct claims
(including a census figure we checked by hand), adding cost and noise without catching real errors.

### Research tools

| Tool | What it does | Source |
| --- | --- | --- |
| `census_profile` | The largest ancestry, birthplace or language groups for a neighborhood and year, summed over its census tracts, with margins of error | US Census API: 2000 Census (SF3) and ACS 5-year 2010–2024; each figure links to its table on data.census.gov |
| `search_old_newspapers` | Up to 5 NYC newspaper pages for 2–3 search words and a year range, with the matched snippet | Library of Congress, Chronicling America (loc.gov API) |
| `read_old_newspaper_page` | A newspaper page's OCR text around the search words | Chronicling America |
| `search_nyt` | Up to 5 NYT articles: headline, date, abstract or snippet, URL; optional place tag from 1981 | NYT Article Search API |
| `search_nypl` | Up to 5 public-domain photos, maps and prints with title, date and collection; photos and maps also get a thumbnail for the page | NYPL Digital Collections API |
| `search_landmarks` | Designated landmarks and historic districts in the neighborhood, by keyword, with their designation reports | NYC Landmarks Preservation Commission datasets (NYC Open Data) |
| `read_landmark_report` | A designation report's text around the search words, with page numbers | LPC designation report PDFs |
| `tax_photo_links` | The Municipal Archives' ~1940 and ~1985 tax photos of one building: a link to each photo, shown in the era that cites it | NYC GeoSearch + NYC Municipal Archives |

Helpers, not sources: NYC GeoSearch (addresses) and the 2020 NTA boundaries and tract lists (see
[Data](#data-sources-how-to-load-it-and-limits)). The tools are in their own modules (`census.py`,
`loc.py`, `nyt.py`, `nypl.py`, `lpc.py`, `geo.py`), each with a smoke test you can run with
`uv run <module>.py`. Tools return errors to the model as text instead of crashing.


## Team

Gabriella Chu (gc3203).
