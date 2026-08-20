# AI Benchmark results

Generated: 2026-08-19 22:38 UTC
Dataset: `tests/ai`

Live `--config` suite XML scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model.

## Offline fixture scorer

Run `2026-08-19-223109` — no live model.

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
| `qwen3.5:9b` | Compact | Local / practical | 78 | 8/17 | 76928 | 10.8s |
| `qwen3.5:9b` | Balanced | Local / practical | 86 | 15/17 | 85597 | 14.5s |
| `qwen3.5:9b` | Full evidence | Local / practical | 88 | 14/17 | 91755 | 16.2s |
| `qwen3.8:27b` | Compact | Local / high-quality | 78 | 9/17 | 82008 | 185.9s |
| `qwen3.8:27b` | Balanced | Local / high-quality | 88 | 13/17 | 103761 | 325.2s |
| `qwen3.8:27b` | Full evidence | Local / high-quality | 86 | 13/17 | 104804 | 332.4s |
| `gemini-3.5-flash-lite` | Compact | Cloud / fast | 82 | 12/17 | 71718 | 2.3s |
| `gemini-3.5-flash-lite` | Balanced | Cloud / fast | 80 | 11/17 | 74648 | 2.9s |
| `gemini-3.5-flash-lite` | Full evidence | Cloud / fast | 83 | 13/17 | 75486 | 2.6s |
| `gemini-3.7-flash` | Compact | Cloud | 83 | 12/17 | 71453 | 39.4s |
| `gemini-3.7-flash` | Balanced | Cloud | 83 | 13/17 | 78856 | 53.7s |
| `gemini-3.7-flash` | Full evidence | Cloud | 85 | 14/17 | 81855 | 25.0s |
| `claude-sonnet-5` | Compact | Cloud | 85 | 13/17 | 134649 | 10.3s |
| `claude-sonnet-5` | Balanced | Cloud | 87 | 13/17 | 143486 | 14.1s |
| `claude-sonnet-5` | Full evidence | Cloud | 82 | 12/17 | 149873 | 15.9s |
| `gpt-5.6-sol` | Compact | Cloud | 90 | 16/17 | 66382 | 10.4s |
| `gpt-5.6-sol` | Balanced | Cloud | 84 | 14/17 | 66953 | 9.4s |
| `gpt-5.6-sol` | Full evidence | Cloud | 88 | 15/17 | 68195 | 9.6s |

## Context mode comparison

Same model and dataset; Compact / Balanced / Full evidence packing.

### `qwen3.5:9b`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 78 | 8/17 | 64379 | 12549 | 76928 | 10.8s |
| Balanced | 86 | 15/17 | 66971 | 18626 | 85597 | 14.5s |
| Full evidence | 88 | 14/17 | 70813 | 20942 | 91755 | 16.2s |

### `qwen3.8:27b`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 78 | 9/17 | 69052 | 12956 | 82008 | 185.9s |
| Balanced | 88 | 13/17 | 72254 | 31507 | 103761 | 325.2s |
| Full evidence | 86 | 13/17 | 72460 | 32344 | 104804 | 332.4s |

### `gemini-3.5-flash-lite`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 82 | 12/17 | 65588 | 6130 | 71718 | 2.3s |
| Balanced | 80 | 11/17 | 66410 | 8238 | 74648 | 2.9s |
| Full evidence | 83 | 13/17 | 67853 | 7633 | 75486 | 2.6s |

### `gemini-3.7-flash`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 83 | 12/17 | 66366 | 5087 | 71453 | 39.4s |
| Balanced | 83 | 13/17 | 71424 | 7432 | 78856 | 53.7s |
| Full evidence | 85 | 14/17 | 73474 | 8381 | 81855 | 25.0s |

### `claude-sonnet-5`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 85 | 13/17 | 120816 | 13833 | 134649 | 10.3s |
| Balanced | 87 | 13/17 | 123211 | 20275 | 143486 | 14.1s |
| Full evidence | 82 | 12/17 | 126777 | 23096 | 149873 | 15.9s |

### `gpt-5.6-sol`

| Context | Overall | Pass | Prompt tok | Completion tok | Total tok | Mean latency |
|---|---:|---:|---:|---:|---:|---:|
| Compact | 90 | 16/17 | 60608 | 5774 | 66382 | 10.4s |
| Balanced | 84 | 14/17 | 60911 | 6042 | 66953 | 9.4s |
| Full evidence | 88 | 15/17 | 62116 | 6079 | 68195 | 9.6s |


| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |
|---|---:|---:|---:|---:|---:|---:|
| `qwen3.5:9b (Compact)` | 71 | 79 | 88 | 65 | 80 | 91 |
| `qwen3.5:9b (Balanced)` | 88 | 93 | 90 | 71 | 80 | 96 |
| `qwen3.5:9b (Full evidence)` | 85 | 93 | 97 | 82 | 80 | 89 |
| `qwen3.8:27b (Compact)` | 79 | 71 | 100 | 53 | 80 | 98 |
| `qwen3.8:27b (Balanced)` | 88 | 94 | 103 | 71 | 80 | 93 |
| `qwen3.8:27b (Full evidence)` | 88 | 94 | 91 | 65 | 80 | 96 |
| `gemini-3.5-flash-lite (Compact)` | 82 | 90 | 70 | 71 | 80 | 99 |
| `gemini-3.5-flash-lite (Balanced)` | 82 | 90 | 56 | 71 | 80 | 99 |
| `gemini-3.5-flash-lite (Full evidence)` | 82 | 90 | 77 | 71 | 80 | 99 |
| `gemini-3.7-flash (Compact)` | 82 | 82 | 94 | 65 | 80 | 98 |
| `gemini-3.7-flash (Balanced)` | 82 | 91 | 100 | 53 | 80 | 99 |
| `gemini-3.7-flash (Full evidence)` | 82 | 94 | 100 | 59 | 80 | 99 |
| `claude-sonnet-5 (Compact)` | 82 | 85 | 91 | 76 | 80 | 99 |
| `claude-sonnet-5 (Balanced)` | 91 | 93 | 94 | 76 | 80 | 86 |
| `claude-sonnet-5 (Full evidence)` | 85 | 94 | 81 | 59 | 80 | 95 |
| `gpt-5.6-sol (Compact)` | 88 | 93 | 101 | 76 | 80 | 99 |
| `gpt-5.6-sol (Balanced)` | 82 | 84 | 94 | 71 | 80 | 99 |
| `gpt-5.6-sol (Full evidence)` | 91 | 90 | 94 | 76 | 80 | 99 |

## Live models

### `qwen3.5:9b` — Compact

Local / practical. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 69 | 50 | 50 | 100 | 100 | 80 | 40 | FAIL |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| adversarial_correlation_not_cause | 55 | 0 | 100 | 100 | 0 | 80 | 80 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 78**

Mean latency: **10.8s** / case.

Tokens: **64379** prompt + **12549** completion = **76928** total.

### `qwen3.5:9b` — Balanced

Local / practical. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 70 | 100 | 100 | 50 | 0 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| explain_region | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 82 | 0 | 100 | 125 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 78 | 100 | 75 | 0 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 86**

Mean latency: **14.5s** / case.

Tokens: **66971** prompt + **18626** completion = **85597** total.

### `qwen3.5:9b` — Full evidence

Local / practical. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 99 | 50 | 100 | 175 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 69 | 0 | 100 | 100 | 100 | 80 | 40 | FAIL |
| adversarial_out_of_scope_time | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| period_jitter | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| waiter_owner_handoff | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 78 | 100 | 75 | 0 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 93 | 100 | 100 | 67 | 100 | 80 | 100 | PASS |

**Overall 88**

Mean latency: **16.2s** / case.

Tokens: **70813** prompt + **20942** completion = **91755** total.

### `qwen3.8:27b` — Compact

Local / high-quality. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 68 | 50 | 0 | 100 | 100 | 80 | 100 | FAIL |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 78**

Mean latency: **185.9s** / case.

Tokens: **69052** prompt + **12956** completion = **82008** total.

### `qwen3.8:27b` — Balanced

Local / high-quality. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 94 | 100 | 100 | 75 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 100 | 100 | 100 | 150 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 83 | 100 | 100 | 133 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 88**

Mean latency: **325.2s** / case.

Tokens: **72254** prompt + **31507** completion = **103761** total.

### `qwen3.8:27b` — Full evidence

Local / high-quality. Run `2026-08-18-141210`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 92 | 100 | 100 | 100 | 100 | 80 | 60 | FAIL |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 80 | 100 | 100 | 0 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 86**

