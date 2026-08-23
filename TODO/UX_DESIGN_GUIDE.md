
# BTFViewer UX Design Guide

## 1. Purpose

This guide defines the UX direction, interaction model, information architecture, and design rules for BTFViewer.

BTFViewer already provides a substantial engineering environment:

- interactive Task/Core Timeline;
- zoom, pan, fit, and cursor-range navigation;
- multiple cursors;
- Statistics and Analysis Findings;
- bookmarks and annotations;
- Find;
- Legend and filtering;
- migration/core-affinity analysis;
- Trace Compare;
- reports and snapshots;
- AI-assisted investigation and verification.

The main UX problem is therefore **not missing functionality**.

The challenge is organizing these capabilities into one understandable, evidence-driven investigation workflow.

---

# 2. Product UX Model

BTFViewer should feel like one connected trace-analysis environment:

```text
SEE
 ↓
TRIAGE
 ↓
SCOPE
 ↓
INVESTIGATE
 ↓
EVIDENCE
 ↓
VERIFY
 ↓
COMPARE
 ↓
DECIDE
````

In engineering terms:

```text
What happened?
      ↓
What looks wrong?
      ↓
Where does it happen?
      ↓
What behavior could explain it?
      ↓
Where is the supporting trace evidence?
      ↓
Does the evidence support the conclusion?
      ↓
Did the change improve it?
      ↓
What should I conclude or do next?
```

This workflow should organize the entire product.

The UI should not behave like a collection of independent tools.

Statistics, Migration, AI, Find, and Trace Compare should feel like different parts of the same investigation process.

---

# 3. Core Design Principles

## 3.1 Timeline Is the Evidence Layer

The Timeline should remain BTFViewer's primary source of truth.

Statistics, Find, Migration views, Trace Compare, and AI may discover or explain an issue, but whenever practical they should lead the user back to concrete Trace Evidence.

Evidence may be:

* a timestamp;
* Task segment;
* Core;
* Task/Core pair;
* migration;
* preemption;
* mutex/blocking event;
* cursor range;
* representative Statistics events such as p95, p99, Max, or WCET.

A feature that produces an analytical conclusion without a practical path back to Evidence is incomplete from a UX perspective.

---

## 3.2 Scope, Filter, Selection, and Highlight Are Different Concepts

These concepts must not be mixed.

### Scope

Scope answers:

> Which time region is being analyzed?

Examples:

```text
Scope: Full Trace
```

```text
Scope: C1–C2 · 282 µs
```

Scope is primarily about **time**.

---

### Filter

Filter answers:

> Which data inside the current Scope is included in the analysis?

Examples:

```text
Task: Worker[3] ×
```

```text
Core: Core_2 ×
```

```text
Migration: Core_2 → Core_5 ×
```

A Filter changes analytical input.

---

### Selection

Selection answers:

> Which object is currently selected for inspection or interaction?

Selection does not automatically imply filtering.

---

### Highlight

Highlight answers:

> What should be visually emphasized?

Highlight should not silently change analytical input.

For example:

```text
Highlight: Worker[3]
```

must not automatically become:

```text
Filter: Worker[3]
```

unless the user explicitly requests filtering.

---

## 3.3 Important Investigation State Must Be Visible

State that changes interpretation must never exist only internally.

The user should always be able to identify:

* active Trace;
* current Scope;
* active Filters;
* selected object where relevant;
* highlighted object where relevant;
* current Task/Core View Mode;
* Baseline/Candidate identity in Trace Compare.

Hidden analytical state is one of the highest-risk UX problems in an engineering analysis tool.

---

## 3.4 Progressive Disclosure

BTFViewer is an engineering tool.

High information density is appropriate, but complexity should be revealed progressively.

A new user should encounter the product in this order:

1. Open and orient.
2. Identify suspicious behavior.
3. Narrow the Scope.
4. Investigate one hypothesis.
5. Locate supporting Evidence.
6. Verify the interpretation.
7. Compare a changed trace.
8. Make a decision.

Do not require users to understand every table, Migration metric, cursor operation, or AI analysis mode before they can perform useful work.

---

## 3.5 Preserve Investigation Context

Moving among:

* Statistics;
* Marks;
* Find;
* Legend;
* Migration views;
* AI;
* Trace Compare;

should not unexpectedly destroy:

* Zoom;
* Timeline position;
* Cursors;
* active Trace;
* Scope;
* relevant Filters;
* bookmarks/annotations;
* Statistics scroll position;
* AI conversation where appropriate.

Navigation should change context only when the user explicitly requests it.

---

## 3.6 Same Concept, Same Language

Use canonical terms consistently across:

* Toolbar;
* menus;
* Statistics;
* Analysis Findings;
* Migration views;
* Trace Compare;
* AI;
* reports;
* CLI;
* documentation.

| Concept                                | Preferred term |
| -------------------------------------- | -------------- |
| Entire dataset                         | Full Trace     |
| Cursor-defined time window             | C1–Cn          |
| Current analyzed time region           | Scope          |
| Included subset of data                | Filter         |
| Current inspected object               | Selection      |
| Visual emphasis                        | Highlight      |
| Entire Timeline fitting                | Fit Trace      |
| Cursor-range fitting                   | Fit Cursors    |
| Primary comparison Trace               | Baseline       |
| New comparison Trace                   | Candidate      |
| Worse comparison result                | Regressed      |
| Better comparison result               | Improved       |
| Trace location supporting a conclusion | Evidence       |

Terminology should not drift between desktop UI, AI, reports, and documentation.

---

# 4. Main Information Architecture

Retain the central Timeline + right Analysis Panel architecture.

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Menu                                                                 │
├──────────────────────────────────────────────────────────────────────┤
│ Primary Toolbar                                                      │
├──────────────────────────────────────────┬───────────────────────────┤
│ Trace Tabs                               │ Analysis Tabs             │
│                                          │ Statistics                │
│                                          │ Marks                     │
│                 Timeline                 │ Find                      │
│                                          │ Legend                    │
│                                          │ AI                        │
├──────────────────────────────────────────┴───────────────────────────┤
│ Investigation Context / Scope / Filters / Cursors / Zoom / Status    │
└──────────────────────────────────────────────────────────────────────┘
```

