# AI settings import files

**Settings → AI → Import…** (Desktop and Web) loads an endpoint configuration
from a JSON file, so a team can share a working setup without retyping URLs.
Copy one of these files, fill in your key if needed, and import it.

A preset name that is not already in the combo (for example `deepseek` or
`grok`) is **added to the list**. Built-in names (`ollama`, `openai`, `gemini`,
`custom`) keep their existing slots. Only the presets named in the file are
touched; the others keep their stored settings.

| File | Endpoint | Lands on |
|------|----------|----------|
| [`ollama.json`](ollama.json) | Local Ollama (`localhost:11434/v1`). Default id `qwen3.5:9b` (≥8k context) | **Ollama** |
| [`gemini.json`](gemini.json) | Google Gemini OpenAI-compatible API | **Google Gemini** |
| [`openai.json`](openai.json) | OpenAI (`api.openai.com`) | **OpenAI** |
| [`deepseek.json`](deepseek.json) | DeepSeek (`api.deepseek.com`) | **DeepSeek** (added if missing) |
| [`grok.json`](grok.json) | xAI Grok (`api.x.ai`) | **Grok** (added if missing) |
| [`presets.json`](presets.json) | Ollama + OpenAI + Gemini + DeepSeek + Grok at once | **Ollama** selected |

After import: review **Authentication**, paste a key or use **Sign in…** (opens the vendor page; paste the issued token), refresh the **Model** dropdown, then **Test connection**. Confirm the Settings dialog to save.

## Fields

| Field | Meaning |
|-------|---------|
| `preset` | `ollama`, `openai`, `gemini`, `custom`, or any new letter-led id (`deepseek`, `grok`, …). Unknown names are added to the preset list. Synonyms of the builtins still fold (`chatgpt` → OpenAI, `google` → Gemini). Omit it and the preset is inferred from `base_url`. |
| `label` | Optional combo label for an extra preset (`DeepSeek`). Defaults to a title-cased id. |
| `base_url` | OpenAI-compatible API root. A bare host gains `/v1`, and Ollama's native `/api` root is corrected automatically. |
| `model` | Model id served by that endpoint. Refresh the **Model** list (dropdown) or **Test connection** to see what the endpoint serves. For Gemini prefer the rolling aliases (`gemini-flash-lite-latest`, `gemini-flash-latest`) — pinned versions differ per account and are retired over time. For Grok / DeepSeek, pick a served id after refresh. |
| `api_key` | Optional. Leave empty (`""`) to use Settings or `OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY` (same order on Desktop and Web). Custom names such as `CURSOR_API_KEY` are not read in the GUI — paste that key on the preset. See [README → API keys](../README.md#ai-api-keys). |
| `auth_mode` | Optional. `none` (local), `api_key`, or `browser` (`sign_in` / `oauth` also accepted). Controls Settings → **Authentication**. Use `none` for local Ollama, `api_key` to paste a provider key, `browser` when the user should **Sign in…** first. Example files include a `//` line comment above this field. |
| `tls_verify` | Optional. `true` (default) verifies the HTTPS certificate. Set `false` (or `insecure_tls: true`) for a self-signed / private-CA gateway. Desktop then skips certificate checks; browsers still verify — trust the cert, use `http://`, or use the Desktop app. |
| `response_language` | Optional reply language for the assistant. |
| `enabled` | Optional. Settings → **Enable AI Assistant**. |
| `auto_apply` | Optional. Settings → **Auto-apply GUI actions**. |
| `context_mode` | Optional. Settings → **Context**: `compact`, `balanced` (default), or `full` (`full evidence` also accepted). |
| `redact_task_names` | Optional. Settings → **Anonymize task names for cloud** (`anonymize_task_names` also accepted). |
| `trace_sensitive` | Optional. Settings → **Treat this trace as sensitive**. |
| `mcp_log` | Optional. Desktop Settings → **Log MCP messages to file**. |

Omitted checkbox keys are left unchanged. Key names may also be camelCase (`baseUrl`, `apiKey`, `authMode`, `responseLanguage`, `aiEnabled`), so a file written for either app works in both. Whole-line `//` comments are ignored on import (so `https://` inside strings is safe).

To carry several endpoints in one file, nest them under `presets` and name the
one to select — see [`presets.json`](presets.json):

```json
{
  "preset": "ollama",
  "enabled": true,
  "auto_apply": false,
  "presets": {
    "ollama": { "base_url": "http://localhost:11434/v1", "model": "qwen3.5:9b", "auth_mode": "none" },
    "deepseek": { "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash", "auth_mode": "api_key" }
  }
}
```

Importing fills the Settings fields but does not save on its own — review the
values, run **Test connection**, then confirm the dialog.

## Live benchmark suite (XML)

[`benchmark.xml`](benchmark.xml) is **not** a Settings import file. It
configures Desktop `ai-test`:

```bash
python builds/btf_viewer.py ai-test -c examples/ai/benchmark.xml -o AI_BENCHMARK.md
python builds/btf_viewer.py ai-test -c examples/ai/benchmark.xml --compare-context -o AI_BENCHMARK.md
python builds/btf_viewer.py ai-test -c examples/ai/benchmark.xml --insecure
make ai-test-context
```

| Element | Meaning |
|---------|---------|
| `<base-url>` | OpenAI-compatible API root (suite default or per `<model>`) |
| `<model id="…">` | Live model id to score |
| `<tls-verify>` | `false` (shipped default) skips checks for a self-signed / private-CA cert; `true` verifies the HTTPS certificate. CLI `--insecure` forces false. |
| `<api-key env="VAR">` | Desktop `ai-test` only: read `VAR` from the environment; if unset, use the element text, then the three shared names. Leave the text empty and do not commit secrets. GUI chat does not use `env`. [README → API keys](../README.md#ai-api-keys). |
| `<timeout-s>` | Per-request timeout |
| `<preset>` | Optional (`gemini` for Gemini OpenAI-compat) |

| `--compare-context` | Run Compact, Balanced, and Full evidence; compare score, tokens, and latency |
| `--context-mode` | Single mode: `compact`, `balanced`, or `full` (default `full`) |

`--models id1,id2` (or `make ai-test-context AI_MODELS=id1,id2`) runs a subset of the XML list. A custom copy may mark models `optional="true"` so they are skipped when their key is missing unless you name them. `--only-cases id1,id2` (or `AI_CASES=id1,id2`) scores a subset of the dataset — useful for re-running a few cases that came back `ERROR`. When `-o` already exists, a narrowed run like this **merges** into it (only the rerun models/context-modes/cases change; everything else is untouched) — pass `--replace-report` (`AI_REPLACE=1`) to overwrite fully instead. Context-mode flags: [AI.md → Context mode benchmarking](../AI.md#context-mode-benchmarking). Full suite: [Benchmark / evaluation suite](../AI.md#benchmark-suite).
Setup, tools, and troubleshooting: [AI.md](../AI.md).

Panel usage: [BTFViewer README → AI Assistant](../README.md#ai-assistant).
