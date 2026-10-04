# BTFViewer Change Log

Since v1.0.0 (2026-09-13)

## 2026-10-02
- Fixed: Trace Health tick period now follows the trace time scale (and a tick-rate metadata key when present) instead of assuming 1 ms in ns (desktop/web)
- Fixed: core-affinity masks above 32 bits; bare `resume`/`resume/isr` notes no longer create a phantom task (web/desktop)
- Statistics: a slice or priority episode still open at trace end is marked as truncated and left out of slice-duration samples, max/min/percentile jumps, and priority plots; CPU% still counts it (desktop/web)
- Mutex / Semaphore: a mutex given back by a different task is no longer a hold-time sample; the table notes how many were excluded (desktop/web)
- Interval and Mutex / Semaphore statistics in a cursor range now require both endpoints inside the range; spans crossing the edge are counted in a note (desktop/web)
- Trace Health: `interval_stop` events with no open start are counted; zero-length intervals and zero migration gaps are kept (desktop/web)
- Renamed for accuracy (section IDs and saved pins unchanged): Blocking Time → Off-CPU Gap, Activation Latency → Fitted Periodic Deviation, Post-Migration Gap → Migration Gap, Migrations "Gap other" → "Gap (all)"; Min/Max jump notes say "observed slice" instead of BCET/WCET (desktop/web)
- Priority Inheritance: mutex inheritance alone is no longer drawn as a red inversion; red needs a medium-priority task between base and peak (desktop/web)
- Mutex / Semaphore / Queue: the Kind column shows what each span measures (mutex hold, sem take→give / give→take, queue send→recv); a re-created handle gets its own `(gen N)` row; kernel gives right after create are counted in the exclusion note; "Waiters" is now "Overlap" and no longer implies contention; the Queue table notes that FIFO pairing ignores overwrite/send-to-front/reset (desktop/web)
- Statistics: new captions from existing trace data — dispatch latency split into create→first run vs resume→run (repeated resumes merged), same-core gap baseline for migrations, priority boost→run and on/off-CPU split, affinity change → first allowed run, suspended time, and interval on-CPU share of the starting task; HTML export adds the per-episode and per-instance columns (desktop/web)
- Trace Health: each metric family is listed as available / limited / unavailable with the reason, in the health dialog, HTML report, and AI evidence package (desktop/web)
- Statistics: p50/p95/p99 headers state the nearest-rank method; tables warn when rows have too few samples for p95/p99 to differ from Max (desktop/web)
- Priority Inheritance and Mutex / Semaphore hold outliers now zoom to the whole span and mark both start and end (desktop/web)
- HTML export adds a Metric definitions card; the AI evidence package attaches the definitions for the statistics it carries (desktop/web)

## 2026-10-01
- Modern UI refresh: unified light/dark theme colors with improved text and focus contrast (desktop/web)
- AI Assistant: status messages show error/warning icons, not color alone (desktop/web)
- Expand report: "Back to report" after jumping to evidence; layout restores when the last trace closes; no longer shrinks the report in narrow windows (desktop/web)
- Statistics: clearer empty-state guidance and tooltips for long labels (desktop/web)
- Icon rails: accessible names for screen readers (desktop/web)
- HTML report: follows the shared theme colors

## 2026-09-19
- Accessibility: colorblind-safe palette setting renamed to "Colorblind-safe palette (Okabe-Ito)" with a clearer tooltip describing its task/core-color scope (desktop/web)
- Fixed: take_mutex/give_mutex STI markers relied on red/green alone; they now also use distinct triangle shapes so mutex direction is never color-only (desktop/web)
- Fixed: packed worker trace reconstruction built `coreTaskSegStarts` from the LOD segment array instead of the raw one, which could desync core-task row lookup/hit-testing once LOD reduction was active (web)
- v1.0.1 released

## 2026-09-16
- Evidence Pack export moved from Marks panel to Analysis Findings (new on desktop)
- Keyboard shortcuts: fixed Ctrl/Cmd and Alt modifiers leaking into bare-key shortcuts (web)
- Desktop: added bare `S` and `+`/`-`/`=`/`_` shortcuts, matching web
- Desktop/web: unified portable workspace (.btfw) state with Session export/import
- Fixed: long tag alias could overlap the data-format control
- Fixed: data-format control covered the tag label when a row was expanded (web)

## 2026-09-15
- AI: tag queries now return value stats (min/avg/max/etc.), not just occurrences
- Tag rename (alias), saved per trace
- Fixed: tag alias sometimes not visible (web)
- Fixed: changing tag format could scroll the Statistics view away

## 2026-09-14
- Tag data format: UInt32 / Int32 / Float32
- Tag chart scale: Linear / Log2
- Tag chart: "Include zero" axis option
- Fixed: Float32 tag charts (scatter/histogram) rendered incorrectly
- Fixed: Log2 scale had no visible effect for Float32 tags
- HTML report: animated KPI numbers and entrance effects
- HTML report: sections expand by default

## 2026-09-13
- v1.0.0 released
