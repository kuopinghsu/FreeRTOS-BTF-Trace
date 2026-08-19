# AI Benchmark results

Generated: 2026-08-19 02:38 UTC
Dataset: `tests/ai`

Live `--config` suite XML scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model.

## Offline fixture scorer

Run `2026-08-19-003934` — no live model.

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
| `gemini-3.7-flash` | Compact | Cloud | 85 | 14/17 | 72955 | 31.6s |
| `gemini-3.7-flash` | Balanced | Cloud | 85 | 14/17 | 79797 | 29.6s |
| `gemini-3.7-flash` | Full evidence | Cloud | 77 | 12/17 | 74317 | 57.9s |

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
| Compact | 85 | 14/17 | 66868 | 6087 | 72955 | 31.6s |
| Balanced | 85 | 14/17 | 72030 | 7767 | 79797 | 29.6s |
| Full evidence | 77 | 12/17 | 67398 | 6919 | 74317 | 57.9s |


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
| `gemini-3.7-flash (Compact)` | 88 | 88 | 98 | 59 | 80 | 99 |
| `gemini-3.7-flash (Balanced)` | 85 | 94 | 100 | 59 | 80 | 99 |
| `gemini-3.7-flash (Full evidence)` | 65 | 76 | 101 | 53 | 80 | 99 |

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

Cloud. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 73 | 50 | 50 | 67 | 100 | 80 | 100 | PASS |
| explain_region | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 75 | 100 | 100 | 100 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 85**

1/17 cases returned an API error (first: HTTP 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.).

Mean latency: **31.6s** / case.

Tokens: **66868** prompt + **6087** completion = **72955** total.

### `gemini-3.7-flash` — Balanced

Cloud. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
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

Mean latency: **29.6s** / case.

Tokens: **72030** prompt + **7767** completion = **79797** total.

### `gemini-3.7-flash` — Full evidence

Cloud. Run `2026-08-19-003934`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 82 | 0 | 100 | 125 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 75 | 100 | 100 | 100 | 0 | 80 | 80 | FAIL |
| period_jitter | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| waiter_owner_handoff | 38 | 0 | 0 | 100 | 0 | 80 | 100 | ERROR |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 77**

3/17 cases returned an API error (first: HTTP 503: This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.).

Mean latency: **57.9s** / case.

Tokens: **67398** prompt + **6919** completion = **74317** total.
