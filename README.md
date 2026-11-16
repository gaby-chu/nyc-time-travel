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
- Under the report: the fact-check desk's citation counts, the Photo Desk (cited photos, maps and newspaper pages), and the Newsroom, which shows each agent's full context and every tool call it made, live while the report is being written.

### The `/chat` API

`POST /chat` with `{"message": "...", "session_id": null}` runs the whole pipeline and returns
`{"response", "session_id", "tool_calls"}`. `response` is the report in Markdown, or a follow-up
question with its options as a bulleted list. Every agent's tool calls are in `tool_calls`, each as
`{"agent", "name", "args", "result"}` (agents are "Clarifier", "Census desk", "Lead", "Researcher 1", …).
To answer a follow-up question, send the answer as `message` with the same `session_id`.
`POST /clear?session_id=...` forgets a session. The page itself uses `GET /run`, which streams the
same run as Server-Sent Events.

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
- **The time limits trade some depth for speed.** A run gets about 14 NYT searches and at most 10
  researchers; see [Staying under 5 minutes](#staying-under-5-minutes). The NYT key also has a daily
  request limit: once it's used up, researchers skip the NYT until it resets, and the reports lean on
  the other sources.

## Sample queries

Three of the example questions on the page (click one to run it). For each: the expected answer,
checked at the source before reading the agent's answer; the agent's answer; and the same model with no tools or system prompt (`vertex_ai/gemini-3.5-flash`, sent only
the question). Shortened answers, with both sides, are in [samples/](samples/). All were run on
2026-11-16 with the code in this repo. That day the loc.gov newspaper search kept timing out, so no
sample cites a pre-1955 newspaper page. The NYT key's daily limit ran out partway through sample 1;
samples 2 and 3 were run again once the NYT was answering. Where a source failed, the reports say
what they couldn't find instead of filling the gap.

Census shares below are of the foreign-born population, from the birthplace tables (2000 Census
PCT019, ACS 2020–2024 B05006) for the neighborhood's census tracts.

### 1. "How did Jackson Heights become one of the most diverse neighborhoods in the city?"

- **Expected:** a planned "garden apartment" development built by the Queensboro Corporation from
  1910 into the early 1950s, after the Queensboro Bridge (1909) and the Roosevelt Avenue el (1917)
  opened. Source: LPC [Jackson Heights Historic District report, LP-1831](https://s-media.nyc.gov/agencies/lpc/lp/1831.pdf).
  Today it's Latin American and South Asian: Ecuador 15.4%, Colombia 14.6%, Mexico 11.7%,
  Bangladesh 6.7%, India 6.6%; in 2000 Colombia led with 17.9%. Source: census
  [2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36081027300,36081027500,36081027700,36081027900,36081028100,36081028300,36081028500,36081028700,36081028900,36081029100,36081030901,36081030902,36081032700,36081033700,36081033900,36081035100) and [2020–2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36081027301,36081027302,36081027500,36081027701,36081027702,36081027900,36081028100,36081028300,36081028500,36081028700,36081028900,36081029100,36081030903,36081030904,36081030905,36081030906,36081032700,36081033700,36081033900,36081035100).
- **Agent** (201 s, 2 rounds, 7 researchers, 61 links): the Queensboro Corporation, the garden apartments and the
  transit lines from the landmark report, and every census share above, group by group.
  [Answer, shortened](samples/1-jackson-heights.md)
- **No tools:** the same developer and garden apartments, then the Colombian, South Asian and Himalayan
  waves, with restrictive covenants and "160 languages" but no sources and no figures for who lives there now.
- **Difference:** the model tells the story well; the agent adds who lives there now, with a link for
  each figure, and shows that Ecuador-born residents have overtaken Colombia-born.

### 2. "How did downtown Flushing become a Chinatown?"

- **Expected:** China-born residents went from 21.7% of the foreign-born in 2000 to 58.4% in
  2020–2024. In 2000 Korea-born residents (19.8%) were almost as many as China-born, and India-born were 11.5%;
  Korea-born are 4.7% today. Source: census for Flushing-Willets Point, [2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36081038300,36081079700,36081085300,36081085500,36081085700,36081085900,36081086500,36081087100,36081088902,36081116100) and
  [2020–2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36081038301,36081079701,36081079702,36081084901,36081084902,36081085300,36081085500,36081085700,36081085900,36081086500,36081086900,36081087100,36081088902,36081116100).
- **Agent** (276 s, 2 rounds, 6 researchers, 59 links): the census shift exactly, Flushing as a department-store
  hub in 1965 and a "growing Asian presence" driving development by the late 1980s (NYT), and the older
  town from the landmark reports. One slip: it calls 58.4% a share of "the population"; it's of the
  foreign-born. [Answer, shortened](samples/2-flushing.md)
- **No tools:** a confident "Little Taipei" story of Taiwanese arrivals in the 1970s, with no sources;
  in 2000 Taiwan-born residents were 4.9%, and it never mentions the Korean share.
- **Difference:** the model's story may be right about the 1970s, but nothing backs it; the agent's
  is narrower, dated and linked.

### 3. "How did Little Haiti in Flatbush grow?"

- **Expected:** Haiti-born residents are the largest foreign-born group in Flatbush: 27.3% in 2000
  and 25.0% in 2020–2024, ahead of Jamaica (15.8%, then 12.6%) and Trinidad and Tobago. Source: census
  for Flatbush, [2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047050800,36047051000,36047051200,36047051400,36047051600,36047076600,36047077000,36047077200,36047077400,36047078600,36047078800,36047079000,36047079200,36047079600) and [2020–2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047050801,36047050803,36047050804,36047051001,36047051002,36047051200,36047051400,36047051601,36047051602,36047076600,36047077000,36047077200,36047077400,36047078601,36047078801,36047079001,36047079201,36047079602).
- **Agent** (264 s, 1 round, 6 researchers, 46 links; 1 claim marked "(unverified)"): the 1970s–80s Haitian and
  West Indian influx and Haitian-Americans organizing politically by the late 1980s (NYT, 1990),
  Flatbush's suburban beginnings from the landmark reports, and Haiti-born residents as the largest
  foreign-born group today (25.0%). It found nothing for 1960 and says so; that line is the unverified
  one. [Answer, shortened](samples/3-little-haiti.md)
- **No tools:** a detailed history (the Duvalier-era waves, a 2018 designation, street boundaries) with
  no sources and no numbers.
- **Difference:** the model has more story; the agent has the figures and doesn't fill the gaps.

The page's other two examples show the follow-up question. "Who has called Sunset Park home over the
last century?" asks which of the three official Sunset Parks you mean, then writes the report. "Take
me to an immigrant neighborhood I've never heard of" asks you to pick from four NYC neighborhoods
(Belmont, Kensington, Brighton Beach, Jackson Heights); with no tools or system prompt, the same model
answers it with an essay about Saint Paul, Minnesota.

## How it works

```text
question ─► CLARIFIER ─► one official neighborhood, question types, eras (or a follow-up question)
              ▼
            LEAD ─► plan ─► Researchers 1..N in parallel, each in a fresh context
              ▲                         │
              └── timeline, gaps? ◄─────┘   (up to 2 more rounds)
              ▼
            WRITER ─► report from the timeline and findings only
              ▼
            CITATION CHECK (code) ─► one revision, then mark what still fails "(unverified)"
```

- **Clarifier** (`resolve_neighborhood`, `neighborhood_at`): matches the name to an NYC Neighborhood
  Tabulation Area, checking informal names by a street address inside it, and asks when unsure.
- **Lead** (`save_plan`, `research`, `save_timeline`): plans era × question type, sends Researchers
  in one turn, saves a timeline and sends more for gaps.
- **Researchers** (Gemini Flash-Lite): one task and era each, with the research tools: `census_profile`,
  `search_old_newspapers`, `read_old_newspaper_page`, `search_nyt`, `search_nypl`, `search_landmarks`,
  `read_landmark_report`, `tax_photo_links`. Each tool is its own module (`census.py`, `loc.py`,
  `nyt.py`, `nypl.py`, `lpc.py`, `geo.py`) with a smoke test: `uv run <module>.py`.
- **Writer**: no tools; writes only from the question, timeline and findings.

Before the Lead starts, code adds the census birthplace figures for 2000 and today (the "Census
desk"). Caps are enforced in code: at most 10 Researchers and 3 rounds per run, and per Researcher
5 reads, 3 searches of each slow archive and 90 seconds. The citation check is code
([checker.py](checker.py)): every claim needs a link, and every link must have come from a tool. An
LLM checker we tried flagged too many correct claims.

## Staying under 5 minutes

Early runs took about 10 minutes, because the archives are slow: a loc.gov search takes ~30 s and the
NYT allows one request every 12 s. What changed ([app.py](app.py)):

- **A run clock:** research stops at 170 s, no new round starts with under 40 s left, and the answer
  is due by 285 s, leaving the Writer the last ~100 s.
- **90 s per Researcher**, then its tools answer "time's up". The Lead waits for the slowest
  Researcher, so one stuck on loc.gov used to hold up the whole round.
- **Fewer slow calls:** 3 searches per slow archive per Researcher; NYT requests share one 12 s queue,
  and a request that would arrive too late is dropped unsent.
- **Fallbacks:** if the Writer runs out of time, the page shows the Researchers' cited findings by era;
  the citation revision runs only with 45 s to spare, otherwise failing claims are marked "(unverified)".

## Team

Gabriella Chu (gc3203).