Mean latency: **332.4s** / case.

Tokens: **72460** prompt + **32344** completion = **104804** total.

### `gemini-3.5-flash-lite` — Compact

Cloud / fast. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 87 | 100 | 100 | 25 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 63 | 0 | 100 | 0 | 100 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 88 | 100 | 100 | 50 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 93 | 100 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |

**Overall 82**

Mean latency: **2.3s** / case.

Tokens: **65588** prompt + **6130** completion = **71718** total.

### `gemini-3.5-flash-lite` — Balanced

Cloud / fast. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 50 | 33 | 100 | 80 | 100 | PASS |
| mutex_contention | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 50 | 50 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 78 | 0 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 90 | 100 | 100 | 67 | 100 | 80 | 80 | FAIL |
| period_jitter | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 83 | 50 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |
| preempt_matrix_vs_chain | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |

**Overall 80**

Mean latency: **2.9s** / case.

Tokens: **66410** prompt + **8238** completion = **74648** total.

### `gemini-3.5-flash-lite` — Full evidence

Cloud / fast. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| mutex_contention | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 70 | 0 | 100 | 50 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 83 | 50 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 68 | 100 | 100 | 33 | 0 | 80 | 100 | FAIL |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |

**Overall 83**

Mean latency: **2.6s** / case.

Tokens: **67853** prompt + **7633** completion = **75486** total.

### `gemini-3.7-flash` — Compact

Cloud. Run `2026-08-19-043257`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 63 | 50 | 50 | 0 | 100 | 80 | 100 | FAIL |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 45 | 0 | 50 | 100 | 0 | 80 | 80 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 75 | 100 | 100 | 100 | 0 | 80 | 80 | FAIL |
| period_jitter | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |

**Overall 83**

Mean latency: **39.4s** / case.

Tokens: **66366** prompt + **5087** completion = **71453** total.

### `gemini-3.7-flash` — Balanced

Cloud. Run `2026-08-19-043257`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 75 | 100 | 100 | 100 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 83**

Mean latency: **53.7s** / case.

Tokens: **71424** prompt + **7432** completion = **78856** total.

### `gemini-3.7-flash` — Full evidence

Cloud. Run `2026-08-19-223109`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 85**

Mean latency: **25.0s** / case.

Tokens: **73474** prompt + **8381** completion = **81855** total.

### `claude-sonnet-5` — Compact

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 100 | 100 | 100 | 133 | 100 | 80 | 100 | PASS |
| trace_regression | 73 | 100 | 50 | 0 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 44 | 0 | 50 | 75 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 54 | 0 | 100 | 75 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 53 | 50 | 50 | 67 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |

**Overall 85**

Mean latency: **10.3s** / case.

Tokens: **120816** prompt + **13833** completion = **134649** total.

### `claude-sonnet-5` — Balanced

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 79 | 100 | 50 | 100 | 100 | 80 | 40 | FAIL |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| adversarial_correlation_not_cause | 78 | 0 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 84 | 100 | 75 | 100 | 100 | 80 | 40 | FAIL |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 87**

Mean latency: **14.1s** / case.

Tokens: **123211** prompt + **20275** completion = **143486** total.

### `claude-sonnet-5` — Full evidence

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 83 | 100 | 100 | 133 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 48 | 50 | 50 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 88 | 100 | 100 | 33 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 68 | 100 | 100 | 50 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 54 | 100 | 100 | 0 | 0 | 80 | 40 | FAIL |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 82**

Mean latency: **15.9s** / case.

Tokens: **126777** prompt + **23096** completion = **149873** total.

### `gpt-5.6-sol` — Compact

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 72 | 50 | 100 | 125 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 93 | 100 | 75 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 90**

Mean latency: **10.4s** / case.

Tokens: **60608** prompt + **5774** completion = **66382** total.

### `gpt-5.6-sol` — Balanced

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 78 | 0 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 78 | 100 | 75 | 0 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 84**

Mean latency: **9.4s** / case.

Tokens: **60911** prompt + **6042** completion = **66953** total.

### `gpt-5.6-sol` — Full evidence

Cloud. Run `2026-08-19-035307`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 78 | 100 | 75 | 0 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 88**

Mean latency: **9.6s** / case.

Tokens: **62116** prompt + **6079** completion = **68195** total.
