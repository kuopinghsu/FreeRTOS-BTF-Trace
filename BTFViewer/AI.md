# AI Assistant

Setup, tools, diagrams, Desktop vs Web, troubleshooting, and CLI details for the BTF Viewer **AI** tab.

For day-to-day panel usage (templates, Apply/Skip, Analysis dialog buttons), see the [user guide → AI Assistant](README.md#ai-assistant). Ask-order playbooks: [WORKFLOWS.md §7](WORKFLOWS.md#7-ai-assistant-flow).

---

## Contents

| Section | |
|---------|--|
| [How it works](#how-it-works) | Context, evidence, investigation plan |
| [Endpoints and models](#endpoints-and-models) | Ollama / cloud, context size, local models |
| [GUI tools](#gui-tools) | Tool schema and Apply / Undo |
| [Diagrams](#diagrams) | Mermaid and tables in replies |
| [Desktop vs web](#desktop-vs-web) | Parity matrix |
| [Troubleshooting](#troubleshooting) | CORS, auth, TLS, timeouts |
| [Opening the web app from `file://`](#opening-the-web-app-from-file) | Ollama CORS for disk pages |
| [CLI regression gate](#cli-regression-gate) | Headless `analyze` |

---

## How it works

The **AI** tab answers diagnostic questions using structured **Analysis Findings** and summary metrics—not the raw `.btf` event stream. That keeps the prompt compact (token-efficient) and analysis fast. The Trace Compare template sends those tables instead of Findings.

When a question needs granular per-task time-series, the model can call `query_raw_metric` to pull a scoped series on demand (still never the raw BTF file). `search_timeline` locates STI / tag / task timestamps like Find. `trigger_compare` returns Trace Compare CSV when two tabs are open. `investigate` builds a structured investigation graph (hypotheses, evidence chain, suggested tools) for one Analysis Finding. Query-only batches (`query_raw_metric`, `search_timeline`, `trigger_compare`, `investigate`) run immediately; mixed GUI batches wait for **Apply** unless **Auto-apply GUI actions** is on.

Important conclusions should cite evidence (`jump:TIME`, metric names) and state **confidence** (High / Medium / Low) plus evidence quality (Directly observed / Strong correlation / Possible explanation / Insufficient evidence). The system prompt asks the model not to invent numbers absent from findings, tool results, or Trace Compare tables.

**Investigate / Root cause / What-if / Optimize / Diagnostic report** show an **Investigation plan** checklist in the AI panel (steps advance as tools run; the final text reply marks remaining steps done). Analysis Findings may include anomaly rows (WCET Max≫Avg spikes, extreme migration bursts).

Natural-language timeline questions (e.g. “find STI wait around TaskA”) are answered via **`search_timeline`** — no separate search UI.

Recommended ask order ([WORKFLOWS.md §7](WORKFLOWS.md#7-ai-assistant-flow)): triage overall findings → **Investigate** / **Root cause** when you want tool-driven drill-down → named metric templates → mitigations after the timeline agrees. Prefer the built-in templates; they already name the metrics and units.

---

## Endpoints and models

Any OpenAI-compatible endpoint works, including Ollama (`http://localhost:11434/v1`). Chat requests time out after 120s (**Stop** still cancels sooner). Give the endpoint at least an **8k** context window so a full Findings card plus a tool round still fits.

**Local models:** the shipped Ollama default is `phi4-mini:3.8b` (light triage). For reliable native function calling prefer `qwen2.5:7b` / `qwen2.5:14b` or `llama3.1:8b` (or larger). 3B-class models often skip tools and emit ` ```btftool ` fences instead.

**Import presets:** [`examples/ai`](examples/ai/README.md) ships [`ollama.json`](examples/ai/ollama.json), [`gemini.json`](examples/ai/gemini.json), [`openai.json`](examples/ai/openai.json), [`deepseek.json`](examples/ai/deepseek.json), [`grok.json`](examples/ai/grok.json), and [`presets.json`](examples/ai/presets.json). Imported values fill **Settings → AI**; review and confirm to save. Each preset keeps its own base URL, model, key, auth mode, and TLS flag.

Keys may also come from the environment as `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `OLLAMA_API_KEY` (`VITE_*` prefixed on the web). A local Ollama endpoint needs no key.

---

## GUI tools

The model may call several tools in one turn; they apply as a single batch. With **Auto-apply GUI actions** off (default in **Settings → AI**), each mutating batch shows **Apply** / **Skip** and **Undo**, plus **Apply GUI actions** under the log. Read-only `query_raw_metric` / `search_timeline` / `trigger_compare` / `investigate` batches run immediately (no Apply card).

| Tool | Parameters / targets | Effect |
|------|----------------------|--------|
| `set_cursors` | `timestamps` (1–8 trace times) | Place cursors (enables **Limit to C1–Cn** when two or more) |
| `zoom_to_range` | `start_time`, `end_time` | Focus the timeline between two times |
| `highlight_task` | `task_name_or_id` (display name, numeric id, or merge key) | Lock-highlight a task row. Unknown names are ignored so the timeline is not dimmed. Empty string clears. |
| `set_view_mode` | `mode` (`task` / `core`); optional `orientation` | Switch Task or Core view; horizontal or vertical |
| `open_corridor_inspector` | optional `core_from` / `core_to` (`Core_0`, `0`, `c0`, `Core 0`) | Open Migration Inspector; aliases resolve the same way |
| `add_annotation` | `time`, `note` (≤240 chars) | Pin an orange timeline note at a timestamp (stays on the current right-panel tab) |
| `query_raw_metric` | `task`, `metric` (`priority_inheritance`, `execution`, `migrations`, `blocking`, `sync`, `findings`) | Read-only: return the per-task series for the current Statistics scope (up to 40 rows) |
| `export_report` | optional `format` (`html` / `csv`) | Download HTML or CSV bundling Analysis Findings, mermaid diagrams from the chat, annotations, and GUI state (cursors / highlight / view). |
| `clear_marks` | optional `what` (`annotations` / `cursors` / `bookmarks` / `all` / `everything`) | Clear AI clutter. `all` (default) drops annotations + cursors; `everything` also clears bookmarks |
| `reset_view` | (none) | Fit the timeline to the full span and clear the task highlight (marks stay) |
| `search_timeline` | `query`; optional `mode` (`contains` / `exact` / `regex` / `sti` / `tags` / `intervals` / `lifecycle` / `pointers` / `migrations`) | Find-panel search; returns matching timestamps (up to 40) |
| `trigger_compare` | optional `tab_a` / `tab_b` (0-based tab index or filename) | Read-only Trace Compare CSV + open the compare dialog (needs two loaded tabs) |
| `investigate` | optional `finding_id`, `depth` (1–5) | Read-only: structured investigation graph (hypotheses, evidence chain, suggested tools) for one Analysis Finding |

Models without native tool calling can emit a fenced ` ```btftool ` JSON block (same cards). Prefer a tool-capable model (see [Endpoints and models](#endpoints-and-models), or `gpt-4o` / Gemini) if native calls stay silent.

After **Apply**, **Undo last actions** restores zoom / view / highlight / inspector / marks; **Ctrl/Cmd+Z** also reverts cursors and marks.

---

## Diagrams

Replies may include ` ```mermaid ` **sequence** diagrams (mutex take/give, block/resume, priority boost / L/M/H) and `graph LR` / **flowchart** core-migration graphs (counts on edges). Pipe **Markdown tables** (and a sanitized HTML `<table>` copied from Findings) render as HTML tables in the reply pane.

- Click a **task** node to lock-highlight that timeline row (`Low[266] (Core 0)` resolves to `Low[266]`).
- Click a **core** node (`Core_0`, `C0`, `C1`) to switch to Core View and scroll to that core.
- Mutex hex and other unresolved labels do nothing (the timeline stays undimmed).
- Click empty figure area to open a larger zoom window (scroll to zoom 0.5–6×; **Esc** or **Close**). Trackpad pinch is treated as scroll.
- The link row under the figure has the same targets.
- **Save As…** HTML keeps inline SVG with clickable nodes (chat zoom wrappers are omitted).

---

## Desktop vs web

| Area | Desktop | Web |
|------|---------|-----|
| Native tools + ` ```btftool ` | Same schema and cards | Same |
| `add_annotation` / `query_raw_metric` / `export_report` | Marks + scoped series + save dialog | Same (browser download) |
| `clear_marks` / `reset_view` / `search_timeline` / `trigger_compare` / `investigate` | Same | Same (compare overlay; search uses Find; investigate is read-only) |
| `highlight_task` / corridor cores | Same resolve rules | Same |
| In-chat mermaid figure | Data-URI image + node hit-test | Inline SVG node clicks |
| In-chat Markdown / HTML tables | Same rendered table | Same |
| Zoom window + link row | Scroll to zoom + link row | Same |
| Authentication | Settings → AI → None / API key / Sign in; panel chip + 401 CTAs until a successful turn | Same (`VITE_*` env keys) |
| Self-signed TLS | **Allow self-signed TLS** per preset skips HTTPS certificate checks | Persist the same flag + tip; browsers still verify — trust the cert, use `http://`, or use Desktop |
| Model picker | Editable combo; refresh fills and opens the dropdown | Same |
| Fonts | **pt** | **px** |
| Endpoint from `file://` | N/A | CORS — prefer Vite proxy, or [Opening the web app from `file://`](#opening-the-web-app-from-file) |

---

## Troubleshooting

| Symptom | Cause | Try |
|---------|-------|-----|
| Web: Failed to fetch / CORS | Browser blocked a cross-origin call (`file://` sends `Origin: null`) | Prefer `npm run dev` / `make preview` (both proxy Ollama), or see [Opening the web app from `file://`](#opening-the-web-app-from-file) |
| 401 / 403 | Missing or rejected key / origin | Settings → AI → Sign in or API key (`OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY`; local Ollama needs none) |
| `CERTIFICATE_VERIFY_FAILED` / self-signed TLS | Private CA or self-signed HTTPS gateway | Desktop: Settings → AI → **Allow self-signed TLS**. Web: trust the cert in the OS/browser, use `http://` on a private LAN, or use the Desktop app |
| Chat probe timed out / `The read operation timed out` | `GET /models` lists ids only; inference is slow or hung | **Test connection** POSTs `/chat/completions` (non-streaming, 120s). Warm the model (`ollama run MODEL`) and retry. Debug with the curl probe below; if curl hangs too, the gateway's chat upstream is stuck. Try `"stream": true` if non-stream never returns. Lower context length on a VRAM-tight local host. |
| Model not found | Typed id is not served | Refresh the Model list (or Test connection) and pick a served id from the dropdown, or `ollama pull` it |
| Gemini HTTP 400 `thought_signature` | Gemini 3 requires a thought blob on tool follow-ups | Retry the question — the viewer echoes Gemini thought signatures |
| Raw ` ```btftool ` JSON instead of native tool calls | Model lacks (or skips) function calling | Same cards either way — **Apply** or enable **Auto-apply GUI actions**. Switch to `qwen2.5:7b` / `llama3.1:8b` / `gpt-4o` / Gemini for native calls |
| Ask times out (over 120s) or stays on Waiting… | Cold start, CPU offload, or VRAM spill | **Stop**, warm with `ollama run MODEL`, retry. Use **Clear** between long threads. Smaller model or shorter Statistics scope if the Findings card is huge |
| Later turns ignore earlier facts | Chat history exceeded the context window | **Clear** on the AI bar, or **Analysis → Query with AI…** for a fresh scoped prompt |

Same body the viewer sends for **Test connection** (replace `BASE`, `MODEL`, and `KEY`):

```bash
curl -vk --max-time 180 \
  -H "Authorization: Bearer KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MODEL","stream":false,"messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":8}' \
  BASE/chat/completions
```

---

## Opening the web app from `file://`

A page opened straight from disk sends `Origin: null`, which Ollama rejects with
`403` — the browser then reports only `Failed to fetch`. Serving the app over
http avoids this entirely (`npm run dev` / `make preview` proxy Ollama for you),
and the Desktop app is not affected at all.

To keep using `file://`, allow every origin on the Ollama side:

```bash
# Server started from a terminal
OLLAMA_ORIGINS="*" ollama serve

# macOS menu-bar app (Ollama.app) — a shell variable does not reach it
launchctl setenv OLLAMA_ORIGINS "*"   # then quit Ollama and reopen it
```

Verify the change took effect; expect `200` and an `Access-Control-Allow-Origin`
header:

```bash
curl -s -D - -o /dev/null -H "Origin: null" http://localhost:11434/v1/models \
  | grep -iE "^HTTP|access-control-allow-origin"
```

If a `file://` page is still refused, list the null origin explicitly with
`OLLAMA_ORIGINS="*,null"`. Note that `*` lets **any** page you visit reach your
local models; undo it with `launchctl unsetenv OLLAMA_ORIGINS` when done.

---

## CLI regression gate

Desktop headless CI can compare a candidate trace to a baseline and optionally ask the configured AI for a short narrative:

```bash
python builds/btf_viewer.py analyze candidate.btf --baseline baseline.btf --fail-on-regression
python builds/btf_viewer.py analyze candidate.btf --save-baseline /tmp/base.json
python builds/btf_viewer.py analyze candidate.btf --baseline /tmp/base.json --fail-on-regression --ai
```

See also [Export → Headless CLI](README.md#headless-cli-desktop-only) in the user guide.