Trace Tabs answer:

> Which dataset am I investigating?

Analysis Tabs answer:

> How am I investigating it?

These are conceptually different and should remain visually distinguishable.

---

# 5. Timeline Dominance

The Timeline should remain the dominant surface.

Recommended normal desktop ratio:

```text
Timeline        68–75%
Analysis Panel  25–32%
```

The Analysis Panel should:

* remain resizable;
* remember an appropriate width;
* have a usable minimum width;
* prefer vertical scrolling;
* avoid routine horizontal scrolling;
* avoid unnecessarily compressing Timeline labels.

Do not solve narrow-window problems by shrinking fonts.

---

# 6. Persistent Investigation Context

Introduce a compact persistent Context Bar.

Example:

```text
Scope: C1–C2 · 282 µs    Task: Worker[3] ×    Core: All    Zoom: 25%
```

Full-trace state:

```text
Scope: Full Trace         Filters: None         Zoom: Fit
```

The Context Bar should answer:

> What exactly am I looking at and analyzing right now?

It should update immediately when:

* Scope changes;
* Cursors change;
* Filters change;
* View Mode changes;
* Zoom changes where displayed.

Avoid filling the Context Bar with low-value state.

Only show information that affects interpretation or navigation.

---

# 7. Visible Filter State

Every Filter that changes analysis must have a visible representation.

Example:

```text
Task: Worker[3] ×
```

Multiple Filters:

```text
Task: Worker[3] ×    Migration: Core_2 → Core_5 ×
```

Rules:

* every active Filter is visible;
* `×` clears an individual Filter;
* provide a clear `Clear All`;
* preserve Filters while switching relevant Analysis Tabs;
* Statistics indicates when results are filtered;
* AI indicates which Filters are part of its context;
* reports and exports include important Filter metadata.

Never silently convert a Selection or Highlight into a Filter.

---

# 8. Task/Core View and Selection Model

Task and Core are mutually exclusive primary Timeline View Modes.

They should appear as a segmented control:

```text
┌────────┬────────┐
│  Task  │  Core  │
└────────┴────────┘
```

The active mode must be obvious.

Switching Task/Core View Mode should normally preserve:

* Timeline position;
* Zoom;
* Cursors;
* Scope.

Selection semantics should remain consistent across:

* Timeline;
* Statistics;
* Legend;
* Migration views;
* AI.

