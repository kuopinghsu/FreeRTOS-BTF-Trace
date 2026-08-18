# AI Benchmark results

Generated: 2026-08-18 12:01 UTC
Dataset: `tests/ai`

Live `--config` suite XML scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model.

## Offline fixture scorer

Run `2026-08-18-072735` — no live model.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 98**

## Comparison

| Model | Context | Category | Overall | Pass | Total tok | Mean latency |
|---|---|---|---:|---:|---:|---:|
| `qwen3.5:9b` | Compact | Local / practical | 77 | 9/17 | 75430 | 11.1s |
| `qwen3.5:9b` | Balanced | Local / practical | 85 | 14/17 | 88260 | 16.1s |
| `qwen3.5:9b` | Full evidence | Local / practical | 83 | 12/17 | 88727 | 16.0s |
| `qwen3.8:27b` | Compact | Local / high-quality | 75 | 9/17 | 76787 | 122.7s |
| `qwen3.8:27b` | Balanced | Local / high-quality | 86 | 15/17 | 96490 | 293.6s |
| `qwen3.8:27b` | Full evidence | Local / high-quality | 79 | 9/17 | 86735 | 335.4s |
| `gemini-3.6-flash` | Compact | Cloud | 51 | 2/17 | 60146 | 34.6s |
| `gemini-3.6-flash` | Balanced | Cloud | 77 | 13/17 | 72463 | 53.8s |
| `gemini-3.6-flash` | Full evidence | Cloud | 75 | 11/17 | 71526 | 71.8s |
| `gemini-3.1-flash-lite` | Compact | Cloud / fast | 81 | 13/17 | 70284 | 4.1s |
| `gemini-3.1-flash-lite` | Balanced | Cloud / fast | 83 | 11/17 | 72445 | 3.5s |
| `gemini-3.1-flash-lite` | Full evidence | Cloud / fast | 84 | 14/17 | 74728 | 3.6s |

## Context mode comparison

Same model and dataset; Compact / Balanced / Full evidence packing.

### `qwen3.5:9b`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 77 | 9/17 | 62968 | 12462 | 75430 | 11.1s |
| Balanced | 85 | 14/17 | 68565 | 19695 | 88260 | 16.1s |
| Full evidence | 83 | 12/17 | 69501 | 19226 | 88727 | 16.0s |

### `qwen3.8:27b`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 75 | 9/17 | 64659 | 12128 | 76787 | 122.7s |
| Balanced | 86 | 15/17 | 69307 | 27183 | 96490 | 293.6s |
| Full evidence | 79 | 9/17 | 62076 | 24659 | 86735 | 335.4s |

### `gemini-3.6-flash`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 51 | 2/17 | 58958 | 1188 | 60146 | 34.6s |
| Balanced | 77 | 13/17 | 64123 | 8340 | 72463 | 53.8s |
| Full evidence | 75 | 11/17 | 63245 | 8281 | 71526 | 71.8s |

### `gemini-3.1-flash-lite`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 81 | 13/17 | 63368 | 6916 | 70284 | 4.1s |
| Balanced | 83 | 11/17 | 66203 | 6242 | 72445 | 3.5s |
| Full evidence | 84 | 14/17 | 67966 | 6762 | 74728 | 3.6s |


| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |
|---|---:|---:|---:|---:|---:|---:|
| `qwen3.5:9b (Compact)` | 76 | 75 | 82 | 59 | 80 | 98 |
| `qwen3.5:9b (Balanced)` | 85 | 90 | 100 | 65 | 80 | 96 |
| `qwen3.5:9b (Full evidence)` | 88 | 97 | 83 | 59 | 80 | 92 |
| `qwen3.8:27b (Compact)` | 65 | 69 | 88 | 59 | 80 | 99 |
| `qwen3.8:27b (Balanced)` | 82 | 91 | 94 | 71 | 80 | 99 |
| `qwen3.8:27b (Full evidence)` | 74 | 82 | 91 | 59 | 80 | 96 |
| `gemini-3.6-flash (Compact)` | 29 | 26 | 82 | 24 | 80 | 99 |
| `gemini-3.6-flash (Balanced)` | 76 | 79 | 85 | 53 | 80 | 99 |
| `gemini-3.6-flash (Full evidence)` | 71 | 74 | 88 | 53 | 80 | 95 |
| `gemini-3.1-flash-lite (Compact)` | 79 | 90 | 74 | 65 | 80 | 99 |
| `gemini-3.1-flash-lite (Balanced)` | 79 | 90 | 88 | 65 | 80 | 99 |
| `gemini-3.1-flash-lite (Full evidence)` | 88 | 91 | 82 | 65 | 80 | 99 |

## Live models

### `qwen3.5:9b` — Compact

Local / practical. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_correlation_not_cause | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 80 | 100 | 100 | 0 | 100 | 80 | 80 | FAIL |
| period_jitter | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| waiter_owner_handoff | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 93 | 100 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 77**

Mean latency: **11.1s** / case.

Tokens: **62968** prompt + **12462** completion = **75430** total.

### `qwen3.5:9b` — Balanced

Local / practical. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 69 | 100 | 100 | 100 | 0 | 80 | 40 | FAIL |
| period_jitter | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| waiter_owner_handoff | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 93 | 100 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 85**

Mean latency: **16.1s** / case.

Tokens: **68565** prompt + **19695** completion = **88260** total.

### `qwen3.5:9b` — Full evidence

