# Who has called Sunset Park home over the last century?

Sample query 4 in the [README](../README.md#sample-queries). Same question, two ways:

1. Neighborhood Time Machine (run 2026-11-16): 285 s; 1 round, 6 researchers, 35 tool calls; 34 links in the report, 7 claims marked "(unverified)".
2. Gemini 3.5 Flash with no tools and no system prompt.

---

## 1. Neighborhood Time Machine

The agent asked first:

> Sunset Park is divided into a few official sections. Which part would you like to focus on?
> - Sunset Park (West), Brooklyn
> - Sunset Park (Central), Brooklyn
> - Sunset Park (East)-Borough Park (West), Brooklyn

Answered with **Sunset Park (West), Brooklyn**. Report:

*Shortened: the first sentence of each paragraph (two for the overview), as the agent wrote them, with their links, plus sentences with the facts the README checks; [...] marks a cut.*

### Overview

Sunset Park (West), Brooklyn, has transitioned over the past century from an industrial, shipping-focused waterfront community populated largely by Scandinavian and Irish immigrants into a diverse neighborhood with major East Asian and Latin American enclaves. (unverified) In the early 1900s, the construction of the massive Bush Terminal and the Brooklyn Army Terminal transformed the local shoreline, attracting tens of thousands of European workers who lived in the neighborhood's newly constructed stone and brick row houses. (unverified) By the turn of the twenty-first century, Sunset Park West had evolved into a predominantly Latino and Chinese neighborhood, with Mexican, Dominican, and Chinese residents comprising the largest shares of the foreign-born population. (unverified)

### Then & now

#### 1900-1920

In the mid-1880s, the Sunset Park West waterfront was almost completely undeveloped except for the oil refinery of Rufus T. Bush near the 39th Street Ferry ([LPC LP-2622](https://s-media.nyc.gov/agencies/lpc/lp/2622.pdf)). [...] Large numbers of Scandinavian immigrants, particularly Norwegians and Finns, settled in the neighborhood alongside Irish families, Polish, Syrian, Maltese, Greek, and Russian Jewish communities ([LPC LP-2622](https://s-media.nyc.gov/agencies/lpc/lp/2622.pdf)).

#### 1940

In October 1944, the United States Army offered local real estate holdings in the area for sale ([The New York Times, 1944](https://www.nytimes.com/1944/10/24/archives/army-offers-sale-of-local-holdings.html)). [The records of the Sunset Park Civic Association from the 1935–1945 era](https://digitalcollections.nypl.org/items/e4423620-c671-012f-a099-58d385a7bc34) are preserved in the digital collections of the New York Public Library. Researchers searched for detailed population figures for Scandinavian, Irish, and Italian groups and the construction of the Gowanus Parkway during this period but did not find them in the searched archives. (unverified)

#### 1960

The opening of the Verrazano-Narrows Bridge in November 1964 established new bus connections linking Brooklyn's Fourth Avenue BMT 95th Street subway station to Staten Island ([The New York Times, 1964](https://www.nytimes.com/1964/11/08/archives/bus-service-set-for-new-bridge-staten-islandbrooklyn-runs-to-begin.html)). [...] Researchers also looked for specific neighborhood-level accounts of the Sunset Park waterfront, the Gowanus Expressway corridor, and the decline of European populations during this era but did not find them in the searched archives. (unverified)

#### 1980

Immigrant street vendors have been active along Fifth Avenue in Sunset Park for several decades ([The New York Times, 2023](https://www.nytimes.com/2023/09/01/realestate/sidewalk-vendors-brooklyn.html)). Researchers also looked for specific growth figures of Latino and Asian communities in Sunset Park West during the 1980s but did not find detailed results in the searched archives. (unverified)

#### Today

Today, Sunset Park West has a large foreign-born population, with Mexican immigrants making up the largest single group at 25.8%, followed by Dominican immigrants at 14.7% and Chinese immigrants at 14.5% ([ACS 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)). [...]

### Who settled, and when

| Group | Arrived | Peak | Declined/moved | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| Mexicans | Not found | Today (approximate) | Not found | Comprised 24.7% of the foreign-born population in 2000 ([Census 2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047000200,36047001800,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)) and 25.8% today ([ACS 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)). |
| Dominicans | Not found | 2000 (approximate) | After 2000 (approximate) | Comprised 20.3% of the foreign-born population in 2000 ([Census 2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047000200,36047001800,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)) and 14.7% today ([ACS 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)). |
| Chinese | Not found | Today (approximate) | Not found | Comprised 11.1% of the foreign-born population in 2000 ([Census 2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047000200,36047001800,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)) and 14.5% today ([ACS 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)), with continuous arrival streams ([The New York Times, 2024](https://www.nytimes.com/2024/03/06/nyregion/chinese-immigrants-new-york-city.html)). |
| Ecuadorians | Not found | 2000 (approximate) | After 2000 (approximate) | Comprised 9.5% of the foreign-born population in 2000 ([Census 2000](https://data.census.gov/table/DECENNIALSF32000.PCT019?g=1400000US36047000200,36047001800,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)) and 7.6% today ([ACS 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B05006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)). |
| Scandinavians (Norwegians/Finns) | 1900-1920 (documented) | Not found | Not found | Settled in large numbers in Sunset Park during the early twentieth century ([LPC LP-2622](https://s-media.nyc.gov/agencies/lpc/lp/2622.pdf)). |
| Irish | 1900-1920 (documented) | Not found | Not found | Settled alongside Scandinavians during early growth ([LPC LP-2622](https://s-media.nyc.gov/agencies/lpc/lp/2622.pdf)); 6.2% of residents claim Irish ancestry today ([ACS Ancestry 2020-2024](https://data.census.gov/table/ACSDT5Y2024.B04006?g=1400000US36047000200,36047001801,36047001802,36047001803,36047001804,36047002000,36047002200,36047007200,36047007400,36047007600,36047007800,36047008000,36047008200,36047008400,36047010100,36047014300,36047014500,36047014700)). |

### What remains

The physical character of Sunset Park West is anchored by well-preserved turn-of-the-twentieth-century residential blocks. (unverified) [...]

### What the records don't show

The available historical records are notably thin regarding the mid-twentieth-century demographic and physical transition of Sunset Park West. Specifically, neighborhood-level demographic displacement figures and detailed sociological studies from the 1960s are missing, leaving the decline of European populations and the rise of Puerto Rican settlement undocumented in local detail ([Researcher 3 Report]). Similarly, detailed population figures and arrival timelines for Scandinavian, Irish, and Italian residents during the 1940s are not found in the archives ([Researcher 2 Report]). [...]

---

## 2. Gemini 3.5 Flash, no tools, no system prompt

`vertex_ai/gemini-3.5-flash` (the model behind the agent's Clarifier, Lead and Writer), sent only the question.
Excerpts; the full answer was about 700 words, with no sources.

> Sunset Park was once the premier Scandinavian enclave in the United States, particularly for **Finns, Norwegians, and Danes**. [...]
> 
> **Puerto Ricans:** Beginning in the late 1940s and peaking in the 1950s and 60s, Puerto Ricans arrived in large numbers [...]
> 
> In the 1980s, Cantonese immigrants from Manhattan's overcrowded Chinatown began moving to Sunset Park [...] Simultaneously, a massive wave of **Mexican immigrants** (predominantly from the states of Puebla and Guerrero) settled in the western half of the neighborhood

The model knows this story well, and it matches the landmark report: Scandinavians, then Puerto Ricans from the 1950s, then Chinese and Mexican arrivals from the 1980s. It doesn't ask which Sunset Park, gives no numbers, and cites nothing.
