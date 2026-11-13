# Neighborhood Time Machine — Project Brief (Deep Research path)

This file tells Claude Code what we're building, which sources to use, and how to adapt the
`wikipedia-deep-research` reference into this project. Read it fully before changing code.
Items marked **VERIFY** were not confirmed against live docs — check them before relying on them.
This project is the **Deep Research** path only. Do not add Text2SQL or Evals-path machinery.

---

## 1. What we're building

A multi-agent deep research system that lets someone "time travel" through any NYC neighborhood:
what it looked like in past eras, which immigrant groups settled there and when, and what traces
of those communities remain today — reconstructed from public historical records, with every claim
cited and every gap stated.

### Scope statement (use in the README and on the front end)

> For any New York City neighborhood, reconstruct what it looked like across eras, which immigrant
> communities settled there and when they arrived, peaked and moved on, and what traces of them
> remain — using historic newspapers, NYT coverage, historic photos and maps, landmark records and
> census data — and say clearly what the records can't show.

### The three question types

| Type | Example | Main evidence | Report format |
|---|---|---|---|
| **1. Then & now** | "What did the Lower East Side look like in 1910 vs. 1940 vs. today?" | NYPL photos/maps, tax-photo links (~1940, ~1985), newspaper descriptions, NYT | One card per era |
| **2. Who settled, and when** | "Which immigrant groups settled in Sunset Park, and when?" | Chronicling America + NYT (narrative), Landmarks reports, Census 2000–today (numbers) | Settlement timeline table: group, arrived, peak, declined/moved, evidence |
| **3. What remains** | "What traces of Little Germany are left in the East Village?" | Landmarks records, today's Census, NYT, NYPL | List of surviving traces + what's gone |

A broad question ("Tell me the story of Chinatown") runs all three.

### In scope
- Any NYC neighborhood, using NYC Department of City Planning's official Neighborhood Tabulation
  Areas (NTAs) as the canonical list. Users can type informal names; the Clarifier translates them
  (from its own knowledge) into an official NTA name or a street address there, and code checks it (§4.6).
- 1850s → today, organized around era anchors: **~1900–1920, ~1940, ~1960, ~1980, today**
  (~1960 added by the user). No Census numbers before 2000 and no tax photos between ~1940 and ~1985,
  so ~1960 rests mostly on NYT (headlines + abstracts) and landmark records. Probe for the Lower East
  Side, 1955–65: NYT 5 articles, Chronicling America 0, NYPL 0. Expect ~1960 to be a thin era and say so.

### Out of scope (the system says so politely)
- Places outside the five boroughs.
- Business turnover, commercial rents, storefront replacement, displacement economics. (Another
  class project covers storefront turnover; keep this project about **settlement history and
  identity**, and keep Census use to ancestry / birthplace / language, not rent or income.)
- Genealogy or information about specific private individuals.

### Data sources the project deliberately does NOT use
- Wikipedia, general web search, historic Census files before 1990 (NHGIS), Mapillary (optional
  stretch only), NYC 311.

---

## 2. Assignment requirements (checklist — every item must be satisfied)

General (all projects):
- [ ] **Unique dataset or question** — question domain: immigrant settlement history and traces.
      User adds the entry to the course sign-up sheet.
- [ ] **Uses data the model doesn't already know deeply** — block-/neighborhood-level history in
      1900s newspapers, NYPL items, landmark reports, tract-level census figures.
- [ ] **Gets at data through tools** — API tools for every source (§4–5).
- [ ] **Combines evidence into a supported claim** — Writer synthesizes across sources; a code citation check (no model) verifies every claim cites a URL the tools returned.
- [ ] **States if the data can't answer** — "What the records don't show" section is mandatory;
      thin eras/neighborhoods are reported, not papered over.
- [ ] **Shows its work** — keep the **`/chat` response shape from Project 1**. Sub-agent tool calls
      go in `tool_calls` too, each with an `agent` field (§8). ASK the user for the Project 1 shape
      if it isn't in this repo — do not invent it.
