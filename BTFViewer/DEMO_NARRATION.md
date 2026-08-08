# Demo narration — BTF Viewer (~12 minutes)

Spoken script for the **desktop** app. The web app is the same analysis with small label differences (noted below).  
Trace: `tracedata/example-8cores.btf.gz`.  
Method: [WORKFLOWS.md](WORKFLOWS.md). UI names: [README.md](README.md).

**How to use this file**

- **Say** — speak this. Written for a voice track or TTS: no backticks, no markdown, numbers spelled the way they should be heard.
- **Do** — click this; do not speak it. Pause until the UI matches before the next **Say**.
- Pace ~140 words/minute. Hold extra silence if a chart is slow. Cut the *If running long* items first.

**Before recording**

- Desktop viewer, empty session (welcome page).
- Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) ready to paste off-camera (or `GEMINI_API_KEY` already in the environment).
- Optional: `BTFViewer/examples/ai/gemini.json` for **Import…** (the sample key field is empty).
- If the **AI** tab is missing: **View → Show AI Assistant**, and in **Settings → AI** tick **Enable AI Assistant**.
- Do not show or read the full API key.

**Pronunciation (voice / TTS)**

| Write / UI | Say |
|------------|-----|
| BTF | B T F |
| `.btf.gz` | compressed B T F |
| STI | S T I |
| WCET | W C E T |
| CS[28] | C S twenty-eight |
| High[268] | High two-sixty-eight |
| σ | sigma |
| L/M/H | low, med, high |
| P0 / P1 / P2 | P-zero / P-one / P-two |
| `jump:TIME` | jump, colon, timestamp |
| µs | microseconds |
| Ctrl+, | control comma (macOS: command comma) |
| Ctrl+Enter | control enter (macOS: command enter) |

**Time axis on this file (easy to get wrong on camera)**  
Span is **2.358 s**, but timestamps do **not** start at zero. The trace opens near **1.014 s** (`#timeScale us`) and ends near **3.37 s**. The inversion window **3.085–3.310 s** is on the axis — it is not past the end of the capture.

**Desktop vs web labels**

| Desktop (this demo) | Web |
|---------------------|-----|
| **Limit to C1–Cn** | **Limit to cursor range (C1–Cn)** |
| **Settings…** on the AI bar, or **Settings → AI** | Same |

---

## 0:00 – 0:40 · Opening

**Do:** Welcome page visible. No trace loaded.

**Say:**

Welcome to B T F Viewer. It is an interactive viewer for FreeRTOS context-switch traces in Best Trace Format. Desktop and web run the same analysis. Today we use the desktop app and the sample trace example eight-cores.

This capture spans two point three five eight seconds, on eight cores, with a hundred and fifty-four tasks. It is a concatenation of deliberate stress tests, so warnings are expected. We will walk the top-down analysis ladder, confirm each finding on the timeline, then finish with the A I Assistant on Google Gemini.

---

## 0:40 – 1:25 · Load the trace and tour the UI

**Do:** **File → Open** (`Ctrl+O`) → `tracedata/example-8cores.btf.gz`. Wait for the timeline and **Statistics**. Press toolbar **Fit** (`Ctrl+0`). Point along the toolbar, then the right tabs.

**Say:**

Open from File, Open — or drag and drop. Compressed B T F works the same as a plain file.

The toolbar is mostly icons. Hover if you need the name. Layout is Horizontal or Vertical. Zoom, one-to-one, and Fit. Task versus Core view. Load for the C P U utilisation strip. Find. Heatmap and Chord for migrations. Analysis for the triage card. Settings at the far right.

The centre canvas is the timeline. Each coloured bar is a run slice. Hover a bar for duration, core, and neighbours. The status bar shows the span — two point three five eight seconds — plus core count and switch stats. Times on the axis start near one point zero one four seconds, not zero.

On the right: Statistics, Marks, Find, Legend, and A I. We stay in Statistics for the ladder, then finish on A I.

**Do:** Confirm **Load** is on (toolbar). Click **Core**, pause, click **Task**. Point at the load strip under the timeline.

**Say:**

Load draws utilisation under the timeline. Core view stacks activity per core. Task view is one row per task. Drag the divider if the chart needs more room.

---

## 1:25 – 2:00 · Get oriented

**Do:** **Statistics** tab. Expand **Summary**. Point at span, 8 cores, ~31 141 segments, STI, instrumentation (priority + sync + intervals).

**Say:**

Every session starts the same way. Is the capture sound, and are we looking at the whole trace? Fit answers the second question. Summary answers the first: eight cores, about thirty-one thousand segments, S T I present, and instrumentation for priority, sync objects, and intervals. Mutex pairing and priority inheritance will have real data — not empty tables.