Always distinguish:

```text
View Mode
Selection
Highlight
Filter
```

---

# 9. Cursor Model

Cursors should be treated as one shared measurement and scoping mechanism.

Example:

```text
C1 1.205 ms    C2 1.487 ms    Δ 282 µs
```

Multiple Cursors:

```text
C1 1.205 ms   C2 1.320 ms   C3 1.487 ms   Span 282 µs
```

Requirements:

* stable C1–Cn numbering;
* exact timestamps;
* clear visual markers;
* easy deletion;
* clear range duration;
* predictable cursor-limit behavior;
* readable handling of overlapping cursor labels.

Reuse the same Cursor model for:

* measurement;
* Fit Cursors;
* Statistics Scope;
* AI Region Analysis;
* Trace Compare ranges;
* Evidence verification;
* export metadata.

Do not create independent Range concepts for different features.

---

# 10. Universal Evidence Navigation

Evidence Navigation should become one of BTFViewer's primary interaction patterns.

Use it across:

* Statistics;
* Analysis Findings;
* AI;
* Find;
* Migration analysis;
* Trace Compare.

Example:

```text
Response p99    48 µs ↗
```

Hover:

```text
Jump to p99 example at 1.487 ms
```

When activated:

1. center Timeline on the Evidence;
2. place or reuse a Cursor when appropriate;
3. Highlight the related Task/Core when useful;
4. preserve the Analysis Panel state;
5. preserve Analysis Panel scroll position;
6. avoid silently changing Scope;
7. avoid silently changing Filters.

Evidence actions should use the same visual affordance throughout the application.

---

# 11. Timeline Interaction

Recommended pointer interaction:

| Interaction          | Action                  |
| -------------------- | ----------------------- |
| Wheel / Trackpad     | Scroll                  |
| Ctrl+Wheel / Pinch   | Zoom                    |
| Drag                 | Pan                     |
| Left click           | Place/manipulate Cursor |
| Double-click Segment | Zoom/inspect Segment    |
| Right-click          | Context actions         |
| Shift modifier       | Snap/precision behavior |

Consistency is more valuable than adding additional interaction modes.

Important pointer actions should have keyboard-accessible alternatives where practical.

---

# 12. Timeline Hover

Hover should answer only immediate inspection questions.

Recommended content:

```text
Worker[3]
Core_2
1.205–1.226 ms
Duration: 21 µs
```

Hover should normally answer:

* what Task;
* what Core;
* when;
* how long.

Do not turn Hover into a miniature Statistics panel.

Deeper information belongs in the Analysis Panel.

---

# 13. Toolbar Design

The Toolbar should expose frequent investigation actions rather than duplicate the entire Menu.

Recommended grouping:

```text
[Open]

[−] [+] [Fit Trace] [Fit Cursors] [25% ▾]

[Task | Core] [STI] [Grid]

[Find] [Migration] [AI]
```

Use spacing or separators between groups.

Low-frequency and advanced actions belong in:

* Menu;
* Overflow;
* Command Palette;
* Settings.

Do not continuously add Toolbar buttons as new features are added.

---

# 14. Fit and Zoom Feedback

**Fit Trace**

Shows the complete Trace.

**Fit Cursors**

Fits the earliest-to-latest placed Cursor.

The distinction should remain explicit.

Expose both relative and physical scale where practical:

```text
25% · 120 µs/pixel
```

Physical scale is especially useful in engineering analysis because it makes the visible time resolution immediately understandable.

---

# 15. Statistics as the Triage Center

Statistics should answer:

> What deserves attention?

before showing detailed low-level metrics.

Recommended hierarchy:

## Triage

1. Analysis Findings
2. Timeline Anomalies
3. Worst Events
4. Response Time
5. Task Health

## Timing Investigation

6. Execution Time
7. Blocking / Off-CPU
8. Dispatch Latency
9. Critical Path
10. Period / Jitter
11. Unified Jitter

## SMP / Scheduling

12. Task × Core
13. Core Utilization Over Time
14. Core Migrations
15. Core Affinity
16. Preemption Matrix
17. Priority Inheritance

## Synchronization / Detail

18. Waiter × Owner
19. Mutex Blocking
20. Mutex / Semaphore
21. Queue
22. Interval
23. Tag
24. Detailed Tables

