// Context panel: shows the message list the server sends to the model on every turn.
// Include with <script src="/context-panel.js"></script>, then call showContext(sessionId).
// The panel goes inside the page element with id "context-home" if there is one, else at the end of the body.
//
// Several agents: store an AgentContexts on the server (see context_panel.py) and call
// showContext(sessionId) on every change. The panel draws one notebook per agent, side by side and
// wrapping onto new rows, each with that agent's messages in order. Agents that work at the same time
// (parallel researchers) open their notebooks at the same time. A sub-agent's fresh context starts with
// only its own messages; messages copied from another agent's conversation are dimmed and say whose they
// are. The notebook that changed last is marked active. The page can fill in each notebook's heading
// by defining window.labelNotebook(agent, headElement). resetContext() empties the panel for a new run.

const contextStyle = document.createElement("style");
contextStyle.textContent = `
    #context-panel { font-family: ui-monospace, monospace; font-size: 0.75rem; }
    #context-panel h2 { font-family: system-ui, sans-serif; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; color: #999; margin-bottom: 1rem; }
    /* Several agents: one notebook per agent, wrapping onto new rows */
    .ctx-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr)); gap: 1rem; align-items: start; }
    .notebook { min-width: 0; }
    .ctx-head { font-family: system-ui, sans-serif; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; color: #999; padding: 0.5rem 0; border-top: 3px solid transparent; }
    .notebook.active .ctx-head { color: #000; border-top-color: #000; }
    /* A notebook's pages scroll on their own once they're long, so one busy agent doesn't stretch the page */
    .ctx-pages { max-height: 34rem; overflow-y: auto; }
    .ctx-note { font-family: system-ui, sans-serif; color: #999; padding: 0.2rem 0.75rem; margin-bottom: 0.5rem; }
    .ctx-note.divider { border-top: 1px solid #ccc; padding-top: 0.5rem; }
    .context-msg {
        border-left: 3px solid #999;
        padding: 0.4rem 0.75rem;
        margin-bottom: 0.5rem;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .context-msg .role { font-weight: bold; }
    .context-msg.system { border-color: #dc2626; }
    .context-msg.user { border-color: #16a34a; }
    .context-msg.assistant { border-color: #2563eb; }
    .context-msg.tool { border-color: #f59e0b; }
    .context-msg.new { animation: context-flash 1.5s; }
    .context-msg.thinking { border-color: #ccc; color: #aaa; }
    .context-msg summary { cursor: pointer; color: #666; }
    .context-msg.copied { opacity: 0.55; }
    @keyframes context-flash { from { background: #fef3c7; } }
`;
document.head.appendChild(contextStyle);

const contextPanel = document.createElement("div");
contextPanel.id = "context-panel";
(document.getElementById("context-home") || document.body).appendChild(contextPanel);

const CONTEXT_FOLD = 1500; // longer messages (a fetched article, say) fold to their start
const TIMELINE_FOLD = 700; // tighter in a notebook

let contextShown = 0; // single agent: how many messages were already shown
let contextQueue = Promise.resolve(); // one fetch at a time, so events arrive in order
let timeline = null; // several agents: built on the first timeline response

function showContext(sessionId) {
    contextQueue = contextQueue.then(() => loadContext(sessionId)).catch((e) => console.error(e));
    return contextQueue;
}

function resetContext() {
    contextShown = 0;
    timeline = null;
    contextPanel.className = "";
    contextPanel.innerHTML = "";
}

async function loadContext(sessionId) {
    const after = timeline ? timeline.seq : 0;
    const res = await fetch("/context?session_id=" + encodeURIComponent(sessionId) + "&after=" + after);
    if (!res.ok) return; // a failed poll: keep what's shown, the next one may work
    const data = await res.json();
    if (Array.isArray(data)) {
        // A server that doesn't know this run answers [] (another instance, or one that restarted).
        // Once notebooks are drawn, keep them rather than wiping them for an empty single context.
        if (timeline) return;
        renderSingle(data);
    } else renderTimeline(data.events);
}

// --- One agent: the message list ---