A caution: this file stitches several suite phases together. A full-trace warning is a clue, not a product bug, until we scope to one phase.

---

## 2:00 – 2:40 · Analysis Findings

**Do:** Toolbar **Analysis**. Scroll slowly past two or three severities. Leave the dialog open or close it after a beat.

**Say:**

Click Analysis on the toolbar. This is the triage card for the current Statistics scope — severity-tagged findings for load, W C E T, blocking, migrations, tick health, sync bounces, and similar. Findings are not a Statistics section. They name the section to open next.

The method is always: read every finding, not just the first; open that section; click Max, a chart point, or a heatmap cell to jump the timeline; then optionally ask A I to narrate the same findings. We do the human ladder first so you can judge the assistant later.

---

## 2:40 – 3:35 · Rung 1 — System health

**Do:** Statistics → **Trace Health (TICK)**. Point at **TICKLESS**, C V ~35.9 %, avg ~944 µs, max gap ~2.481 ms, missed ≈ 8. Skip **Tick Distribution** unless you are running short.

**Say:**

Rung one is system health. Open Trace Health. Mode is tickless. Coefficient of variation is about thirty-six percent — well above the five percent line that separates a steady periodic tick from tickless idle.

Average period is around nine hundred forty microseconds. Largest gap is about two and a half milliseconds. Estimated missed ticks is eight.

On a tickless build the kernel suppresses ticks when nothing is runnable, so multi-tick gaps in idle stretches are expected. Before treating missed ticks as a defect, scope a busy window with cursors and re-read this section. If it is still warning while every core is loaded, then chase it. For this demo it is P-two: do not let tickless idle poison every latency number until we scope.

---

## 3:35 – 4:20 · Rung 2 — Core balance

**Do:** **Core Utilisation**. Point at cores ~68.7–77.3 % and Load Balance Score **95 %**, σ **6.0 %**. Optionally glance at **Concurrent Core Active** or **Kernel Switch Overhead** — do not open charts unless running short.

**Say:**

Rung two: are the cores sharing the work? Core Utilisation excludes idle and tick. Cores sit roughly sixty-nine to seventy-seven percent. Load Balance Score is ninety-five percent, sigma about six percent. Eighty-five percent or more with sigma at or below thirty counts as reasonably balanced.

So imbalance is not the main story. Do not stop here. A scheduler can keep every core equally busy by bouncing work between them. Good balance and expensive migration often coexist. Core Time Breakdown, Concurrent Core Active, and Kernel Switch Overhead refine that picture. High gap percent often tracks switch overhead.

---

## 4:20 – 5:15 · Rung 3 — Task C P U and W C E T

**Do:** **Top Tasks by CPU**. Point at **CS[28]** ~15.9 %, Max ~3.623 ms. Open **Execution Time Per Slice**, sort by **Max**, click the **Max** cell. Pause on the zoomed timeline.

**Say:**

Rung three attributes C P U to tasks. Top Tasks is dominated by equal-priority context-switch workers. C S twenty-eight is about sixteen percent of C P U, with a worst slice around three point six milliseconds. Several siblings sit near fifteen percent.

Open Execution Time Per Slice, sort by Max, and click that Max value. The timeline jumps to the worst slice. Three to four milliseconds is long next to a one millisecond tick — one slice can span several tick periods and delay everything behind it.

Later you can cap that fan-out, pin workers with core affinity, or set deadlines under Settings, Display, Analysis thresholds. Values are in nanoseconds: C S twenty-eight equals two million means a two millisecond deadline. Always check Preemption Chain and Mutex before blaming the task’s own work.

---

## 5:15 – 6:25 · Rung 4 — Latency, cursors, inheritance

**Do:** **Fit** again (`Ctrl+0`). **Blocking Time**, sort by **Max**. Point at **High[268]** ~52.865 ms; **Low[266]** / **Med[267]** ~35–40 ms; skip **Runner[1]** (~737 ms sleep). Zoom toward the right of the trace. Place **two cursors** at about **3.085 s** and **3.310 s** (axis times). Tick **Limit to C1–Cn**. Optionally reopen **Analysis**. Then **Priority Inheritance**: **Low[266]** mutex inherit; **PS[228]** L/M/H. On the timeline, red bottom stripes on Low.

**Say:**

Rung four is latency. Blocking Time is the off-C P U gap until the next resume. High two-sixty-eight waits up to about fifty-three milliseconds in the inversion demo. Low and Med are thirty-five to forty milliseconds. Ignore Runner — that is orchestrator sleep between suite phases.

Place two cursors around the inversion window — Low, Med, and High near three point zero eight five to three point three one zero on the time axis. Enable Limit to C 1 through C n so Statistics and Analysis describe only that phase. The status bar shows the span between cursors. Re-open Analysis if you want findings for this window only.

