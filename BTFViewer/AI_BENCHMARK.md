# AI Benchmark results

Generated: 2026-08-15 11:59 UTC
Dataset: `tests/ai`

Live `--config` suite XML scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model.

Live model tables are from the 14-case run before `response_vs_blocking`, `preempt_matrix_vs_chain`, and `mutex_block_vs_wait_queue` were added. The next live suite will score 17 cases. Gemini was not run (`GEMINI_API_KEY` missing).

## Offline fixture scorer

Run `2026-08-15-115323` — no live model.

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

| Model | Category | Overall | Pass | Mean latency |
|---|---|---:|---:|---:|
| `qwen3.8:27b` | Local / high-quality | 88 | 11/14 | 189.9s |
| `qwen3.5:27b` | Local / high-quality | 81 | 10/14 | 148.5s |
| `qwen3.5:9b` | Local / practical | 78 | 9/14 | 52.4s |
| `gemma4:26b` | Local / high-quality | 73 | 8/14 | 110.6s |

| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |
|---|---:|---:|---:|---:|---:|---:|
| `qwen3.8:27b` | 89 | 86 | 100 | 79 | 80 | 99 |
| `qwen3.5:27b` | 75 | 86 | 88 | 64 | 80 | 99 |
| `qwen3.5:9b` | 75 | 82 | 87 | 57 | 80 | 97 |
| `gemma4:26b` | 71 | 66 | 67 | 64 | 80 | 94 |

`qwen3.8:27b` leads quality. `qwen3.5:9b` is the practical default (about 3.6× faster than 3.8:27b, 10 points behind). `gemma4:26b` is slower than 9b and slightly worse. Shared weak spots: mutex-vs-starvation, correlation-not-cause, and out-of-scope timestamps.

## Live models

### `qwen3.8:27b`

Local / high-quality. Run `2026-08-15-100223`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 68 | 100 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 94 | 100 | 100 | 75 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 82 | 100 | 100 | 125 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |

**Overall 88**

Mean latency: **189.9s** / case.

### `qwen3.5:27b`

Local / high-quality. Run `2026-08-15-100223`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 58 | 50 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 94 | 100 | 100 | 75 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 30 | 0 | 50 | 0 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 70 | 100 | 100 | 50 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 98 | 100 | 100 | 100 | 100 | 80 | 100 | ERROR |

**Overall 81**

1/14 cases returned an API error (first: Remote end closed connection without response).

Mean latency: **148.5s** / case.

### `qwen3.5:9b`

Local / practical. Run `2026-08-15-112143`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 90 | 100 | 100 | 50 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 90 | 100 | 100 | 67 | 100 | 80 | 80 | FAIL |
| period_jitter | 55 | 50 | 50 | 100 | 0 | 80 | 80 | FAIL |
| waiter_owner_handoff | 68 | 50 | 100 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |

**Overall 78**

Mean latency: **52.4s** / case.

### `gemma4:26b`

Local / high-quality. Run `2026-08-15-112143`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 60 | 100 | 50 | 50 | 0 | 80 | 100 | FAIL |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 63 | 100 | 100 | 0 | 0 | 80 | 100 | FAIL |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 33 | 0 | 50 | 0 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 83 | 50 | 100 | 67 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 87 | 100 | 100 | 25 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 85 | 100 | 50 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 73 | 100 | 50 | 0 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 59 | 100 | 50 | 100 | 0 | 80 | 40 | FAIL |
| stats_page_next_check | 83 | 50 | 75 | 100 | 100 | 80 | 100 | PASS |

**Overall 73**

Mean latency: **110.6s** / case.