This does not remove expert information.

It changes the default investigation order.

The existing Statistics content already contains broad timing, CPU/scheduling, migration, and synchronization analysis, so the UX should primarily improve prioritization rather than remove analytical depth. 

---

# 16. Statistics Section Design

Use one predictable Statistics section pattern.

Example:

```text
▼ Response Time                         Warning
  Scope: C1–C2
```

Section headers may include:

* title;
* severity/status;
* Scope;
* Filtered state;
* collapse/expand;
* Help;
* Plot;
* Export;
* drag/reorder affordance where supported.

Do not let section headers consume excessive vertical space.

---

# 17. Statistical Distribution Presentation

Prefer:

```text
Typical → Tail → Worst
```

Example:

|   p50 |   p95 |   p99 |    Max |
| ----: | ----: | ----: | -----: |
| 21 µs | 38 µs | 48 µs | 113 µs |

Recommended visual priority:

1. p50 — Typical
2. p95 / p99 — Tail
3. Max / WCET — Worst
4. CV / Outlier metrics

Do not let Max visually dominate every table when tail behavior is more representative of the issue.

Numeric presentation should remain consistent across Statistics and reports.

---

# 18. Analysis Findings as an Investigation Inbox

Analysis Findings should not be passive text.

Use actionable Finding cards.

Example:

```text
⚠ High — Response-time tail

Worker[3] p99 = 61 µs

Evidence
1.487 ms ↗

[Show Evidence] [Investigate] [Ask AI]
```

Migration example:

```text
⚠ Medium — Migration burst

Worker[3]
17 migrations inside C1–C2

[Show Evidence] [Task × Core] [Investigate]
```

The intended path is:

```text
Finding
   ↓
Evidence
   ↓
Relevant Analysis
   ↓
Timeline Verification
```

The user should not need to know BTFViewer's Statistics hierarchy before starting an investigation. This matches the existing TODO direction of making Analysis Findings the investigation entry point. 

---

# 19. Migration and Core-Affinity UX

Migration analysis should use progressive drill-down.

```text
Migration Summary
       ↓
Task × Core
       ↓
Suspicious Task/Core
       ↓
Migration Corridor / Detail
       ↓
Timeline Evidence
```

Start with engineering-friendly summary metrics:

* Total Migrations;
* Migration Rate;
* Most Migrated Task;
* Most Active Core Pair;
* Median Dwell;
* Ping-pong / Thrash indication.

Do not require users to interpret a complex Heatmap before understanding the underlying numbers.

---

# 20. Task × Core Heatmap

The Heatmap should answer:

> Which Tasks execute on which Cores?

On Hover or Selection, show:

```text
Worker[3]
Core_2
31.7% of scoped execution
```

Actions may include:

```text
[Highlight Task]
[Filter Timeline]
[Show Migrations]
```

These actions must remain semantically distinct.

Selecting a Heatmap cell should begin an investigation rather than end it.

---

# 21. Migration Corridor / Core-Pair Detail

Selecting a Core pair should expose useful detail.

Example:

```text
Core_2 → Core_5

47 migrations
Task: Worker[3]
Median dwell: …
Ping-pong: …

[Show Events]
[Filter Timeline]
[Open Statistics]
```

The view should show:

* direction;
* count;
* involved Tasks;
* dwell/gap metrics;
* ping-pong indication where supported;
* direct Event/Evidence navigation.

Visualization is discovery, not proof.

Always provide a path back to concrete Timeline Evidence.

---

# 22. AI Role

AI should act as:

> **Evidence Navigator + Engineering Explainer + Investigation Assistant**

It should not behave like a generic chatbot detached from BTFViewer.

AI should help users:

* interpret Findings;
* explain Cursor Regions;
* prioritize suspicious metrics;
* investigate timing tails;
* investigate Migration/Core imbalance;
* verify hypotheses against Trace Evidence;
* compare Traces;
* identify the next useful BTFViewer action.

The existing AI design already emphasizes Findings, verification, Statistics pages, timestamps, p95/p99, and evidence-backed reasoning, so the UI should expose that workflow rather than hide it inside prompts. 

---

# 23. AI Landing Page

Start with investigation intent rather than an empty conversation.