function renderSingle(messages) {
    contextPanel.innerHTML = "<h2>Context (" + messages.length + " messages)</h2>";
    messages.forEach((m, i) => {
        const isNew = i >= contextShown; // highlight what this turn added
        // Hidden thinking gets its own grayed-out block: it isn't sent back to the model
        if (m.thinking) contextPanel.appendChild(contextBlock("thinking", m.thinking, isNew));
        // Tool-call turns have no text, so show the calls instead
        contextPanel.appendChild(contextBlock(m.role, m.content ?? formatToolCalls(m.tool_calls), isNew));
    });
    contextShown = messages.length;
}

// --- Several agents: one notebook each ---

function renderTimeline(events) {
    if (!timeline) {
        const grid = document.createElement("div");
        grid.className = "ctx-grid";
        contextPanel.innerHTML = "";
        contextPanel.className = "timeline";
        contextPanel.appendChild(grid);
        timeline = { grid, seq: 0, notebooks: {}, pages: {}, count: {} };
    }
    let last = null;
    for (const e of events) {
        if (e.seq < timeline.seq) continue; // already drawn
        timeline.seq = e.seq + 1;
        if (!timeline.notebooks[e.agent]) addNotebook(e.agent);
        last = e.agent;
        const cell = timelineCell(e);
        if (cell) addPage(e.agent, cell);
    }
    if (!last) return;
    // Mark the notebook that changed last
    for (const [agent, notebook] of Object.entries(timeline.notebooks)) notebook.classList.toggle("active", agent === last);
}

function addNotebook(agent) {
    const notebook = document.createElement("div");
    notebook.className = "notebook";
    notebook.dataset.agent = agent;
    const head = document.createElement("div");
    head.className = "ctx-head";
    head.textContent = agent;
    if (window.labelNotebook) window.labelNotebook(agent, head);
    const pages = document.createElement("div");
    pages.className = "ctx-pages";
    notebook.append(head, pages);
    timeline.grid.appendChild(notebook);
    timeline.notebooks[agent] = notebook;
    timeline.pages[agent] = pages;
    timeline.count[agent] = 0;
}

function addPage(agent, cell) {
    const pages = timeline.pages[agent];
    // Follow new pages, unless the reader has scrolled up in this notebook
    const atBottom = pages.scrollTop + pages.clientHeight >= pages.scrollHeight - 40;
    pages.appendChild(cell);
    timeline.count[agent] += 1;
    if (atBottom) pages.scrollTop = pages.scrollHeight;
}

function timelineCell(e) {
    if (e.type === "message") {
        const m = e.message;
        const block = contextBlock(m.role, m.content ?? formatToolCalls(m.tool_calls), true, TIMELINE_FOLD);
        if (e.from) {
            // Another agent wrote this: this context shares that agent's conversation
            block.classList.add("copied");
            block.querySelector(".role").textContent += " (from " + e.from + ")";
        }
        return block;
    }
    // A fresh context: an agent's first needs no divider
    if (e.type !== "context" || !timeline.count[e.agent]) return null;
    const note = document.createElement("div");
    note.className = "ctx-note divider";
    note.textContent = "new context (" + e.total + " messages)";
    return note;
}

// --- Shared ---

// name(key: value, ...), with string values printed as text so a markdown argument stays readable.
// Takes LiteLLM's {function: {name, arguments}} calls or a flat {name, arguments}.
function formatToolCalls(calls) {
    return (calls ?? [])
        .map((call) => {
            const name = call.name ?? call.function?.name;
            let args = call.arguments ?? call.function?.arguments;
            if (typeof args === "string") {
                try {
                    args = JSON.parse(args);
                } catch {}
            }
            const lines =
                args && typeof args === "object"
                    ? Object.entries(args).map(([k, v]) => k + ": " + (typeof v === "string" ? v : JSON.stringify(v, null, 2)))
                    : [String(args ?? "")].filter(Boolean);
            if (!lines.length) return name + "()";
            return name + "(\n" + lines.map((l) => "  " + l.replaceAll("\n", "\n  ")).join("\n") + "\n)";
        })
        .join("\n");
}

function contextBlock(label, text, isNew, fold = CONTEXT_FOLD) {
    const div = document.createElement("div");
    div.className = "context-msg " + label + (isNew ? " new" : "");
    const role = document.createElement("div");
    role.className = "role";
    role.textContent = label;
    div.appendChild(role);
    if (text.length > fold) {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = text.slice(0, 300) + "... (" + text.length + " characters)";
        details.append(summary, text);
        div.appendChild(details);
    } else {
        div.append(text);
    }
    return div;
}
