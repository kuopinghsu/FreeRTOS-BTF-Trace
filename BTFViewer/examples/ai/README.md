# AI settings import files

**Settings → AI → Import…** (Desktop and Web) loads an endpoint configuration
from a JSON file, so a team can share a working setup without retyping URLs.
Copy one of these files, fill in your key, and import it.

| File | Endpoint |
|------|----------|
| [`gemini.json`](gemini.json) | Google Gemini via its OpenAI-compatible API |
| [`openai.json`](openai.json) | OpenAI (`api.openai.com`) |
| [`deepseek.json`](deepseek.json) | DeepSeek (`api.deepseek.com`) — imports as **Custom** |
| [`grok.json`](grok.json) | xAI Grok (`api.x.ai`) — imports as **Custom** |

## Fields

| Field | Meaning |
|-------|---------|
| `preset` | `ollama`, `openai`, `gemini`, or `custom`. Other vendor names such as `deepseek` import as `custom`. Omit it and the preset is inferred from `base_url`. |
| `base_url` | OpenAI-compatible API root. A bare host gains `/v1`, and Ollama's native `/api` root is corrected automatically. |
| `model` | Model id served by that endpoint. **Test connection** lists what the endpoint serves. For Gemini prefer the rolling aliases (`gemini-flash-lite-latest`, `gemini-flash-latest`) — pinned versions differ per account and are retired over time. |
| `api_key` | Optional. Leave empty to use `OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY` from the environment (`VITE_*` on the web), which keeps keys out of shared files. |
| `response_language` | Optional reply language for the assistant. |

Key names may also be camelCase (`baseUrl`, `apiKey`, `responseLanguage`), so a
file written for either app works in both.

To carry several endpoints in one file, nest them under `presets` and name the
one to select:

```json
{
  "preset": "ollama",
  "presets": {
    "ollama": { "base_url": "http://localhost:11434/v1", "model": "phi4-mini:3.8b" },
    "gemini": { "model": "gemini-flash-lite-latest" }
  }
}
```

Importing fills the Settings fields but does not save on its own — review the
values, run **Test connection**, then confirm the dialog. Only the presets named
in the file are touched; the others keep their stored settings.
