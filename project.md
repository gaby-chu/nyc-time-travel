Your agent must:

Use data the model doesn't already know deeply.
Get at the data through tools: SQL, files, search, or an API.
Combine evidence into a supported claim.
State if the data can't answer a question.
Show its work. Keep the /chat response shape from Project 1. Sub-agent tool calls go in tool_calls too, with an agent field.
Have a front end that says what the agent explores, who it's for and how to use it.
Be deployed to GCP Cloud Run.


Deep Research
At least three agent shapes with different jobs, for example Lead, Researcher and Writer.
The Lead fans out to several Researchers in one turn, and they run in parallel in fresh contexts.
The Lead goes back for more when the findings leave a gap, up to a turn cap.
Vague input questions require clarification.
The output is accurately cited. 


README
Each agent should come with a README.md that:

Describes the project and who the target user is
Where your data came from and how someone could load it (it’s not strictly necessary that the grader can load it, just that they understand where it came from).
Lists three sample queries for the grader to test with. For each, give the answer you expect and the file, table or API endpoint it comes from.
For each sample query, include the answer from the same model with no tools and no system prompt, next to your agent's answer. This will help us measure the effectiveness of how your agent uses the information even if the model already knows the domain.