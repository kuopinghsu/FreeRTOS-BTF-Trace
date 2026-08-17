# AI Benchmark results

Generated: 2026-08-17 07:36 UTC
Dataset: `tests/ai`

Live `--config` suite XML scores a real endpoint. Offline rows score the canned `response` fields in `dataset.json` and gate the scorer, not a model.

Live **17-case** tables (`gemini-2.5-flash-lite`, `gemini-2.5-pro`, `claude-sonnet-5`) are run `2026-08-17-072125`. Local Ollama tables remain the **14-case** run from 2026-08-15 (before `response_vs_blocking`, `preempt_matrix_vs_chain`, and `mutex_block_vs_wait_queue`). Gemini 3.6 Flash and Gemini 3.1 Flash-Lite stay the shipped cloud ids in [`examples/ai/benchmark.xml`](examples/ai/benchmark.xml) (tool follow-up / thought signatures); they were not in this live suite.

## Offline fixture scorer

Run `2026-08-17-072125` — no live model.

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

17-case live suite, 2026-08-17:

| Model | Category | Overall | Pass | Mean latency |
|---|---|---:|---:|---:|
| `claude-sonnet-5` | Local / practical | 87 | 14/17 | 13.9s |
| `gemini-2.5-pro` | Cloud / frontier | 78 | 14/17 | 35.3s |
| `gemini-2.5-flash-lite` | Cloud / fast | 69 | 10/17 | 2.6s |

| Model | Finding | Evidence | Tool use | Root cause | Calibration | Safety |
|---|---:|---:|---:|---:|---:|---:|
| `claude-sonnet-5` | 85 | 94 | 98 | 71 | 80 | 95 |
| `gemini-2.5-pro` | 74 | 79 | 91 | 53 | 80 | 99 |
| `gemini-2.5-flash-lite` | 65 | 63 | 73 | 47 | 80 | 99 |

`claude-sonnet-5` leads this 17-case suite (87, 14/17, 13.9s). `gemini-2.5-pro` matches the pass count but is slower (35.3s) and weaker on root cause. `gemini-2.5-flash-lite` is the latency win (2.6s) and drops under the 70 headline. Shared weak spots: mutex-vs-starvation, correlation-not-cause, and out-of-scope timestamps.

14-case local Ollama suite, 2026-08-15 (not comparable pass counts):

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

`qwen3.8:27b` leads that local set. `qwen3.5:9b` is the practical default (about 3.6× faster than 3.8:27b, 10 points behind). `gemma4:26b` is slower than 9b and slightly worse.

## Live models

### `gemini-2.5-flash-lite`

Cloud / fast. Run `2026-08-17-072125`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 53 | 100 | 50 | 0 | 0 | 80 | 100 | FAIL |
| trace_regression | 68 | 50 | 0 | 100 | 100 | 80 | 100 | FAIL |
| explain_region | 38 | 0 | 0 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_mutex_vs_starvation | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 48 | 0 | 100 | 33 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 20 | 0 | 0 | 0 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| stats_page_next_check | 78 | 100 | 75 | 0 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 83 | 100 | 100 | 0 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |

**Overall 69**

Mean latency: **2.6s** / case.

### `gemini-2.5-pro`

Cloud / frontier. Run `2026-08-17-072125`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 88 | 100 | 50 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| trace_regression | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 48 | 0 | 50 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 58 | 0 | 100 | 100 | 0 | 80 | 100 | FAIL |
| adversarial_out_of_scope_time | 50 | 100 | 50 | 0 | 0 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 70 | 50 | 50 | 50 | 100 | 80 | 100 | PASS |
| stats_page_next_check | 78 | 50 | 50 | 100 | 100 | 80 | 100 | PASS |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 78**

Mean latency: **35.3s** / case.

### `claude-sonnet-5`

Local / practical. Run `2026-08-17-072125`.

| Case | Overall | Finding | Evidence | Tool use | Root cause | Calibration | Safety | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| migration_thrash | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| mutex_contention | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| priority_inversion | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| deadline_miss | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| load_imbalance | 83 | 100 | 100 | 133 | 0 | 80 | 100 | PASS |
| trace_regression | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| explain_region | 88 | 50 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_mutex_vs_starvation | 23 | 0 | 0 | 0 | 0 | 80 | 100 | FAIL |
| adversarial_exec_vs_preemption | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_correlation_not_cause | 78 | 0 | 100 | 100 | 100 | 80 | 100 | PASS |
| adversarial_out_of_scope_time | 95 | 100 | 100 | 100 | 100 | 80 | 80 | FAIL |
| period_jitter | 98 | 100 | 100 | 100 | 100 | 80 | 100 | PASS |
| waiter_owner_handoff | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| stats_page_next_check | 89 | 100 | 100 | 100 | 100 | 80 | 40 | FAIL |
| response_vs_blocking | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |
| preempt_matrix_vs_chain | 100 | 100 | 100 | 133 | 100 | 80 | 100 | PASS |
| mutex_block_vs_wait_queue | 78 | 100 | 100 | 100 | 0 | 80 | 100 | PASS |

**Overall 87**

Mean latency: **13.9s** / case.

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
