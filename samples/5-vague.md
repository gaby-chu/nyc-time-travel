# Take me to an immigrant neighborhood I've never heard of

Sample query 5 in the [README](../README.md#sample-queries). Same question, two ways:

1. Neighborhood Time Machine (run 2026-11-16): 6 s; the Clarifier only, 4 tool calls.
2. Gemini 3.5 Flash with no tools and no system prompt.

---

## 1. Neighborhood Time Machine

The whole reply:

> Which of these historic New York immigrant neighborhoods would you like to explore?
> - Belmont, Bronx
> - Kensington, Brooklyn
> - Brighton Beach, Brooklyn
> - Jackson Heights, Queens

---

## 2. Gemini 3.5 Flash, no tools, no system prompt

`vertex_ai/gemini-3.5-flash` (the model behind the agent's Clarifier, Lead and Writer), sent only the question.
Excerpts; the full answer was about 860 words, with no sources.

> We are not going to New York, Los Angeles, or Miami.
> 
> Instead, pack a heavy coat, because I am taking you to the icy, wind-whipped streets of the Twin Cities—specifically to the neighborhood of **Frogtown in Saint Paul, Minnesota**, home to the largest concentrated population of **Hmong** people in the United States.

With no system prompt the model doesn't know the question is about New York, so it leaves the city entirely. The agent stays in scope and asks which neighborhood, offering four that its Clarifier checked against the official NYC neighborhood list.