```text
Trace: candidate.btf
Scope: C1–C2 · 282 µs
Filters: Task Worker[3]

What do you want to investigate?

[Explain Findings]
[Explain Cursor Region]
[Investigate Top Issue]
[Check Migrations]
[Compare Traces]

More analyses ▾

Ask anything about this trace…
```

Group templates by intent:

## Start

* Explain Findings
* Triage Findings

## Investigate

* Investigate
* Explain Region
* Highest Latency
* WCET / Hot CPU
* Task Profile

## SMP

* Migration Thrash
* Core Balance

## Verify

* Verify Finding
* Explain Finding
* Auto Investigate

## Compare

* Compare Open Traces
* Diagnostic Report

Low-frequency options should live under:

```text
More analyses ▾
```

---

# 24. AI Context

Always show the AI's current context.

Example:

```text
Trace: candidate.btf
Scope: C1–C2 · 282 µs
Filters: Task Worker[3]
Context: Compact
```

The user should never need to guess:

* which Trace AI is discussing;
* whether Scope is Full Trace or C1–Cn;
* whether Filters are applied;
* whether context is stale.

---

# 25. AI Evidence-First Response Design

Prefer:

```text
Summary

Evidence

Confidence

Next check
```

Example:

```text
Summary

Worker[3] shows a long execution-time tail.

Evidence

p50     21 µs
p99     48 µs
max    113 µs

WCET at 1.487 ms ↗

Confidence

High · Directly observed

Next check

Open Response Time → Worker[3]
```

Avoid large unstructured analytical prose blocks.

---

# 26. AI Confidence and Evidence Vocabulary

## Confidence

* High
* Medium
* Low

## Evidence strength

* Directly observed
* Strong correlation
* Possible explanation
* Insufficient evidence

Important rules:

* distinguish Observation from Interpretation;
* do not present correlation as causation;
* reference Trace Evidence for important claims;
* use the same vocabulary in AI reports where practical.

---

# 27. AI Actionable Links

AI Evidence should be actionable.

Examples:

```text
[Jump to 1.487 ms]
[Open Response Time]
[Highlight Worker[3]]
[Zoom C1–C2]
```

These actions must reuse BTFViewer's normal:

* Scope model;
* Filter model;
* Highlight model;
* Cursor model;
* Evidence Navigation.

AI must not implement a parallel navigation system.

---

# 28. AI Busy, Failure, and Privacy UX

While AI is running:

* keep Timeline responsive;
* keep previous Conversation visible;
* keep Cancel available when supported;
* disable only conflicting actions;
* show concise status;
* keep Provider/Model secondary.

On failure:

* preserve the user's prompt where possible;
* provide retry where appropriate;
* translate provider/network failures into actionable messages;
* do not use raw exceptions as the primary UI.

Privacy should be understandable in plain language.

Example:

```text
Local AI
Trace data stays on this computer
```

```text
Cloud AI
Scoped trace information may be sent to the configured provider
```

Networking and TLS details belong in Advanced Settings.

---

# 29. Trace Compare

Trace Compare should answer:

> Did the Candidate improve or regress relative to the Baseline?

The first view should be decision-oriented.

Example:

```text
Baseline                      Candidate
baseline.btf                  candidate.btf
Scope: Full Trace             Scope: C1–C2 · 4.8 ms

3 REGRESSIONS    5 IMPROVEMENTS    1 WARNING

Largest regression

Response p99
48 µs → 61 µs
+13 µs (+27%)

Why?
Response tail moved with mutex blocking.

[Inspect Baseline] [Inspect Candidate]
```

The existing Compare design already centers Baseline/Candidate and changed metrics, so the UX should make those results easier to act on rather than introduce another comparison model. 

---

# 30. Trace Compare Ordering

Recommended order:

1. Regressions
2. Major Improvements
3. Validation Warnings
4. Lower-impact changes
5. Unchanged detail

Users usually enter Compare to answer:

> Did I make anything worse?

Regressions therefore belong first.

---

# 31. Delta Presentation

Show both absolute and relative delta.

Preferred:

```text
48 µs → 61 µs
+13 µs (+27%)
```

Do not use percentage alone when the baseline is small.

---

# 32. Compare to Decision

Trace Compare should not end at a Delta table.

It should help users answer:

* Is the change acceptable?
* Is there a meaningful Regression?
* Is further investigation required?
* Did the targeted metric improve?
* Did another metric regress?