- [ ] **Front end** says what the agent explores, who it's for, and how to use it (§9).
- [ ] **Deployed to Google Cloud Run** (§10).

Deep Research path:
- [ ] **At least three agent shapes with different jobs** — Clarifier, Lead, Researcher, Writer (the Clarifier stays a separate agent and the citation check is code, not an agent: both user's choice).
- [ ] **Lead fans out to several Researchers in one turn; they run in parallel in fresh contexts.**
- [ ] **Lead goes back for more when findings leave a gap, up to a turn cap.**
- [ ] **Vague input questions require clarification.**
- [ ] **Output is accurately cited.**

---

## 3. The reference: `wikipedia-deep-research`

Base the project on this folder and **stay as close to its build as possible**: same files, same
`app.py` layout and mechanics, same dependencies plus only what new sources need (`uv add`). Don't add
build or infrastructure files the reference doesn't have. Two sibling examples exist (`wikipedia-deck-critic`,
`wikipedia-deck-researchers`); don't copy them wholesale — only the two patterns noted below.

### How the reference works (keep these mechanics)
- `app.py`
  - LiteLLM on Vertex AI: `vertex_ai/gemini-3.5-flash` (Lead/Writer), `vertex_ai/gemini-3.5-flash-lite`
    (Researchers). `SETTINGS`: 90 s timeout, 2 retries; `WRITER_SETTINGS`: 240 s, 1 retry (a full report
    takes 2-3 minutes).
  - `Research` dataclass: per-run shared state the model never sees.
  - Tools return a JSON error string on failure instead of raising — **keep for every tool**.
  - `research` function tool: enforces a researcher cap in code, clones the Researcher with a number
    (`Researcher 3`), runs it with `Runner.run` in a **fresh context**, appends findings to shared
    state. Several `research` calls in one Lead turn run concurrently.
  - Each researcher has `RESEARCHER_SECONDS` (90): after that every research tool answers "time's up"
    and it reports what it has (`out_of_time`). The Lead waits for a round's slowest researcher, so this
    is what keeps a run near 5 minutes. loc.gov calls give up after 2 tries of 20 s.
  - Lead: plan → `research` ×N in the same turn → check gaps → more `research` (capped) → `DONE`.
  - Writer: sees only the question + findings (+ shared timeline); keeps links; bans filler words.
  - FastAPI: `/` serves `index.html`; `/run` streams SSE from a queue fed by hooks; cancels on disconnect.
