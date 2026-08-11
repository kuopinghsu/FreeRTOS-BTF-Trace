# AI settings import files

**Settings → AI → Import…** (Desktop and Web) loads an endpoint configuration
from a JSON file, so a team can share a working setup without retyping URLs.
Copy one of these files, fill in your key if needed, and import it.

| File | Endpoint | Lands on |
|------|----------|----------|
| [`ollama.json`](ollama.json) | Local Ollama (`localhost:11434/v1`). Default id `phi4-mini:3.8b`; for native tool calling prefer `qwen2.5:7b` / `llama3.1:8b` (≥8k context) | **Ollama** |
| [`gemini.json`](gemini.json) | Google Gemini OpenAI-compatible API | **Google Gemini** |
| [`openai.json`](openai.json) | OpenAI (`api.openai.com`) | **OpenAI** |
| [`deepseek.json`](deepseek.json) | DeepSeek (`api.deepseek.com`) | **Custom** |
| [`grok.json`](grok.json) | xAI Grok (`api.x.ai`) | **Custom** |
| [`presets.json`](presets.json) | Ollama + OpenAI + Gemini + Custom at once | **Ollama** selected |

After import: review **Authentication**, paste a key or use **Sign in…** (opens the vendor page; paste the issued token), refresh the **Model** dropdown, then **Test connection**. Confirm the Settings dialog to save. Only the presets named in the file are touched; the others keep their stored settings.

## Fields

| Field | Meaning |
|-------|---------|
| `preset` | `ollama`, `openai`, `gemini`, or `custom`. Other vendor names such as `deepseek` / `grok` / `xai` import as `custom`. Omit it and the preset is inferred from `base_url`. |
| `base_url` | OpenAI-compatible API root. A bare host gains `/v1`, and Ollama's native `/api` root is corrected automatically. |
| `model` | Model id served by that endpoint. Refresh the **Model** list (dropdown) or **Test connection** to see what the endpoint serves. For Gemini prefer the rolling aliases (`gemini-flash-lite-latest`, `gemini-flash-latest`) — pinned versions differ per account and are retired over time. For Grok / DeepSeek, pick a served id after refresh. |
| `api_key` | Optional. Leave empty (`""`) to use `OPENAI_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_API_KEY` from the environment (`VITE_*` on the web), which keeps keys out of shared files. |
| `auth_mode` | Optional. `none` (local), `api_key`, or `browser` (`sign_in` / `oauth` also accepted). Controls Settings → **Authentication**. Use `none` for local Ollama, `api_key` to paste a provider key, `browser` when the user should **Sign in…** first. Example files include a `//` line comment above this field. |
| `tls_verify` | Optional. `true` (default) verifies the HTTPS certificate. Set `false` (or `insecure_tls: true`) for a self-signed / private-CA gateway. Desktop then skips certificate checks; browsers still verify — trust the cert, use `http://`, or use the Desktop app. |
| `response_language` | Optional reply language for the assistant. |

Key names may also be camelCase (`baseUrl`, `apiKey`, `authMode`, `responseLanguage`), so a file written for either app works in both. Whole-line `//` comments are ignored on import (so `https://` inside strings is safe).

To carry several endpoints in one file, nest them under `presets` and name the
one to select — see [`presets.json`](presets.json):

```json
{
  "preset": "ollama",
  "presets": {
    "ollama": { "base_url": "http://localhost:11434/v1", "model": "phi4-mini:3.8b", "auth_mode": "none" },
    "gemini": { "model": "gemini-flash-lite-latest", "auth_mode": "api_key" }
  }
}
```

Importing fills the Settings fields but does not save on its own — review the
values, run **Test connection**, then confirm the dialog.

Panel usage: [BTFViewer README → AI Assistant](../README.md#ai-assistant).
Setup, tools, and troubleshooting: [AI.md](../AI.md).