Avoid automatic pass/fail conclusions unless explicit engineering thresholds exist.

---

# 33. Find

Recommended layout:

```text
Find task, annotation…

Match: Contains ▾

3 of 18 matches

[Previous] [Next]
```

The user should always know:

* total number of matches;
* current match;
* how to navigate Previous/Next.

Selecting a match should:

* center Timeline;
* Highlight the match;
* preserve Scope unless explicitly requested otherwise.

Long Match Mode explanations belong in Contextual Help rather than permanent panel text.

---

# 34. Marks, Bookmarks, and Annotations

Keep these concepts distinct.

## Cursor

Temporary measurement / investigation point.

## Bookmark

Saved location intended for later return.

## Annotation

Human-written note tied to Trace time.

Recommended controls:

```text
Bookmarks | Annotations

Range
C1–C2 · 282 µs

[Import Marks] [Export Marks]

[Import Session] [Export Session]
```

Avoid generic `Marker` terminology when the actual object type is known.

---

# 35. Legend

Interactive Legend entries must look interactive.

Provide:

* pointer cursor;
* Hover state;
* Active state;
* concise Tooltip;
* clear distinction between Highlight and Filter;
* visible Filter state;
* obvious reset behavior.

Legend interaction should reuse the same Task/Core Selection and Filter models as the rest of the application.

---

# 36. Command Palette

The Command Palette supports expert productivity without Toolbar clutter.

It should:

* show keyboard shortcuts;
* show useful disabled commands when appropriate;
* explain prerequisites;
* support synonyms;
* keep command names aligned with Menus;
* support keyboard-only execution.

Example:

```text
Fit Cursor Range                         Ctrl+R
```

Disabled example:

```text
Compare Traces
Unavailable — open at least two traces
```

---

# 37. Settings

Organize Settings by user intent.

## Appearance

* Theme
* UI Font
* Timeline Font
* Colorblind-safe Palette

## Display

* Grid
* STI
* Analysis Tab Visibility
* Overlays

## Layout

* Orientation
* Row Size
* Label Dimensions
* Panel Defaults
* Cursor Limits

## AI

1. Enable AI
2. Provider / Preset
3. Model
4. Authentication / Connection
5. Response Language
6. Context Level
7. Privacy / Redaction
8. Advanced Networking / TLS

Common settings should not require navigating advanced networking details.

---

# 38. Application State UX

## Loading

Show meaningful stages:

```text
Reading trace…
Parsing events…
Building Timeline…
Computing Statistics…
```

Do not use fake precision when progress cannot be measured.

---

## Empty

Examples:

```text
Open a BTF trace to begin.
```

```text
Place two cursors to measure a range.
```

```text
Open at least two traces to compare.
```

An Empty State should explain why content is unavailable and what the user can do next.

---

## Disabled

Disabled actions should explain prerequisites.

Examples include:

* multi-core requirement;
* Cursor-count requirement;
* multi-Trace requirement;
* AI configuration requirement;
* unavailable data type.

---

## Error

Errors should explain:

1. what failed;
2. which Trace/file is affected;
3. why, when known;
4. what the user can do next.

Example:

```text
Could not open trace

example.btf contains an invalid timestamp near line 482.
```

Raw technical details may remain available for debugging, but they should not be the primary message.

---

# 39. Typography and Information Density

BTFViewer should retain engineering-tool density without relying on unusually small text.

Define three main text roles:

## Section Heading

Major analytical structure.

## Body / Metric

Normal controls, tables, and values.

## Secondary Metadata

Scope, units, hints, confidence.

Avoid:

* persistent 9–10 px explanatory text;
* oversized headings;
* excessive whitespace;
* excessive borders;
* routine horizontal scrolling;
* clipped button labels.

---

# 40. Numeric Presentation

Engineering tables should:

* right-align numeric values;
* keep units consistent within columns;
* use appropriate precision;
* align comparable values visually;
* avoid unnecessary raw timestamps;
* apply consistent µs/ms/s conversion.

Example:

```text
 21.4 µs
 48.1 µs
113.0 µs
```

---

# 41. Color Roles

Separate Data Colors from Semantic Colors.

## Data Colors

Used for:

* Task identity;
* Core identity;
* Heatmaps;
* data-series distinction.

## Semantic Colors

Used for:

* Regression / Error;
* Warning;
* Improvement;
* Selection / Focus.

Do not reuse semantic Warning/Error colors as arbitrary Task identity colors when it creates ambiguity.

---

# 42. Colorblind Safety

Important meaning must not depend on color alone.

Use combinations of:

* text;
* icons;
* numeric values;
* borders;
* patterns;
* shape;
* color.

Validate:

* Task/Core distinction;
* Selection;
* Highlight;
* Severity;
* Regression/Improvement;
* Heatmaps;
* Migration views.

---

# 43. Light and Dark Themes

Validate both themes for:

* Timeline;
* Grid;
* Task/Core colors;
* selected segments;
* Cursors;
* Marks;
* Statistics;
* Findings;
* Heatmaps;
* Migration views;
* AI Conversation;
* Trace Compare;
* Tooltips;
* Evidence links;
* Disabled controls.

Neither theme should behave like a partially supported mode.

---

# 44. High-DPI and Responsive Desktop

Test:

* high-DPI scaling;
* long Task names;
* long translated labels;
* narrow Analysis Panels;
* Toolbar overflow;
* Statistics cards;
* AI controls;
* Find controls;
* Cursor labels.

Define intentional behavior.

## Wide

* Full Timeline + Analysis Panel
* Full Toolbar labels where appropriate

## Medium

* Narrower Analysis Panel
* Shorter helper text
* Compact Toolbar labels where necessary

## Narrow

* Analysis Panel can Hide / Show
* Secondary Toolbar actions move to overflow
* Normal font sizes remain
* Statistics avoid whole-window horizontal scrolling

Do not use smaller fonts as the primary responsive strategy.

---

# 45. Workspace Persistence

Remember useful workspace preferences such as:

* Analysis Panel width;
* Theme;
* appropriate layout settings;
* appropriate Statistics collapse state.

Do not unexpectedly restore:

* stale temporary Filters;
* invalid Cursor state;
* invalid Scope from another Trace.

Explicitly define:

```text
Session-persistent state
Application-persistent state
```

---

# 46. Onboarding

Use lightweight first-run guidance.

Example:

```text
New to BTFViewer?

Start with Statistics → Analysis Findings.

[Show Me] [Dismiss]
```

Requirements:

* dismissible;
* remember dismissal;
* provide direct navigation;
* avoid modal walkthroughs;
* avoid teaching advanced features during first use.

---

# 47. Contextual Help

Prefer Contextual Help over permanently visible explanatory text.

Move long explanations to:

* Tooltips;
* Info buttons;
* Help affordances;
* Documentation.

Keep prerequisite information visible when it is necessary to understand the current state.

---

# 48. Developer UX Rules

1. Keep Timeline as the Evidence layer.
2. Keep Scope explicit.
3. Distinguish Scope, Filter, Selection, and Highlight.
4. Do not allow interpretation-changing state to remain invisible.
5. Give every Filter a visible state and reset path.
6. Make time-related analytical results navigate to Evidence when practical.
7. Preserve Timeline position unless navigation is explicitly requested.
8. Preserve Cursors and relevant context across Analysis surfaces.
9. Use C1–Cn consistently.
10. Reuse canonical terminology.
11. Keep primary actions visible.
12. Put advanced variants in Menu, Overflow, Command Palette, or Settings.
13. Do not add Toolbar buttons for rarely used actions.
14. Explain disabled prerequisites.
15. Avoid modal dialogs for information required during Timeline inspection.
16. Do not hide important state only in Tooltips.
17. Do not use color as the only status indicator.
18. Preserve keyboard access for important actions.
19. Validate narrow panels and High-DPI.
20. Validate Light, Dark, and Colorblind-safe modes.
21. Keep GUI, reports, CLI, documentation, and AI terminology synchronized.
22. Prefer a path back to Evidence over another isolated visualization.
23. Make AI reuse the normal Scope, Filter, Highlight, Cursor, and Evidence models.
24. Treat Compare as an input to Decision, not the final user goal.

---

# 49. UX Review Checklist

For every significant UI change, verify:

* [ ] Is the main action obvious?
* [ ] Is the active Trace obvious?
* [ ] Is current Scope obvious?
* [ ] Are Scope and Filter semantically distinct?
* [ ] Are active Filters visible?
* [ ] Can Filters be cleared easily?
* [ ] Is Selection distinguishable from Highlight?
* [ ] Is Highlight distinguishable from Filter?
* [ ] Does the feature preserve Timeline context where appropriate?
* [ ] Can analytical results navigate to Evidence?
* [ ] Does Evidence Navigation avoid unintended state changes?
* [ ] Are disabled states explained?
* [ ] Is the Empty State useful?
* [ ] Is the Loading State understandable?
* [ ] Are errors actionable?
* [ ] Does the Narrow layout work?
* [ ] Does High-DPI work?
* [ ] Does Light Mode work?
* [ ] Does Dark Mode work?
* [ ] Does Colorblind-safe mode work?
* [ ] Is keyboard access preserved?
* [ ] Is terminology consistent?
* [ ] Is Hidden State minimized?
* [ ] Is there a path back to Timeline Evidence?
* [ ] Is the next useful action obvious?
* [ ] Does the feature support the overall investigation workflow?

---

# 50. Implementation Roadmap

The UX Design Guide defines the interaction model and design rules.

Implementation priority is maintained separately for remaining steps.

## Step 1 — Core Clarity and Investigation Foundation

**Completed.** Product behavior is documented in:

* [`BTFViewer/README.md`](../BTFViewer/README.md) / [`README_zh-TW.md`](../BTFViewer/README_zh-TW.md) — terminology, status-bar Scope/Filters, Selection vs Highlight, Fit Trace / Fit Cursors, Findings **Investigate**
* [`BTFViewer/WORKFLOWS.md`](../BTFViewer/WORKFLOWS.md) / [`WORKFLOWS_zh-TW.md`](../BTFViewer/WORKFLOWS_zh-TW.md) — SEE → TRIAGE → SCOPE → INVESTIGATE
* [`BTFViewer/STATISTICS.md`](../BTFViewer/STATISTICS.md) / [`STATISTICS_zh-TW.md`](../BTFViewer/STATISTICS_zh-TW.md) — triage-first order, Scope/Filtered indicators, Findings Evidence line

Focus (shipped):

* canonical terminology;
* Investigation Context;
* Filters;
* Task/Core model;
* Cursors;
* Triage-first Statistics;
* Findings;
* Find;
* Marks;
* Legend;
* Toolbar and basic Timeline interaction;
* basic application states.

---

## Step 2 — Evidence-Driven Analysis and Guided Investigation

**Complete.** Behavior is documented in `BTFViewer/README.md`, `WORKFLOWS.md`,
`STATISTICS.md`, and `AI.md` (Evidence Navigation, Findings inbox, Migration
corridor detail, Compare → Decision, AI Evidence / Confidence / Privacy,
exported context, Command Palette, context preservation exceptions).

Deferred polish items live in Step 3.

---

## Step 3 — Polish, Accessibility and Validation

See:

```text
TODO-step3.md
```

Focus:

* Loading / Empty / Disabled / Error coverage;
* Typography;
* Numeric Presentation;
* Semantic Colors;
* Accessibility;
* High-DPI;
* Responsive Desktop;
* Settings;
* Workspace persistence;
* Onboarding;
* Contextual Help;
* cross-surface audits;
* UX regression testing;
* end-to-end new-user validation.

The implementation model is:

```text
FOUNDATION
    ↓
EVIDENCE-DRIVEN WORKFLOW
    ↓
POLISH & VALIDATION
```

---

# 51. Final UX Direction

BTFViewer should **not** reduce its engineering depth to become easier to use.

Instead, organize that depth around a visible investigation process:

```text
Timeline
   ↓
Statistics / Findings
   ↓
Scope
   ↓
Detailed Analysis
   ↓
Timeline Evidence
   ↓
Verification / AI
   ↓
Trace Compare
   ↓
Decision
```

Or, at the product level:

```text
SEE
 ↓
TRIAGE
 ↓
SCOPE
 ↓
INVESTIGATE
 ↓
EVIDENCE
 ↓
VERIFY
 ↓
COMPARE
 ↓
DECIDE
```

The highest-level design rule is:

> **Every BTFViewer analysis should make the current Scope clear, expose the Evidence behind the result, preserve investigation context, and make the next useful action obvious.**

This approach keeps BTFViewer's expert RTOS Trace-analysis depth while substantially reducing the learning and navigation burden for new users.