- `context_panel.py` / `context-panel.js`: per-agent exact contexts. Keep it — it visually proves parallel fresh
  contexts. `context-panel.js` was changed (user's choice) to draw one notebook card per agent inside the page
  (`#context-home`) instead of a fixed sidebar timeline; `context_panel.py` is unchanged.
- `wikipedia.py`: **delete**, but copy its structure (plain functions, truncation, `__main__` smoke
  test) for every new source module.
- `index.html`: rewrite (§9). `pyproject.toml`/`uv.lock`/`.gitignore`: keep, `uv add` new deps.
- Keys live in `.env` only (user's choice): no `.env.example`. `.env` stays in `.gitignore`.
  `.Rhistory`: delete.

### Patterns to borrow
- From `wikipedia-deck-researchers` → `review_slide`: a **deterministic code check**. Use its code
  half for the citation check (§6); the LLM half was dropped (user's choice, see §6).
- From `wikipedia-deck-critic` → `is_enabled=...` to **remove a tool once a cap is reached**. Use it to
  remove `research` after the round cap.
- Do NOT use the background-agent pattern: the Lead must see all findings at once to detect gaps.

---

## 4. Data sources (five research sources + three helpers)

Environment variables (`.env` locally; Secret Manager on Cloud Run):
```
CENSUS_API_KEY=
NYT_API_KEY=
NYPL_API_KEY=
```
Chronicling America, NYC Open Data (Landmarks, NTAs) and GeoSearch need no key (an optional
Socrata app token raises NYC Open Data rate limits).

Every source module must: return plain text the model can read; include a `Source: <url>` line per
record; truncate long text (~8–12k chars, ideally around matched terms); return `{"error": ...}` on
failure; set a descriptive User-Agent (no personal email); cache responses on disk/in memory per run.

### Coverage map (why five sources)
```
1850s ─────── 1922 ─────────── 1963 ────────── 2000 ─────────── today
Chronicling America (full text; NYC coverage mostly pre-1923 due to copyright)
NYT Article Search (headline/abstract/lead paragraph, 1851 → today) ─────────────►
NYPL photos & maps (strongest for public-domain, older material) ─────►
Tax-photo links: ~1940 and ~1985 snapshots
Landmarks records: whole life of designated buildings & historic districts ──────►
                                               Census API: 2000, ACS 2010+ ►
```

### 4.1 Chronicling America (Library of Congress) — historic newspapers, full text (no key)
- Since 2025 accessible only through the **loc.gov API** (don't use the legacy chroniclingamerica API).
- Pattern: `https://www.loc.gov/collections/chronicling-america/?dl=page&qs=<terms>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&fo=json`
  Reference: https://libraryofcongress.github.io/data-exploration/loc.gov%20JSON%20API/Chronicling_America/README.html
  **VERIFY** param names, pagination, location filters (city/state), language filters, and how to
  fetch a page's OCR full text.
- Coverage: content is public-domain; a sharp drop after 1922. NYC's major papers are the least
  likely to appear after 1922. Some non-English papers exist — **VERIFY** what NYC-relevant
  foreign-language titles are available.
- OCR is noisy and historic papers contain slurs and stereotypes about immigrant groups (§6 rules).
- Respect rate limits. **RISK:** loc.gov may block some datacenter IPs — test from Cloud Run in M2.

### 4.2 NYT Article Search API — mid-century to today (free key)
- `GET https://api.nytimes.com/svc/search/v2/articlesearch.json?q=<q>&fq=<filter>&begin_date=YYYYMMDD&end_date=YYYYMMDD&page=<n>&api-key=$NYT_API_KEY`
- Coverage: Sept 1851 → today. Returns headline, abstract, lead paragraph, pub_date, web_url,
  keywords (incl. geographic tags) — **not full text**. Cite `web_url`; quote only abstract/lead text.
- Rate limits: about **10 requests/minute, 4,000/day** — **VERIFY**. Implement a shared async
  rate limiter + cache, since parallel researchers will contend for it.
- Use `fq` with geographic keywords (e.g. `glocations:("Chinatown (Manhattan, NY)")`) — **VERIFY** syntax.

### 4.3 NYPL Digital Collections API — historic photos and maps (free token)
- `GET https://api.repo.nypl.org/api/v2/items/search?q=<q>&publicDomainOnly=true`
  Header: `Authorization: Token token="$NYPL_API_KEY"`
- Return title, date, collection, item UUID and the public item page
  (`https://digitalcollections.nypl.org/items/<uuid>`) — **VERIFY** URL pattern and response fields.
- **Link to images; don't copy them** into the app. Prefer public-domain items.
- Good queries: street names + "street scene", neighborhood names, "tenement", historic map titles.

### 4.4 NYC Landmarks Preservation Commission (NYC Open Data) — what remains (no key)
- **Individual Landmark and Historic District Building Database** (`7mgd-s57w`): building-by-building
  info from LPC designation reports (architect, style, construction date, original use, etc.).
- **Individual Landmark Sites** (`buis-pvji`) and **Historic Districts** boundaries — **VERIFY** IDs.
- Designation report PDFs (rich narrative history, often including the district's immigrant
  history): linked from LPC's site; a common pattern is `http://s-media.nyc.gov/agencies/lpc/lp/<LP#>.pdf`
  — **VERIFY**. Extract text with `pypdf`, truncate around matched terms, cite the PDF URL + page.
- Socrata pattern: `https://data.cityofnewyork.us/resource/<id>.json?$where=...`

### 4.5 Census API — 2000 to today (free key)
- Base `https://api.census.gov/data/...` with `&key=$CENSUS_API_KEY`. NYC = state `36`, counties
  `005` (Bronx), `047` (Kings/Brooklyn), `061` (New York/Manhattan), `081` (Queens), `085` (Richmond).
- Use **tract-level** data aggregated to the neighborhood (§4.6). Topics: **ancestry, place of birth
  of the foreign-born, language spoken at home** only.
  - ACS 5-year, 2010–2024 (verified; 2009 dropped because data.census.gov, which citations link to,
    doesn't have it; the API itself needs a key, so API URLs can't be cited): `B04006` (ancestry), `B05006` (place of birth, foreign-born),
    language `B16001` through 2015 and `C16001` from 2016 (B16001 is blank for tracts from 2016).
  - 2000 Census SF3 at `/data/2000/dec/sf3` (verified): `PCT018` (ancestry), `PCT019` (birthplace).
    2000 language is only published crossed with age, so it isn't used.
  - **No 1990 (or earlier) data (user's decision: Census covers 2000 → today).** The 1990 long form
    isn't in the Census API (its 1990 catalog has only CBP, PEP, CPS, SIPP; 1960–1980 have no datasets
    at all), and NHGIS is excluded. 2010 decennial has no ancestry/birthplace/language — use ACS.
- Tract boundaries change each decade; report figures as approximate when boundaries differ, and say so.
- Margins of error: ACS estimates for small groups are noisy — report MOE or flag "small, uncertain".

### 4.6 Helpers (not research sources — say so in the README)
- **NYC GeoSearch** (`https://geosearch.planninglabs.nyc/v2/search?text=<address>`, no key): address →
  BBL, coordinates, (possibly) tract. **VERIFY** response fields.
- **Neighborhood → tracts**: DCP's 2020 NTA boundaries and NTA↔census-tract equivalency files on NYC
  Open Data: 2020 NTAs `9nt8-h7nd`, 2020 tract↔NTA equivalency `hm78-6dwm` (verified). `uv run geo.py
  build` writes them to `data/ntas.json` (codes, names, tracts, boundaries); the app loads it at startup.
  This is a lookup table, not a database the agent writes SQL against.
- **Informal names: no hand-written alias list** (user's decision). The model knows that "Koreatown"
  is around West 32nd Street; it doesn't reliably know NTA codes. So the Clarifier either passes an
  official NTA name to `resolve_neighborhood`, or a street address with a house number and borough
  (e.g. "10 West 32nd Street, Manhattan") to `neighborhood_at`, which geocodes it and tests it against
  the real NTA boundaries. Its translation is visible in `tool_calls`. GeoSearch can't geocode
  intersections or place names, and returns a closest match even for fake streets, so
  `neighborhood_at` rejects matches on a different street or borough.
- **Tax-photo links**: NYC Municipal Archives has photos of nearly every building ~1940 (720k images)
  and ~1985, searchable by borough/block/lot. Generate a link the user can open; don't scrape images.
  **VERIFY** the current gallery URL/search pattern (the archives have moved platforms).

---

## 5. Tools to implement

One module per source: `census.py`, `loc.py`, `nyt.py`, `nypl.py`, `lpc.py`, plus `geo.py` (helpers),
each with a `__main__` smoke test. Wrap as `@function_tool`s in `app.py`.

| Tool | Used by | Returns |
|---|---|---|
| `resolve_neighborhood(name)` | Clarifier | Candidate NTAs for an official name (code, name, borough) + tracts |
| `neighborhood_at(address)` | Clarifier | The NTA containing a street address + tracts (for informal names) |
| `census_profile(nta_code, year, topic)` | Researchers | Top groups/languages with counts, MOE, tract list, `Source:` API URL |
| `search_old_newspapers(terms, start_year, end_year)` | Researchers | Page hits: paper, date, snippet, URL |
| `read_old_newspaper_page(url)` | Researchers | Truncated OCR text + `Source:` |
| `search_nyt(query, start_year, end_year, place=None)` | Researchers | Articles: headline, date, abstract, lead paragraph, URL |
| `search_nypl(query, start_year=None, end_year=None)` | Researchers | Items: title, date, collection, item URL |
| `search_landmarks(nta_code or bbox, keyword=None)` | Researchers | Landmarks/district buildings: name, date built, original use, report link |
| `read_landmark_report(url, terms)` | Researchers | Truncated report text around terms + page refs |
| `tax_photo_links(address or bbl)` | Researchers (Then & now) | ~1940 and ~1985 photo links (the page shows the archive's thumbnail, or the full scan when there is none) |
| `save_plan(plan)` / `save_timeline(rows)` | Lead | Stores the era × question-type plan and draft timeline in shared state |
| `research(task, era, question_type, hints)` | Lead | Runs one Researcher (§6) |

Rules:
- Every URL in a research tool's result is added to `state.fetched: set[str]` (the citation check
  uses it).
- Cap results per search (≤5) and reads per researcher (≤5, enforced in the prompt and by a counter).

---

## 6. Agents and flow

```
/chat (question [+ clarification answer])
  → CLARIFIER — vague / ambiguous / out of scope? return a question + options, stop.
  → LEAD      — save_plan(eras × question types) → research(...) ×N in ONE turn
                (parallel, fresh contexts) → save_timeline → gaps/contradictions?
                → research again (≤2 more rounds) → DONE
  → WRITER    — report from findings + timeline only
  → CHECK     — code, not an agent: every claim cites a link, every link was returned by a tool;
                one Writer revision, then mark what still fails "(unverified)"
  → response  (report + tool_calls with agent field)
```

### Shared state (extend `Research`)
```python
@dataclass
class Research:
    hooks: PanelHooks
    nta: dict | None = None                  # {"code", "name", "borough", "tracts": {...}}
    question_types: list[str] = field(default_factory=list)   # ["then_now","settlement","remains"]
    eras: list[str] = field(default_factory=lambda: ["1900-1920", "1940", "1960", "1980", "today"])
    researchers: int = 0
    rounds: int = 0
    findings: list[str] = field(default_factory=list)
    plan: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    fetched: set[str] = field(default_factory=set)
    cache: dict[str, str] = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)      # for /chat (§8)
```

### Caps (enforce in code, not just prompts)
- `MAX_RESEARCHERS = 10` per run; `MAX_ROUNDS = 3` (initial + 2 gap rounds).
- Remove `research` via `is_enabled` when `rounds >= MAX_ROUNDS`; the tool also returns
  "No researchers left. Reply DONE." as a backstop. Lead `max_turns` ~15, Researcher ~12.

### Clarifier (new) — structured output
```python
class Clarify(BaseModel):
    ready: bool
    nta_code: str | None
    question_types: list[str] = []    # subset of then_now / settlement / remains
    eras: list[str] = []              # default all five anchors
    group: str | None = None          # e.g. "Italian" if the user named one
    question: str | None = None       # asked when not ready
    options: list[str] = []           # candidate neighborhoods or question choices
    out_of_scope: bool = False
```
Not ready when: no place given ("Tell me about immigrants in NYC"), the name matches several NTAs or
spans several ("Little Italy", "the Village"), the place is outside NYC, or the question is about
storefront turnover/rents/private individuals (out of scope — say why, suggest an in-scope question).
For an informal name, the Clarifier uses its own knowledge to pick a representative street address
for each place the name could mean (e.g. "Little Italy" → 150 Mulberry Street, Manhattan and 2344
Arthur Avenue, Bronx) and calls `neighborhood_at` for each; more than one NTA → not ready, offer them.
A small, well-known place inside a big NTA (Koreatown in Midtown South) → say the NTA is larger, so
census figures are diluted.

### Lead prompt (draft)
```
You lead a research team reconstructing the history of one NYC neighborhood.
You're given the neighborhood (with its census tracts), the question types and eras to cover.
1. Save a plan with save_plan: one row per (question type × era) worth researching.
2. Call research once per independent task, all in the same turn. Typical split:
   - settlement: one task per era for newspaper/NYT evidence of which groups lived there,
     plus one task for census figures 2000–today;
   - then_now: one task per era for photos/maps/descriptions;
   - remains: one task for landmark records, one for recent coverage of surviving institutions.
   Give each a specific task, era, and search hints (street names, group names, institutions).
3. Read the findings and save a timeline (save_timeline): for each group, arrival / peak / decline
   with the evidence for each, and for each era what the place looked like.
4. If an era has no evidence, or two sources disagree (e.g. newspapers vs. census), call research
   again for just that gap with new search terms (nearby streets, institution names, other spellings).
5. When everything the sources allow is covered, reply DONE and nothing else.
```

### Researcher prompt (draft)
```
You research one task about one NYC neighborhood in one era, using the tools you have.
Search first, then read the most relevant results. Read at most 5 items.
Reply with at most 8 bullets of facts that answer your task. Each bullet ends with its source link
and, where possible, a short exact quote (under 20 words) or the census figure with its year.
Use only what the sources say — never outside knowledge. If the sources don't answer part of the
task, say so in a last bullet, and name the searches you tried.
Historic sources may use slurs or stereotypes: report what they show in neutral terms; only quote
offensive wording if it is itself the evidence, and mark it as the source's language.
```

### Writer prompt (draft)
```
Write the report in markdown using only the timeline and findings you're given.
- One-paragraph overview answering the question.
- Then & now (if requested): one section per era — what it looked like, what was happening,
  photo/map links.
- Who settled, and when (if requested): a table — Group | Arrived | Peak | Declined/moved | Evidence.
  Mark each date "documented", "approximate", or "not found".
- What remains (if requested): surviving buildings, institutions, names, and what's gone.
- "What the records don't show": thin eras, missing groups, approximate census boundaries.
- Every factual sentence and table row ends with a link from the findings.
- Plain, specific, respectful sentences about communities; present-day group names; no stereotypes;
  no "vibrant", "rich tapestry", "melting pot", "it is worth noting".
```

### Citation check (code only — no Checker agent, user's choice)
An LLM Checker was built and dropped: on test runs it flagged many correct claims (including a Census
figure checked by hand), so it added cost and noise without catching real errors.
1. **Code check (`checker.py`, no model):** every table row / factual sentence / bullet has a link;
   every linked URL is in `state.fetched`. Flag anything uncited or citing an unfetched URL.
   Gap sections ("What the records don't show") and short lead-ins are exempt.
2. On failures: one Writer revision with the problems listed; anything still failing is marked
   "(unverified)". Record the counts (`state.checks`) for the README. Python controls this loop
   (pattern: `wikipedia-deck-critic/call_loop.py`).
3. **Limit (say so in the README):** this checks that cited sources exist and came from this run,
   not that they say what the claim says.

---

## 7. README must demonstrate (Deep Research requirements)

No eval suite is required for this path, but the README must show evidence for each requirement:
- **Parallel fan-out in fresh contexts:** shown in text from a run's log (≥3 researchers started in one
  Lead turn, with their start and finish times); no screenshot (user's choice).
- **Gap loop:** one trace where a thin era or a newspaper/census contradiction triggers a second round
  (show the before/after timeline).
- **Clarification:** a vague question ("Tell me about immigrant neighborhoods") and an ambiguous name
  ("Little Italy") returning options; one out-of-scope request handled politely.
- **Accurate citations:** citation-check counts on the demo runs (first check vs after revision); an
  example of a claim marked unverified; the limit in §6 (existence, not meaning).
- **States what data can't answer:** a thinly documented neighborhood run with an honest gaps section.
- Demo set (6–8 neighborhoods): mix of well-documented (e.g. Lower East Side, Chinatown, Little Italy)
  and thinner ones (e.g. a Queens or Staten Island neighborhood), across all three question types.
- Sources and their limits (§12), and the note that GeoSearch/NTA lookups/tax-photo links are helpers.

---

## 8. `/chat` endpoint (Project 1 response shape)

- `/chat` must keep the **exact response shape from the user's Project 1** (`pam/app.py`, confirmed
  by the user):
  ```python
  class ChatRequest(BaseModel):
      message: str
      session_id: str | None = None

  class ChatResponse(BaseModel):
      response: str
      session_id: str
      tool_calls: list[dict]   # each {"name", "args", "result"} — add "agent" here
  ```
- Content: the final report markdown + a `tool_calls` list with **every tool call from every agent**,
  each with an `agent` field (`"Clarifier"`, `"Lead"`, `"Researcher 3"`, `"Writer"`),
  the tool name, arguments, and a truncated result.
- Collect calls with a `RunHooks` subclass (extend `PanelHooks`) — `on_tool_start`/`on_tool_end` give
  `agent.name`. **VERIFY** how the installed `openai-agents` version exposes tool arguments in hooks;
  if not available, derive them from `AgentContexts` events (they store each agent's `tool_calls`).
- Clarification across requests (built in M8): `/chat` keeps only the pending clarification per
  `session_id` in memory (`pending`: original question + question asked), like pam's sessions. The
  next message on that session is the answer. If it's gone (a new Cloud Run instance), the message
  is treated as a new question, which still works because options name the neighborhood and NTA code.
  `/run` (SSE) is fully stateless: the page sends question, asked, answer. `/clear` drops a session.
- A clarifying response is the question plus one `- option` line per option. Out-of-scope replies
  aren't kept pending.
- A full run takes 5–8 minutes (M8 test: 488 s). Cloud Run's default request timeout is 300 s: raise
  it (e.g. 900 s) when deploying (§10).
- Keep `/run` (SSE) + context panel as an optional live view for demos.

---

## 9. Front end (`index.html`)

- Intro (required): **what** it explores (how NYC neighborhoods looked across eras, which immigrant
  communities settled there and when, what remains), **who** it's for (New Yorkers, students,
  history fans, anyone curious about their neighborhood), **how** to use it (name a neighborhood and
  ask one of the three kinds of question, or "tell me its story").
- One question box; the Clarifier finds the neighborhood. Clarification options render as buttons.
- Example-question buttons, including one vague question to demo clarification.
- Results: era cards (with photo/map links), the settlement timeline table, the "what remains" list,
  and the "what the records don't show" section. Render markdown tables.
- "The Newsroom": one card per agent with its byline, its notebook (the context panel) and its `tool_calls`.
- No scope-and-limits text on the page (user's choice): the Clarifier turns away out-of-scope questions,
  and the README's "Sources and limits" section states the limits. Five example questions (user's choice).

---

## 10. Deploying to Cloud Run

Deploy **exactly the way `pam` was deployed**: Cloud Run continuous deployment from the GitHub repo
(`gaby-chu/nyc-time-travel`), set up in the GCP console, with Google's buildpacks building from
`pyproject.toml` + `uv.lock`. Use the same region as `pam` (`europe-west1`).

- **No `Dockerfile`, `.dockerignore`, or `Procfile`.** Don't add build files the reference and `pam`
  don't have. Only revisit this if a buildpack build actually fails, and ask the user first.
- The only code change from the reference: copy `pam`'s `__main__` block (bind `0.0.0.0`, read
  the `PORT` env var, default 8000). The reference binds `127.0.0.1:8000`.
- `.env` stays out of the build because it's in `.gitignore` and the deploy comes from the repo.
- Vertex AI auth: same as `pam` — the Cloud Run service account needs **Vertex AI User**; no
  `gcloud auth` in the container. LiteLLM needs `VERTEXAI_PROJECT=agentic-gc3203` (verified
  locally: without it LiteLLM used the gcloud default project `capstone` and got 403). It's in `.env`;
  set the same env var on the Cloud Run service. Location is already set in code (`vertex_location: global`).
- Secrets (new vs. `pam`, which needed no keys): `CENSUS_API_KEY`, `NYT_API_KEY`, `NYPL_API_KEY`
  in **Secret Manager**, exposed to the service as env vars via the console.
- In the service settings: raise the request timeout (default 5 min; multi-round runs can exceed
  it) and set max instances to 1 for the demo (in-memory panel/sessions); `/chat` must not depend on them.
- Rate limiting: one shared limiter for NYT across concurrent researchers; cache all API responses.
- Deploy the **unchanged** reference first (M1).

---

## 11. Build order (milestones with acceptance checks)

- **M1 — Baseline deploy.** Reference runs locally, then on Cloud Run via GitHub continuous
  deployment, set up the same way as `pam` (§10). Only change: `pam`'s `PORT`/`0.0.0.0` `__main__` block.
  No Wikimedia credentials (user's choice): the check is that the deployed page loads, not a research run.
- **M2 — Source modules + helpers.** `census.py`, `loc.py`, `nyt.py`, `nypl.py`, `lpc.py`, `geo.py`, each
  with a passing smoke test locally **and** one call tested from Cloud Run (loc.gov/NYT risk).
- **M3 — Hand trace.** Answer "Who settled in the Lower East Side, and when?" by calling the tools
  directly. ✔ evidence for ≥3 groups across ≥3 eras; note which eras are thin.
- **M4 — Agents, question type 2 first ("who settled, and when").** Swap tools in; new Lead/Researcher/
  Writer prompts; shared state; caps. ✔ ≥3 researchers in parallel in one Lead turn; a gap round fires.
- **M5 — Add question types 1 (then & now) and 3 (what remains).**
- **M6 — Clarifier.** ✔ vague → options; ambiguous name → options; out-of-scope → polite refusal.
- **M7 — Citation check.** ✔ code check catches an uncited row and an unfetched URL (`uv run checker.py`);
  one Writer revision; "(unverified)" marking; counts recorded. (LLM Checker dropped, §6.)
- **M8 — `/chat` in the Project 1 shape** with all sub-agent tool calls tagged by `agent`. ✔ clarify → answer → report over HTTP; out-of-scope reply; every call has agent/name/args/result.
- **M9 — Front end** text, clarification buttons, era cards, show-work panel. ✔ intro/scope text, example
  questions, markdown via marked + DOMPurify (as in pam), era cards from the Writer's fixed `## Then & now` /
  `### <era>` headings, "unverified" marks, citation-check line, Show work grouped by agent; works at phone width.
- **M10 — Final deploy + README** (§7 evidence, sources and limits).

---

## 12. Known limitations to state in the README
- Chronicling America's NYC coverage is rich before 1923, thin to 1954, and empty from 1955 (checked:
  208 NYC pages in 1953-54, 0 after; copyright). NYT search returns headlines, abstracts and snippets
  (no lead paragraphs any more), not full text; ~500 requests/day.
- Census numbers start in 2000 (1990 isn't in the Census API; the 2010 census didn't ask these
  questions); tract boundaries change between decades, so neighborhood totals are
  approximate; ACS estimates for small groups have large margins of error; census categories don't
  map neatly onto how communities identify themselves.
- NYPL's openly available material skews older; coverage of any one block is hit-or-miss.
- Landmark records only cover designated buildings and historic districts.
- Coverage varies a lot by neighborhood; thinly documented places get thinner answers, by design.
- Historic sources reflect the biases of their time; the system reports them, it doesn't endorse them.
