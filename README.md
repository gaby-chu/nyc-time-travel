# Neighborhood Time Machine

Pick a New York City neighborhood and travel back through its records. Neighborhood Time Machine is a
deep research agent: ask it what a neighborhood looked like around 1900–1920, 1940, 1960, 1980 and today,
which immigrant communities settled there and when, or which of their buildings and institutions remain.
It searches historical newspapers, the New York Times archive, the New York Public Library's digital
collections, NYC landmark designation reports and the census, and writes a report where every fact
links to the record it came from. Where the records are thin, it says so.

Built on the course's `wikipedia-deep-research` scaffold: FastAPI + the OpenAI Agents SDK + LiteLLM +
Gemini on Vertex AI (`vertex_ai/gemini-3.5-flash` for the Clarifier, Lead and Writer;
`vertex_ai/gemini-3.5-flash-lite` for the Researchers).

## Use the deployed agent

Open **TODO: Cloud Run URL** in a browser.

- Type a question, or click one of the example questions under the box.
- Name the neighborhood any way you like: official names ("Sunset Park"), informal ones ("Koreatown",
  "Little Germany"), or ones that mean several places ("Chinatown", "Little Italy"). If the name is
  ambiguous or the question is vague, the agent asks which you mean: click an option.
- The page is laid out like a newspaper. While the agents work, **The Newsroom** shows one notebook per
  agent (the editor, each reporter, the rewrite desk), side by side: its full context, filling in live.
  Reporters who work in parallel open their notebooks at the same time. **The Wire**, beside the
  notebooks, lists each agent's steps as they happen. A full run takes about 5 minutes (it waits on slow
  archives; see [Limits](#sources-and-limits)).
- The finished report goes to press as the front page: the overview as the lead story, with a lead
  picture. Below it is a timeline of the eras (Then & now), each in the style of its day. Then come the
  settlement table (Who settled, and when; "The Record"), what remains ("Still Standing") and what the
  records don't show ("Corrections & Omissions"). Every fact ends with a link to its source.
- Pictures appear in the era that cites them, each linking to its page: NYPL photos and maps, the city's
  ~1940 and ~1985 tax photos of buildings the report names, and scans of the newspaper pages the report
  quotes. Only pictures the report cites are shown, since a search for a place name also finds other
  places with the same name. An era with nothing in the records says so. A claim the citation check
  couldn't verify is highlighted as "unverified".
- Each notebook in the Newsroom also lists that agent's tool calls: click one to see its arguments and
  result.

Out of scope, and the agent says so: places outside the five boroughs; rents, real estate,
gentrification and business turnover; genealogy and private individuals.

## Sample queries

Three queries for testing. For each: the answer we expect, checked directly at the source before running
the agent; where it comes from; the agent's answer; and the same model's answer with no tools and no
system prompt (`vertex_ai/gemini-3.5-flash`, the model behind the agent's Lead and Writer, sent only the
question). Excerpts are below; the full answers are in [samples/](samples/). Both answers in each pair were
produced on the same day.

### 1. "What happened to Little Germany in the East Village after the General Slocum disaster?"

**Expected answer.** On June 15, 1904, the excursion steamboat *General Slocum*, chartered for a church
picnic, burned, killing more than 1,000 neighborhood residents, including 784 members of St. Mark's
Evangelical Lutheran Church. The fire is "widely considered the symbolic end of Kleindeutschland"; the
center of German New York was already shifting uptown to Yorkville. St. Mark's church building later
became the Community Synagogue Center.

**Source.** LPC designation reports [LP-2491](https://s-media.nyc.gov/agencies/lpc/lp/2491.pdf) (East
Village/Lower East Side Historic District: the "symbolic end" quote, Yorkville, the 784 congregants,
St. Mark's later use) and [LP-2475](https://s-media.nyc.gov/agencies/lpc/lp/2475.pdf) (the same quote);
the New-York Tribune's front page of June 16, 1904 in Chronicling America
(`https://www.loc.gov/resource/sn83030214/1904-06-16/ed-1/?sp=1`).

**Agent** (241 s, 2 rounds, 7 researchers; 62 claims with 81 links; the first draft cited 2 URLs no tool
had returned, fixed in the revision) [full answer](samples/1-little-germany.md):

> On June 15, 1904, the chartered steamboat *General Slocum* caught fire on the East River, killing more
> than 1,000 local residents, including 784 members of St. Mark's Evangelical Lutheran Church ([LPC
> Designation Report LP-2491, 2012](https://s-media.nyc.gov/agencies/lpc/lp/2491.pdf)). [...] This event
> hastened the exodus of German residents from the Lower East Side to Yorkville and other areas [...]
> In 1940, the St. Mark's Evangelical Lutheran Church congregation sold its building at 323 East 6th
> Street to the Community Synagogue Center [...]

It also covers what came after across all five eras: Eastern European Jewish, Polish, Hungarian and
Ukrainian churches and residents, later Black and Puerto Rican residents, and the German buildings that
survive, each fact linked to a landmark report, a 1904 newspaper page or an NYT article.

**Same model, no tools** [full answer](samples/1-little-germany.md#2-gemini-35-flash-no-tools-no-system-prompt):

> It was also the definitive death blow to **Kleindeutschland** [...] Within just a few years of the
> tragedy, the neighborhood virtually vanished. [...] By 1905, just one year after the disaster, the
> German population of the East Village had dwindled to a fraction of its former size.

**Difference.** The model knows the story and gets the date, St. Mark's and Yorkville right, but with no
sources, and it overstates: the landmark report calls the fire the *symbolic* end of a community that was
already moving uptown, not a blow that emptied the neighborhood within a year. The agent's version matches
the record and links each fact to it.

### 2. "What did the Lower East Side's pushcart markets look like around 1910?"

**Expected answer.** Carts lined both sides of the market streets, so only a small wagon could pass; the
shoppers were mostly women buying fish, fowl, fruit, vegetables and challah for the Sabbath on Thursday
evening and Friday morning; barrels of salt herring; boys and peddlers shouting their wares in Yiddish.
Carts stood in place about twelve hours a day, piled with everything "from a shoestring to a top hat".

**Source.** Chronicling America (loc.gov): The Evening World, April 14, 1905, p. 19
(`https://www.loc.gov/resource/sn83030193/1905-04-14/ed-1/?sp=19`), and The Sun, April 12, 1908, p. 32
(`https://www.loc.gov/resource/sn83030272/1908-04-12/ed-1/?sp=32`). NYPL Digital Collections has a 1905
photograph, "Hester Street, New York".

**Agent** (189 s, 1 round, 1 researcher: one era and one question type, so the Lead sent one; 16 claims
with 17 links, no problems) [full answer](samples/2-pushcart-markets.md):

> Carts stood packed two or three tiers deep on both sides of the roadway, and occasionally stood directly
> in the middle of Hester Street ([The Sun, 1904](https://www.loc.gov/resource/sn83030272/1904-07-26/ed-1/?sp=10)).
> This density blocked the streets so severely that only small-sized wagons could pass [...] Shoppers were
> overwhelmingly female, particularly on Friday mornings as women prepared for the Sabbath by purchasing
> fish, fowl, fruits, vegetables, and challah Sabbath loaves ([The Evening World, 1905](https://www.loc.gov/resource/sn83030193/1905-04-14/ed-1/?sp=19)).
> Goods displayed on the pushcarts [...] included eggs, cranberries, kneepants, coffee, wine glasses,
> pickled tomatoes, underwear, and barrels of salt herring [...]

**Same model, no tools** [full answer](samples/2-pushcart-markets.md#2-gemini-35-flash-no-tools-no-system-prompt):

> These were heavy, two-wheeled wooden carts, often rented from local stables for about 10 to 25 cents a
> day. [...] Peddlers [...] barked, sang, and yelled in a mix of Yiddish, Italian, and heavily accented
> English. *"Hees! Hees! (Herring!)"* or *"A penny a plate!"* rose above the din.

**Difference.** The model writes a vivid scene, but every detail is unsourced and some can't be checked
(the rental price, the quoted cries; the 1905 reporter records the cry *"Veiber!"*, Yiddish for
"women!"). The agent's scene is plainer, but each detail comes from a reporter who was there, and its
"What the records don't show" section says what the pages don't cover (unlicensed vendors, what happened
after 1920).

### 3. "How did Brighton Beach become 'Little Odessa'?"

**Expected answer.** Through immigration from the Soviet Union, above all Ukraine. Ukraine and Russia are
the two largest foreign birthplaces: in 2000, 6,284 Ukraine-born (28.1%) and 4,420 Russia-born (19.7%) of
22,391 foreign-born residents; in 2020-2024, Ukraine 4,853 (24.3%), Russia 2,853 (14.3%), and a newer group
from Uzbekistan, 1,824 (9.1%), of 19,991.

**Source.** Census API, place of birth of the foreign-born, summed over Brighton Beach's tracts (NTA
BK1303): 2000 SF3 table PCT019
(`https://api.census.gov/data/2000/dec/sf3?get=group(PCT019)&for=tract:036001,036002,036200,036400,036600,061002,061001&in=state:36%20county:047`)
and ACS 2020-2024 table B05006
(`https://api.census.gov/data/2024/acs/acs5?get=group(B05006)&for=tract:036001,036002,036200,036400,036600,061002,061003,061004&in=state:36%20county:047`).

**Agent** (467 s, 3 rounds, 8 researchers; 52 claims with 57 links; 2 claims still failing after the
revision, marked "(unverified)") [full answer](samples/3-little-odessa.md):

> Brighton Beach became known as "Little Odessa" due to a major wave of immigration starting in the
> mid-1970s and 1980s, when Soviet emigres—particularly Jewish families from Ukraine and other Soviet
> republics—settled in large numbers in the neighborhood ([The New York Times, 1985](https://www.nytimes.com/1985/11/03/magazine/old-country-pleasures-brooklyn-s-borscht-belt.html)).
> [...] Ukraine is the largest single foreign birthplace group with 4,853 people (24.3%), followed by
> Russia with 2,853 (14.3%) [...]

It also traces the place before the Soviet wave (a summer resort around 1900-1920, from Chronicling America
ads and articles). It gives the 2020-2024 census figures but not the 2000 ones.

**Same model, no tools** [full answer](samples/3-little-odessa.md#2-gemini-35-flash-no-tools-no-system-prompt):

> Brighton Beach [...] became known as **"Little Odessa"** due to a massive influx of Soviet
> immigrants—specifically Soviet Jews—beginning in the 1970s. [...] In recent years, a new wave of
> immigrants from Central Asian countries (such as Uzbekistan, Kyrgyzstan, and Tajikistan) has arrived

**Difference.** The model already knows this story well, including the newer Central Asian arrivals. The
agent adds what the model can't: the numbers (Ukraine-born still the largest group, Uzbekistan now third)
and a dated, linked source for each step. This is the query where the model's own knowledge is closest
to the agent's.

The page's example buttons ask about neighborhoods where immigrant communities are thriving today. Three
of them are the samples above; the other two are "How did downtown Flushing become a Chinatown?" and a
vague one, "Take me to an immigrant neighborhood I've never heard of" (the agent suggests neighborhoods to
pick from).

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

Helpers, not sources: NYC GeoSearch (addresses), the 2020 NTA boundaries and tract equivalencies from NYC
Open Data (built once into `data/ntas.json` by `uv run geo.py build`). The tools are in their own modules
(`census.py`, `loc.py`, `nyt.py`, `nypl.py`, `lpc.py`, `geo.py`), each with a smoke test you can run
with `uv run <module>.py`. Tools return errors to the model as text instead of crashing.

### `/chat` API

`POST /chat` keeps the response shape of our Project 1 agent:

```jsonc
// request
{"message": "Tell me the story of Chinatown", "session_id": null}
// response
{"response": "Which Chinatown would you like to explore?\n- Chinatown-Two Bridges, Manhattan (MN0301)\n- ...",
 "session_id": "1c1b3dd1-...",
 "tool_calls": [{"agent": "Clarifier", "name": "neighborhood_at",
                 "args": {"address": "70 Mott Street, Manhattan"}, "result": "MN0301: Chinatown-Two Bridges, ..."}]}
```

`response` is the report markdown, or a clarifying question with one `- option` line per option. Send
the chosen option as the next `message` with the same `session_id`. `tool_calls` holds every tool call
from every agent, each tagged with its `agent` ("Clarifier", "Lead", "Researcher 3", …). The page itself
uses `GET /run`, which streams the same run as Server-Sent Events.

## Evidence for the Deep Research requirements

All runs below are on the code in this repo. Numbers are from the runs' logs.

**Researchers fan out in parallel, in fresh contexts.** In the Little Italy run ("Who settled in Little
Italy in Manhattan, and when?"), the Lead called `research` five times in one turn, and Researchers 1–5
all started at 13.5 s, one per era (1900–1920, 1940, 1960, 1980, today), and ran at the same time: the
first finished at 23.9 s and the last at 353.4 s. Each is a clone of the Researcher run with its own
`Runner.run`, so each starts from an empty context with only its task. To watch this live, open the
Newsroom during a run: each Researcher gets its own notebook, and they all open on the Lead's turn.

**The Lead goes back for gaps.** In the same question's earlier run, round 1 found no population
figures for 1940 or 1960. The Lead saved a timeline, then sent Researcher 6 with a gap task ("population
counts, percentages of Italian-descent residents, or presence of other ethnic groups … during the 1940
and 1960 census eras"), and saved the timeline again:

| | After round 1 | After the gap round |
| --- | --- | --- |
| 1940, 1960 and 1980 eras | descriptions only | the same, plus "Exact population counts or percentage breakdowns are not found" |
| Italians, decline | "declined rapidly after 1980; today 9.5% of NTA ancestry responses" | adds "by 2000, only 188 foreign-born Italian residents remained" (2000 Census) |

The gap round found the 2000 figure and confirmed the pre-2000 gap, which the report then states. Since
then, gap tasks must try something round 1 didn't (another source, other search words, another era)
instead of repeating the same searches.

**Vague and ambiguous questions get clarifying questions.** Clarifier output on the current code:

| Question | Reply |
| --- | --- |
| "Tell me about immigrant neighborhoods" | "Which neighborhood would you like to explore?" Options: Lower East Side, Manhattan (MN0302); Jackson Heights, Queens (QN0301); Belmont, Bronx (BX0603); Sunset Park (West), Brooklyn (BK0702) |
| "What was Little Italy like in 1910?" | "Which Little Italy would you like to explore?" Options: SoHo-Little Italy-Hudson Square, Manhattan (MN0201); Belmont, Bronx (BX0603) |
| "Tell me the story of Chinatown" | Options: Chinatown-Two Bridges, Manhattan (MN0301); Sunset Park (Central), Brooklyn (BK0703); Flushing-Willets Point, Queens (QN0707) |
| "What was the Latin Quarter in Paris like in 1900?" | Out of scope: "this app only researches the history of neighborhoods within the five boroughs", with NYC neighborhoods to try instead |
| "How have rents changed in Bushwick since 2010?" | Out of scope: rents and displacement economics, with Bushwick history questions to try instead |

**Citations are checked.** Citation check counts:

| Run | First draft | After one revision |
| --- | --- | --- |
| Little Italy, run 1 | 11 claims, 19 links; 1 link to a URL no tool returned | 0 problems |
| Little Italy, run 2 | 10 claims, 22 links; 0 problems (no revision needed) | |
| Little Italy, run 3 | 25 claims, 41 links; 2 uncited claims | 24 claims, 43 links; 0 problems |
| Sample 1, Little Germany | 62 claims, 81 links; 2 links to URLs no tool returned | 0 problems |
| Sample 2, pushcart markets | 16 claims, 17 links; 0 problems (no revision needed) | |
| Sample 3, Little Odessa | 52 claims, 57 links; 6 links to URLs no tool returned | 2 still failing, marked "(unverified)" |

In sample 3, one of the two claims marked "(unverified)" links
`https://www.nytimes.com/2022/07/19/dining/how-to-spend-a-day-in-brighton-beach`: the NYT search had
returned that URL ending in `.html`, and the writer dropped the ending, so the link doesn't match any
source found in the run. The limit: the check confirms that every cited source exists and was found in
this run, not that it says exactly what the claim says.

**It says what the data can't answer.** Every report ends with "What the records don't show". The
pushcart report says the pages don't show how the markets changed after 1920, how vendor groups were
spread across the neighborhood, or how many vendors worked without a license. The Brighton Beach report
says the 1900-1920 newspapers cover the resort and its trains, not who lived there year-round. Little
Italy's says exact population counts for the Italian community in 1940 and 1960 are absent from the
searched archives.

## Sources and limits

- **Old newspapers stop in 1954.** Chronicling America only has public-domain papers. For NYC that's
  rich before 1923 (the Tribune, the Sun, the Evening World) and thin through the 1940s (some Yiddish
  dailies, the Daily Worker). We checked: 208 NYC pages in 1953–54, none from 1955 on. For 1960, 1980 and
  today the newspaper source is the NYT.
- **The NYT search returns headlines, abstracts and snippets, not full text,** and many old articles have
  only a headline. Its place tags exist only from 1981. The API allows about 500 requests a day, and a run
  makes about 15–30, so heavy use runs out of quota.
- **Census numbers start in 2000.** The 1990 long form isn't in the Census API, and the 2010 census didn't
  ask about ancestry, birthplace or language. Tract boundaries change between decades, so older totals
  for today's neighborhoods are approximate (the report says how well the tracts matched). ACS estimates
  for small groups have large margins of error and are flagged. Census categories don't map neatly onto
  how communities identify themselves: e.g. the ancestry table has no separate entry for most Asian and
  Hispanic origins, so we use birthplace for those.
- **Neighborhoods are 2020 NTAs.** A historic neighborhood like Koreatown is a few blocks of a larger NTA
  (Midtown South), so its census figures cover the whole NTA; the report says so.
- **NYPL's openly available material skews old**, and coverage of any one block is hit or miss.
- **Landmark records only cover designated buildings and historic districts.** One district's report
  (East Village/Lower East Side, LP-02491) is missing from the city's dataset; we link it by hand.
- **Coverage varies a lot by neighborhood**, and the ~1960 era is thin almost everywhere. Thinly
  documented places get thinner answers, by design.
- **Historic sources reflect the biases of their time.** The agent reports what they show in neutral
  terms and quotes offensive wording only where it's itself the evidence.
- **It's slow, and the time limit trades some depth for speed.** A loc.gov newspaper search takes about
  30 seconds, and NYT requests are spaced 6 seconds apart on one shared key. Each researcher gets 90
  seconds, then reports what it has, so a full run takes about 5 minutes; on a day the archives are slow,
  researchers find less. The NYT key also has a daily request limit: once it's used up, researchers
  skip the NYT until it resets, and the reports lean on the other sources.

## Run it locally

1. A GCP project with billing and the Vertex AI API enabled, then `gcloud auth application-default login`.
2. A `.env` file in this folder (it's in `.gitignore`) with:

   ```bash
   CENSUS_API_KEY=...      # https://api.census.gov/data/key_signup.html (activate it from the email)
   NYT_API_KEY=...         # https://developer.nytimes.com, with the Article Search API enabled
   NYPL_API_KEY=...        # https://api.repo.nypl.org/sign_up
   VERTEXAI_PROJECT=...    # your GCP project ID
   ```

3. `uv run app.py`, then open <http://localhost:8000>.

The server listens on the port in the `PORT` environment variable (8000 if unset), which is how Cloud Run
runs it.

## Deploying

Same as Project 1: Cloud Run continuous deployment from this GitHub repo, built by Google's buildpacks
from `pyproject.toml` and `uv.lock` (no Dockerfile), region `europe-west1`. On the service:

- the four `.env` values as environment variables, with the three API keys stored in Secret Manager;
- the service account has the Vertex AI User role;
- request timeout raised to 900 s (the default 300 s cuts off a full run);
- max instances 1, because the context panel and pending clarifications are kept in memory.

## Team

Gabriella Chu (gc3203).