Blocking answers how long this task was off C P U. Dispatch Latency is different: after create or resume, how long until first switch-in. Preemption Chain names who preempted whom.

Priority Inheritance belongs in this window. Low is boosted by mutex inherit — the kernel doing its job; look for red stripes under that task. A low-med-high pattern on P S two-twenty-eight is the classic three-task inversion and deserves a design look, not just a tuning change.

---

## 6:25 – 7:35 · Rung 5 — Migrations and locks

**Do:** Uncheck **Limit to C1–Cn** (or **Shift+C** to clear cursors). Full-trace numbers below will not match a scoped window. **Core Migrations**, sort by **Rate** or **Ping**. Point at **CS[18]** ~1692/s, dwell ~476 µs, Ping 24. **Task** view; click **CS[18]** in the label column or **Legend** to lock-highlight; **Load** on. Then **Mutex / Semaphore**: mutex `0x80021920` holds 864 / bounces 6 / **Warning**; queue `0x80021990` holds 864 / bounces **858** / status **OK**.

**Say:**

Clear the cursor scope so we are back on the full trace. Rung five is concurrency: migrations and locks. Trace-wide there are almost nineteen thousand migrations. C S eighteen runs about seventeen hundred migrations per second, half-millisecond dwell, high ping — classic A-B thrash from the first stress test, not lock contention. Hottest core pairs are mostly zero percent lock-bounce. That distinction matters. Thrash is an affinity and fan-out problem. Bounce is an ownership problem.

In Task view, lock-highlight the task from the Legend or the label column. With Load on, the strip shows that task’s share per core.

Now Mutex and Queue. One mutex has hundreds of holds and a handful of bounces — Warning status. The queue is the headline: eight hundred fifty-eight of eight hundred sixty-four holds crossed a core while still held. Status can still read O K. Co-locate producers and consumers, or shorten the hold. Investigate every Warning row on the timeline before treating teardown noise as a bug.

---

## 7:35 – 8:20 · Rung 6 — Compliance (affinity and lifecycle)

**Do:** Scroll Statistics down (these sections sit after migrations). Expand **Core Affinity**. Point at columns **Task**, **Mask**, **Observed Cores**, **Violations**. Scan `Aff[*]` rows — Violations empty. Point at **AffM[299]** if the remask `0x1 → 0x8` (or similar) is visible. Expand **Task Lifecycle**. Sort or scroll to **SR0**…**SR3**. Point at **Susp/Res** `4/4`. Click **SR0** — timeline jumps to create and highlights the task. Zoom if needed to show no run slices between a suspend and the matching resume. Optionally expand **Tag Analysis**, click **tag0_event** for the scatter (skip if time is tight). Point at the Statistics footer: **Export HTML** / **Trace Compare…**.

**Say:**

Last rung: did the system do what the firmware asked? Scroll Statistics to Core Affinity. Each row is a task that called affinity-set. Mask is what it requested. Observed Cores is where it actually ran. Violations lists cores used outside that mask. On this trace the Aff tasks stay inside their masks, and the remask on Aff M behaves. Violations stays empty — that is a pass.

Now Task Lifecycle. Look at the S R tasks — S R zero through S R three. Susp slash Res is four slash four: every suspend has a matching resume. Click S R zero. The timeline jumps to create and highlights that row. Confirm it does not run between suspend and resume. Runs is how many times the scheduler dispatched it — that number is much larger than four, and that is normal. Four is the A P I count, not every preemption.

If you have a few seconds, Tag Analysis is the same idea for firmware numbers. Click tag zero event to open the distribution. Bind a budget later if you want pass or fail between builds.

These two tables are the clean checks. The problems we already showed — migration rate, queue bounces, High’s long block — stay in those earlier sections. After a firmware change, open a second trace in another tab and use Trace Compare at the bottom of Statistics, or Export H T M L for a report in this same order.

---

## 8:20 – 8:45 · Find (optional; skip if running long)

**Do:** Toolbar **Find** or **Find** tab (`Ctrl+F`). Type `CS[28]`. **F3** / **Shift+F3**. Return to **Statistics**.

**Say:**

Find searches tasks, migrations, STI, and intervals. Marks holds cursors, bookmarks, and annotations. Legend is its own tab for colours and filters. Right-click the timeline to place a cursor, bookmark, or note. Sessions restore zoom, cursors, and marks.

---

## 8:45 – 10:20 · A I setup — Google Gemini

**Do:** **AI** tab. Click **Settings…** on the A I bar (or **Settings → AI**, `Ctrl+,`). Confirm **Enable AI Assistant**. **Preset:** **Google Gemini**. Show **Base URL**  
`https://generativelanguage.googleapis.com/v1beta/openai`  
and **Model** `gemini-flash-lite-latest` (or a name **Test connection** lists). Paste the API key into **API key** off-camera. Optional: **Import…** → `examples/ai/gemini.json`, then paste the key. **Test connection**. Wait for models + probe. **OK**. On the A I bar, **Language…** → English if needed.

