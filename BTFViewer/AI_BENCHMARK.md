# AI Benchmark results

Generated: 2026-08-14 (Gemini 3.6 Flash 08:33–08:35 UTC; Gemma 4 26B 07:43 UTC; Gemini 3.1 Flash-Lite 07:13 UTC)
Dataset: `tests/ai` (7 expected-facts cases)
Host: Apple Silicon, 32 GB unified memory

```bash
python builds/btf_viewer.py ai-test --dataset tests/ai --models compared --fail-under 0 -o AI_BENCHMARK.md
python builds/btf_viewer.py ai-test --dataset tests/ai --models gemini --fail-under 0 -o AI_BENCHMARK.md
# or: make -C BTFViewer ai-test-live
#     make -C BTFViewer ai-test-live AI_MODELS=gemini
```

Plan and scoring rules: [AI.md → Benchmark / evaluation suite](AI.md#benchmark-suite).

`--models compared` is `qwen3.5:9b,qwen3.5:27b,gemma4:26b` (local Ollama). `--models gemini` is `gemini-3.6-flash,gemini-3.1-flash-lite` (Google OpenAI-compat. Live Gemini runs now execute a tool-result follow-up when the first turn is tools-only.

**Takeaway:** **`qwen3.5:9b` (82**, 6/7, 10.7s) is the recommended local investigator. **`gemini-3.1-flash-lite` (81**, 6/7, 5.5s) leads among cloud models scored with the tool follow-up. **`gemini-3.6-flash` (75**, 6/7, ~9s) is a real follow-up score (free-tier 429 split the run). `qwen3.5:27b` **80** / 6/7 and `gemma4:26b` **80** / 5/7 are slower local alternatives. Do not use 3B-class models for investigation.

Live `--models` scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model. PASS is overall ≥ 70.

## Offline fixture scorer

Run `2026-08-14-015819` — no live model.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 98**

## Comparison

| Model | Category | Overall | Pass | Mean latency |
|---|---|---:|---:|---:|
| `qwen3.5:9b` | Local / practical | **82** | **6/7** | 10.7s |
| `qwen3.5:27b` | Local / high-quality | 80 | 6/7 | 64.4s |
| `gemma4:26b` | Local / high-quality | 80 | 5/7 | 72.6s |
| `gemini-3.6-flash` | Cloud | **75** | **6/7** | ~9s |
| `gemini-3.1-flash-lite` | Cloud / fast | **81** | **6/7** | 5.5s |

| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |
|---|---:|---:|---:|---:|---:|---:|
| `qwen3.5:9b` | **79** | **86** | **100** | 57 | 80 | **100** |
| `qwen3.5:27b` | 71 | 71 | **100** | 71 | 80 | 94 |
| `gemma4:26b` | 71 | 57 | **100** | **86** | 80 | 91 |
| `gemini-3.6-flash` | — | — | — | — | — | — |
| `gemini-3.1-flash-lite` | **79** | 64 | **100** | **71** | 80 | **100** |

## Live models

### `qwen3.5:9b`

Local / practical. Run `2026-08-14-015819`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| mutex_contention | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 82**

Mean latency: **10.7s** / case.

### `qwen3.5:27b`

Local / high-quality. Run `2026-08-14-015819`; `explain_region` re-run `2026-08-14-0714` after the chain-of-thought follow-up.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| mutex_contention | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 82 | 50 | 100 | 100 | 100 | 80 | 60 | FAIL |

**Overall 80**

Mean latency: **64.4s** / case (original seven-case mean). `explain_region` re-run was 89s. Still FAIL: the follow-up conclusion cited out-of-window `jump:57` / `jump:950` / `jump:2050`.

### `gemma4:26b`

Local / high-quality. Run `2026-08-14-0743` with tool-result follow-up (the published **59** was the earlier single-turn run).

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 68 | 0 | 50 | 100 | 100 | 80 | 100 | FAIL |
| mutex_contention | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 78 | 100 | 0 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 69 | 100 | 100 | 100 | 0 | 80 | 40 | FAIL |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 80**

Mean latency: **72.6s** / case. Remaining FAILs: `migration_thrash` refused to name migration/thrash without more metrics (68); `load_imbalance` wrote `Task[5]` (invented vs `Hot[5]`) so safety 40.

### `gemini-3.6-flash`

Cloud. Run `2026-08-14-083304` with tool-result follow-up; free-tier 429 after four cases, remaining three at `2026-08-14-083511`. `migration_thrash` parts from a later retry (`2026-08-14-0836`, 9.3s); the other three first-window cases still have overall only (retry 429/503).

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| mutex_contention | 88 | — | — | — | — | — | — | PASS |
| priority_inversion | 88 | — | — | — | — | — | — | PASS |
| deadline_miss | 78 | — | — | — | — | — | — | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 70 | 50 | 50 | 50 | 100 | 80 | 100 | PASS |
| explain_region | 43 | 0 | 50 | 67 | 0 | 80 | 100 | FAIL |

**Overall 75**

Mean latency: **~9s** / case. PASS 6/7. `explain_region` 43 (thin catalog; no finding keywords). Do not treat this as worse than Flash-Lite 81 — Flash-Lite had a full seven-case part dump in one window.

### `gemini-3.1-flash-lite`

Cloud / fast. Run `2026-08-14-071240` with tool-result follow-up (empty first turn → host catalog tool result → text conclusion).

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 81**

Mean latency: **5.5s** / case.
