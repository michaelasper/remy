"""Simple web UI for interacting with the Remy planning API."""

from __future__ import annotations

import html
import json

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

SAMPLE_CONTEXT = {
    "date": "2025-01-01",
    "prefs": {"diet": "omnivore", "max_time_min": 30, "allergens": []},
    "recent_meals": [],
    "inventory": [
        {"id": 1, "name": "chicken thigh, boneless", "qty": 600, "unit": "g"},
        {"id": 2, "name": "broccoli", "qty": 400, "unit": "g"},
    ],
    "leftovers": [],
    "constraints": {"attendees": 2, "time_window": "evening"},
}

ESCAPED_SAMPLE_CONTEXT = html.escape(json.dumps(SAMPLE_CONTEXT, indent=2))

HTML_PAGE = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Remy Dinner Planner</title>
    <style>
      :root {{
        color-scheme: light dark;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}

      body {{
        margin: 0;
        display: flex;
        flex-direction: column;
        min-height: 100vh;
      }}

      header {{
        padding: 1.5rem;
        background: #1f2933;
        color: #f5f7fa;
      }}

      header h1 {{
        margin: 0 0 0.25rem 0;
        font-size: 1.75rem;
      }}

      main {{
        flex: 1;
        padding: 1.5rem;
        display: grid;
        gap: 1.5rem;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        background: #f8fafc;
      }}

      section {{
        background: white;
        border-radius: 0.75rem;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        display: flex;
        flex-direction: column;
        gap: 1rem;
      }}

      textarea {{
        width: 100%;
        min-height: 320px;
        font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.9rem;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #cbd5e1;
        resize: vertical;
        background: #0b0f19;
        color: #f5f7fa;
      }}

      button {{
        cursor: pointer;
        border: none;
        border-radius: 0.5rem;
        padding: 0.75rem 1rem;
        background: #2563eb;
        color: white;
        font-size: 1rem;
        font-weight: 600;
        transition: background 0.15s ease;
      }}

      button:hover {{
        background: #1d4ed8;
      }}

      pre {{
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font-size: 0.9rem;
        line-height: 1.4;
        background: #0b0f19;
        color: #f5f7fa;
        padding: 1rem;
        border-radius: 0.5rem;
        flex: 1;
        overflow: auto;
        max-height: 420px;
      }}

      .status {{
        font-size: 0.95rem;
        min-height: 1.5rem;
      }}

      footer {{
        padding: 1rem 1.5rem;
        text-align: center;
        background: #1f2933;
        color: #9aa5b1;
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>Remy Dinner Planner</h1>
      <p>Craft dinner plans from your pantry inventory and preferences.</p>
    </header>
    <main>
      <section>
        <h2>Planning Context JSON</h2>
        <p>Paste or tweak a planning context. Press “Generate Plan” to call the API.</p>
        <textarea id="context-input" spellcheck="false">{ESCAPED_SAMPLE_CONTEXT}</textarea>
        <div>
          <button id="generate-btn">Generate Plan</button>
        </div>
        <div class="status" id="status"></div>
      </section>
      <section>
        <h2>Plan Response</h2>
        <pre id="plan-output">// Waiting for plan…</pre>
      </section>
    </main>
    <footer>
      Remy API · POST <code>/plan</code>
    </footer>
    <script>
      const input = document.getElementById("context-input");
      const output = document.getElementById("plan-output");
      const statusEl = document.getElementById("status");
      const button = document.getElementById("generate-btn");

      async function fetchPlan() {{
        let payload;
        try {{
          payload = JSON.parse(input.value);
        }} catch (error) {{
          statusEl.textContent = "Invalid JSON: " + error.message;
          statusEl.style.color = "#dc2626";
          return;
        }}

        statusEl.textContent = "Requesting plan…";
        statusEl.style.color = "#1f2933";
        button.disabled = true;

        try {{
          const response = await fetch("/plan", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json"
            }},
            body: JSON.stringify(payload)
          }});

          const text = await response.text();
          if (!response.ok) {{
            statusEl.textContent = `Error: ${{response.status}} ${{response.statusText}}`;
            statusEl.style.color = "#dc2626";
            output.textContent = text;
            return;
          }}

          const data = JSON.parse(text);
          output.textContent = JSON.stringify(data, null, 2);
          statusEl.textContent = "Plan generated successfully.";
          statusEl.style.color = "#16a34a";
        }} catch (error) {{
          statusEl.textContent = "Request failed: " + error;
          statusEl.style.color = "#dc2626";
          output.textContent = "";
        }} finally {{
          button.disabled = false;
        }}
      }}

      button.addEventListener("click", fetchPlan);
    </script>
  </body>
</html>
"""

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def ui_home() -> str:
    """Serve the Remy web UI."""

    return HTML_PAGE