Local / practical. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 63 | 100 | 100 | 0 | 0 | 80 | 100 | FAIL |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 93 | 100 | 100 | 67 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 62 | 100 | 100 | 50 | 0 | 80 | 40 | FAIL |

**Overall 83**

Mean latency: **16.0s** / case.

Tokens: **69501** prompt + **19226** completion = **88727** total.

### `qwen3.8:27b` — Compact

Local / high-quality. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 53 | 50 | 0 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 70 | 100 | 50 | 0 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 73 | 0 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 75**

Mean latency: **122.7s** / case.

Tokens: **64659** prompt + **12128** completion = **76787** total.

### `qwen3.8:27b` — Balanced

Local / high-quality. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 80 | 100 | 50 | 50 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 80 | 100 | 50 | 50 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 78 | 0 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 48 | 0 | 50 | 100 | 0 | 80 | 100 | ERROR |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 86**

1/17 cases returned an API error (first: OpenAI-compatible request timed out after 360s (http://localhost:11434/v1/chat/completions). Waited 360s for a non-streaming POST /chat/completions (GET /models only lists ids and does not run the model). First load of a large model is ofte).

Mean latency: **293.6s** / case.

Tokens: **69307** prompt + **27183** completion = **96490** total.

### `qwen3.8:27b` — Full evidence

Local / high-quality. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 94 | 100 | 100 | 75 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | ERROR |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 54 | 50 | 50 | 75 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 48 | 0 | 50 | 100 | 0 | 80 | 100 | ERROR |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 62 | 0 | 100 | 125 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 54 | 100 | 100 | 0 | 0 | 80 | 40 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 98 | 100 | 100 | 100 | 100 | 80 | 100 | ERROR |
| stats_page_next_check | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| response_vs_blocking | 48 | 0 | 0 | 167 | 0 | 80 | 100 | ERROR |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 79**

4/17 cases returned an API error (first: OpenAI-compatible request timed out after 360s (http://localhost:11434/v1/chat/completions). Waited 360s for a non-streaming POST /chat/completions (GET /models only lists ids and does not run the model). First load of a large model is ofte).

Mean latency: **335.4s** / case.

Tokens: **62076** prompt + **24659** completion = **86735** total.

### `gemini-3.6-flash` — Compact

Cloud. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| mutex_contention | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| priority_inversion | 78 | 100 | 0 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 38 | 0 | 0 | 100 | 0 | 80 | 100 | FAIL |
| load_imbalance | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| trace_regression | 53 | 50 | 0 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 23 | 0 | 0 | 0 | 0 | 80 | 100 | ERROR |
| adversarial_exec_vs_preemption | 38 | 0 | 0 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_correlation_not_cause | 28 | 0 | 0 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 65 | 50 | 100 | 100 | 0 | 80 | 80 | FAIL |
| stats_page_next_check | 68 | 50 | 0 | 100 | 100 | 80 | 100 | FAIL |
| response_vs_blocking | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| preempt_matrix_vs_chain | 33 | 0 | 0 | 67 | 0 | 80 | 100 | ERROR |
| mutex_block_vs_wait_queue | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 51**

4/17 cases returned an API error (first: HTTP 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.).

Mean latency: **34.6s** / case.

Tokens: **58958** prompt + **1188** completion = **60146** total.

### `gemini-3.6-flash` — Balanced

Cloud. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 87 | 100 | 100 | 25 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 87 | 100 | 100 | 25 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 23 | 0 | 0 | 0 | 0 | 80 | 100 | ERROR |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 77**

3/17 cases returned an API error (first: HTTP 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.).

Mean latency: **53.8s** / case.

Tokens: **64123** prompt + **8340** completion = **72463** total.

### `gemini-3.6-flash` — Full evidence

Cloud. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| mutex_contention | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| priority_inversion | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| adversarial_out_of_scope_time | 75 | 100 | 100 | 100 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 23 | 0 | 0 | 0 | 0 | 80 | 100 | ERROR |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| preempt_matrix_vs_chain | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 75**

4/17 cases returned an API error (first: HTTP 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.).

Mean latency: **71.8s** / case.

Tokens: **63245** prompt + **8281** completion = **71526** total.

### `gemini-3.1-flash-lite` — Compact

Cloud / fast. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 70 | 50 | 50 | 50 | 100 | 80 | 100 | ERROR |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 43 | 50 | 50 | 0 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 48 | 0 | 100 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 83 | 50 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 73 | 100 | 100 | 67 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 70 | 100 | 100 | 50 | 0 | 80 | 100 | PASS |

**Overall 81**

1/17 cases returned an API error (first: HTTP 400: * GenerateContentRequest.contents[2].parts[0].function_response.name: Name cannot be empty. * GenerateContentRequest.contents[3].parts[0].function_response.name: Name cannot be empty.).

Mean latency: **4.1s** / case.

Tokens: **63368** prompt + **6916** completion = **70284** total.

### `gemini-3.1-flash-lite` — Balanced

Cloud / fast. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 85 | 100 | 50 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 93 | 100 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 63 | 100 | 100 | 0 | 0 | 80 | 100 | FAIL |

**Overall 83**

Mean latency: **3.5s** / case.

Tokens: **66203** prompt + **6242** completion = **72445** total.

### `gemini-3.1-flash-lite` — Full evidence

Cloud / fast. Run `2026-08-18-072735`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 73 | 50 | 100 | 0 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 84**

Mean latency: **3.6s** / case.

Tokens: **67966** prompt + **6762** completion = **74728** total.