**Say:**

Now the AI Assistant. It never sees the raw BTF stream. It only receives structured Analysis Findings for the current Statistics scope, plus span and core count. If Statistics is empty or scoped wrong, the model will sound confident about nothing. We already built the findings. Now we connect an endpoint.

Open Settings, AI — the Settings button on the AI bar is the short path. Tick Enable AI Assistant. Presets are Ollama, OpenAI, Google Gemini, and Custom. Each preset keeps its own U R L, model, and key, so switching later does not wipe Gemini.

Choose Google Gemini. The default base U R L is Google’s OpenAI-compatible Gemini endpoint. Prefer a rolling model alias such as gemini-flash-lite-latest. Pinned versions differ by account and get retired.

Paste your Gemini A P I key from Google A I Studio into A P I key. Leave it empty only if the G E M I N I A P I K E Y environment variable is already set. Import can load the sample gemini JSON; it fills the form but does not save until you review and confirm.

Click Test connection. The viewer lists models the endpoint serves, then runs a short chat probe. A 401 means the key is wrong or missing. When Test succeeds, save Settings.

On the A I bar, Language sets the reply language. Templates sit above the conversation. Ask sends the box. Command-enter or control-enter is the shortcut. Stop cancels. Clear wipes the log so an old turn cannot colour the next answer.

---

## 10:20 – 12:00 · Templates — ask, then verify

**Do:** **Limit to C1–Cn** unchecked (full-trace triage). Click template **Analysis Findings**. Wait. Point at the **You** bubble then **Assistant**. If a `jump:TIME` link appears, click it — timeline seeks and an annotation is added; **AI** tab stays selected. Open the Statistics section the reply names. Click **Clear**. Second template: **Migration thrash**. Compare to the tables you already showed.

**Say:**

Ask in ladder order. Start with Analysis Findings or Triage findings — those prompts already name metrics and units. Then tick health, core balance, W C E T, latency, migration thrash, priority inversion. Use Deadline / budget only after you have set thresholds.

Click Analysis Findings. Your prompt appears in the You bubble; the model reply in Assistant. Read severity, what it means for this S M P system, and which Statistics section to open next.

If the reply includes jump, colon, timestamp, that number is in the trace time unit — microseconds on this file. Click it: the timeline seeks and an annotation is dropped. Confirm what you see against Statistics. Treat the assistant as a triage aid, not ground truth — especially on a demo concatenation.

Clear, then click Migration thrash. It should cite rate, ping, dwell, and the hot queue bounces we already measured. If the story disagrees with the tables, believe the tables.

That is the full loop: load, ladder, evidence on the timeline, then Gemini to narrate the same findings. Thank you for watching. The numbers are in the workflows guide, section three, worked example example eight-cores. Open that file and reproduce every step yourself.

---

## Timing cheat-sheet

Spoken ≈ **1 450 words** (~10.5 min at 140 wpm) plus ~1.5 min of clicks ≈ **12 minutes**.

| Clock | Block | ~words |
|------:|-------|--------|
| 0:00 | Opening | 95 |
| 0:40 | Load + UI | 170 |
| 1:25 | Orient | 95 |
| 2:00 | Analysis Findings | 95 |
| 2:40 | TICK | 130 |
| 3:35 | Core balance | 110 |
| 4:20 | W C E T | 130 |
| 5:15 | Latency + cursors + inherit | 175 |
| 6:25 | Migrations + locks | 160 |
| 7:35 | Affinity + lifecycle | 175 |
| 8:20 | Find (optional) | 55 |
| 8:45 | Gemini settings | 230 |
| 10:20 | Templates + close | 175 |

**If running long:** skip Find, Tick Distribution, Concurrent Core Active, and the second A I template.  
**If running short:** open **Tick Distribution**, toolbar **Heatmap**, or Statistics **Export HTML** after the verdict.

## On-camera checklist

- [ ] `tracedata/example-8cores.btf.gz` opens; **Fit** + **Load** + **Statistics**
- [ ] Status span ≈ 2.358 s; axis starts near 1.014 s
- [ ] Toolbar **Analysis** has findings
- [ ] Cursors at ~3.085 and ~3.310; **Limit to C1–Cn** on, then **off** before migrations
- [ ] CS[18] lock-highlight + Load; queue **858** / 864 bounces
- [ ] Gemini **Test connection** succeeds (key off-screen)
- [ ] Template **Analysis Findings** returns; optional `jump:` click keeps the A I tab
- [ ] No API key visible in the recording or a screenshot
