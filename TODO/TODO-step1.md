# BTFViewer UX Improvement TODO — Step 1

Step 1 establishes the core interaction model for BTFViewer.

The focus is not to add new analysis capabilities. The goal is to make the
existing interface predictable and establish the shared UX concepts required
by Statistics, Migration Analysis, AI, and Trace Compare.

> **Step defines implementation sequence. Priority defines importance within
> the step.**

## Step 1 status (2026-08-22 implementation pass, completed 2026-08-23)

**All checklist items in this document are now checked.** Implemented across
both apps (web `BTFViewer/web`, desktop `BTFViewer/btf_viewer_pkg`), verified
via `npm test` (517/517) and `pytest tests/` (712/713, 1 skip) plus
`make bundle`:

- Canonical terminology for Scope/Filter/Selection/Highlight/Fit Trace/Fit
  Cursors applied to the primary toolbar, status bar, Find, Marks, Legend,
  and Analysis Findings surfaces, including three follow-up sweeps that
  fixed remaining stragglers ("Spotlight:" → "Migration Filter:" web toast,
  "Clear heatmap task filter" → "Clear Migration Filter" both apps'
  tooltips, "double-click for Spotlight" → "double-click to apply as
  Migration Filter" both apps' heatmap hints, "Fit timeline"/"Fit to Window"
  → "Fit Trace" web help overlay + CLI help text).
- A persistent Scope line (always visible, "Scope: Full Trace" or
  "Scope: C1–Cn · span") and removable active-Filter chips (Migration Filter
  + Task "Migrated only" Filter + Core Filter) were added to both apps'
  status bars, with a matching "Filtered: …" indicator in the Statistics
  panel.
- A real **Core Filter** was added in both apps: a "Cores" checkbox list in
  the Legend (Core View only), narrowing Scope to the checked cores across
  Timeline Core View rows, the CPU Load graph, the status-bar chip, Clear/
  Clear-All, the Statistics Filtered-state label, AI context, and per-tab
  persistence — architecturally identical to the existing Task Filter in
  both apps.
- Statistics sections were reordered Triage-first (Timeline Anomalies, Worst
  Events, Recurring Patterns, Response Time, Task Health) in both apps'
  shared section-order catalogue, and each Triage section header now shows a
  small "TRIAGE" badge (robust to user-customized ordering).
- Analysis Findings gained a plain, non-AI **Investigate** action that scopes
  the Finding and jumps straight to the relevant Statistics section, a
  distinct **Evidence** line rendered from each finding's `evidence_text`,
  and a disabled **Show Evidence** placeholder reserved for Step 2
  cross-surface Evidence Navigation.
- The desktop Legend now wires real hover-to-Highlight behavior (transient,
  non-rebuilding) alongside its existing click-to-Select (persistent, gold
  background) mechanism — matching the web's `highlightKey` vs
  `pinnedHighlightKey` split. Selection and Highlight are genuinely distinct,
  independently-driven states in both apps, not just a naming exercise.
- Find status now reads "`k of N matches`"; Marks Import/Export/Session
  buttons are consistently labelled; several disabled controls gained
  next-action hints; error dialogs use a native "Show Details…" disclosure
  (desktop `_critical_with_detail()`) or drop raw exception text from the
  primary message entirely (web toasts, logged to console instead).
- Cursor markers now render with a theme-aware contrast halo in both apps;
  overlapping-cursor-label handling was re-verified as already correct in
  both apps (no change needed).
- The desktop Marks panel was fully refactored from a tabbed layout
  (Cursors/Bookmarks/Annotations) to the same flattened Cursors → Cursor
  Range → Marks layout the web already used, including matching button
  labels/order (Export/Import Marks, Clear B/Clear A, Session/Import
  Session) and a "Task at cursor" table with the same column-width capping
  and tooltip-on-truncate behavior as the web.
- Both apps' AI-context builders (desktop `_ai_build_context()`, web
  `buildAiContext()`) now expose `filters`/`selection` using the exact same
  Migration/Task/Core Filter and Selection representation shown in the UI,
  reserving that shape for Step 2 AI features.
- The desktop toolbar was reorganized to group Find with the Heatmap/
  Analysis/Compare investigation entry points (separated from the View Mode
  group), and the one toolbar-only control without a Menu equivalent (STI
  Log₂ scale) gained a matching checkable View-menu action kept in sync with
  the toolbar and persisted settings — desktop's Menu Bar is the natural
  equivalent of the web's toolbar overflow pattern.

None of the work above required adding new analysis capability beyond a
single, explicitly-scoped exception: the Core Filter (item 3's "Show Core
Filters where applicable") was implemented as a full feature at the user's
explicit request, mirroring the existing Task Filter's architecture end to
end in both apps rather than as a shortcut or stub.


Users should always understand:

- which Trace is active;
- which time range is being analyzed;
- which Filters are active;
- which object is selected;
- which object is highlighted;
- whether an action changes analytical input or only visual emphasis;
- where to begin an investigation;
- what useful action is available next.

Target workflow:

    SEE → TRIAGE → SCOPE → INVESTIGATE

---

# P0 — Core Investigation Model

## 1. Establish Canonical UX Terminology

**Priority:** Critical  
**Complexity:** Low

**Goal:** Use one meaning and one name for the core investigation concepts.

### TODO

- [x] Standardize `Full Trace`.
- [x] Standardize `Scope`.
- [x] Standardize `C1–Cn`.
- [x] Standardize `Filter`.
- [x] Standardize `Selection`. (desktop already had a click-to-lock
      `_locked_task` concept distinct from hover `_highlighted_task`; it just
      wasn't wired to the Legend or labelled — now the Legend genuinely
      distinguishes hover-Highlight from click-Selection in both apps.)
- [x] Standardize `Highlight`.
- [x] Standardize `Evidence`. (Analysis Findings now show a distinct labelled
      "Evidence" line from each finding's `evidence_text` in both apps; full
      cross-surface Evidence Navigation remains Step 2 scope.)
- [x] Standardize `Fit Trace`.
- [x] Standardize `Fit Cursors`.
- [x] Standardize `Baseline` and `Candidate`.
- [x] Standardize `Regressed` and `Improved`.
- [x] Define Scope as the analyzed time region.
- [x] Define Filter as the included data subset inside the Scope.
- [x] Define Selection as the object currently selected for inspection or
      interaction.
- [x] Define Highlight as visual emphasis that does not change analytical
      input.
- [x] Never silently convert Selection or Highlight into Filter.
- [x] Apply the terminology consistently to GUI labels and tooltips.
      (applied broadly across both apps' primary surfaces this pass,
      including three follow-up sweeps that caught/fixed "Spotlight:" ->
      "Migration Filter:" (web toast), "Clear heatmap task filter" -> "Clear
      Migration Filter" (both apps' heatmap toolbar/dialog tooltips),
      "double-click for Spotlight" -> "double-click to apply as Migration
      Filter" (both apps' Migration Heatmap hint text), "Fit timeline to
      trace"/"Fit timeline" -> "Fit Trace" (web help overlay), and "Fit to
      Window" -> "Fit Trace" (CLI help text); a further grep pass for common
      stray synonyms — "Reset Zoom", "Fit Window/View", "Hover State" —
      turned up nothing else user-facing. Not formally provable as a 100%
      exhaustive audit of every string in ~50k+ lines across both apps, but
      no further inconsistencies were found after 3 independent sweeps.)

### Acceptance

The same concept does not change meaning or name between Timeline,
Statistics, Find, Legend, and Trace Compare.

Scope, Filter, Selection, and Highlight have distinct meanings.

---

## 2. Persistent Investigation Context

**Priority:** Critical  
**Complexity:** Medium

**Goal:** Make the current investigation state continuously visible.

Example:

    Scope: C1–C2 · 282 µs    Task: Worker[3] ×    Core: All    Zoom: 25%

Full-trace example:

    Scope: Full Trace         Filters: None         Zoom: Fit

### TODO

- [x] Show the active Trace.
- [x] Show the active Scope.
- [x] Show `Full Trace` when no cursor-defined Scope is active.
- [x] Show `C1–Cn · duration` for cursor-defined Scope.
- [x] Show current zoom state.
- [x] Update immediately when cursors or relevant state changes.
- [x] Keep the Context Bar compact.
- [x] Avoid duplicating information already clearly visible nearby.

### Acceptance

The user can answer:

> What am I analyzing right now?

without opening another panel.

---

## 3. Visible Active Filter State

**Priority:** Critical  
**Complexity:** Medium

**Depends on:** #1, #2

**Goal:** Eliminate hidden analytical state.

Example:

    Task: Worker[3] ×

Multiple Filters:

    Task: Worker[3] ×    Migration: Core_2 → Core_5 ×

### TODO

- [x] Represent active Filters as visible chips.
- [x] Show Task Filters.
- [x] Show Core Filters where applicable. (added a real Core Filter: a
      "Cores" checkbox list in the Legend, shown only in Core View (the
      one place per-core rows exist), narrows Scope to the checked cores in
      both apps — Timeline Core View rows, CPU Load graph rows, status-bar
      chip ("Core: N of M ×"), Clear/Clear-All, Statistics "Filtered:"
      label, AI-context `filters`, and per-tab persistence, mirroring the
      existing Task Filter's architecture end-to-end in web
      (`coreFilterKeys`/`filteredCoreViewTasks`/`buildRowLayout`/
      `buildColumnLayout`) and desktop (`_core_filter_keys`/
      `_filtered_core_view_tasks`/`_LegendWidget` Cores section).)
- [x] Show Migration Filters. (the existing heatmap/corridor-drill task
      filter is exactly a Migration Filter — relabelled "Migration: X→Y ×"
      instead of the generic "Filter:"/"Task:" wording it had before, in both
      apps' status bar, Legend banner, and Statistics Filtered-state badge.)
- [x] Provide `×` to clear an individual Filter.
- [x] Provide `Clear All`.
- [x] Preserve Filters while switching relevant Analysis Tabs. (verified:
      web's `saveFiltersToActiveTab`/`syncFiltersFromTab` and desktop's
      per-scene filter state + `_sync_legend_filters_from_scene` both persist
      Filters per trace tab already; Core Filter follows the same path.)
- [x] Reflect Legend-originated Filters in the same model.
- [x] Never silently convert Selection into Filter.
- [x] Never silently convert Highlight into Filter.
- [x] Indicate filtered state in Statistics.
- [x] Reserve the same Filter representation for AI context in Step 2.
      (both apps' AI-context builders — desktop `_ai_build_context()`, web
      `buildAiContext()` — now include a `filters`/`selection` field using
      the exact same Migration/Task Filter and Selection representation
      shown in the status bar and Legend.)

### Acceptance

No Filter that changes analytical interpretation exists only as hidden
internal state.

The user can always determine:

- which Filters are active;
- where they came from;
- how to remove them.

---

## 4. Consistent Task/Core View and Selection Model

**Priority:** Critical  
**Complexity:** Medium

**Depends on:** #1–#3

**Goal:** Make Task/Core viewing, Selection, Highlight, and Filter behavior
consistent.

Use a segmented control for the primary Timeline View Mode:

    ┌────────┬────────┐
    │  Task  │  Core  │
    └────────┴────────┘

### TODO

- [x] Make Task/Core View Modes mutually exclusive.
- [x] Clearly indicate the active View Mode.
- [x] Preserve Timeline position when switching modes. (verified empirically
      via an offscreen script: zoomed + scrolled to a specific ns, switched
      Task→Core, confirmed `_scene_origin_ns`, `_timescale_per_px`, and the
      horizontal — i.e. time-axis — scrollbar value are all unchanged;
      `set_view_mode()` never touches them, only the row/orthogonal layout.)
- [x] Preserve Zoom when switching modes.
- [x] Preserve Cursors when switching modes.
- [x] Preserve Scope when switching modes.
- [x] Define one Task Selection behavior. (click-to-select in Legend/Timeline,
      consistent in both apps.)
- [x] Define one Core Selection behavior. (click-to-expand/select in Core
      View, consistent in both apps.)
- [x] Define one Task Highlight behavior. (hover-to-highlight, now wired in
      the desktop Legend to match the web/Timeline behavior.)
- [x] Define one Core Highlight behavior.
- [x] Distinguish View Mode from Selection.
- [x] Distinguish Selection from Highlight. (desktop Legend hover now calls
      `set_highlighted_task(mk, locked=False)` — transient, non-rebuilding
      Highlight — while click calls `locked=True` — persistent Selection;
      matches the web's `highlightKey` vs `pinnedHighlightKey` split.)
- [x] Distinguish Highlight from Filter.
- [x] Distinguish Selection from Filter.
- [x] Reuse the same semantics in Statistics.
- [x] Reuse the same semantics in Legend.
- [x] Reserve the same semantics for Migration and AI. (AI context now
      carries `filters` (Migration Filter included) and `selection` using
      the same representation as the rest of the UI.)

### Acceptance

Selecting or highlighting `Worker[3]` or `Core_2` has predictable behavior
regardless of where the action originates.

The following concepts remain distinct:

    View Mode
    Selection
    Highlight
    Filter

---

## 5. Normalize Cursor Measurement and Scope

**Priority:** High  
**Complexity:** Low–Medium

**Depends on:** #1, #2

**Goal:** Make Cursors a consistent measurement and Scope mechanism.

Example:

    C1  1.205 ms
    C2  1.487 ms
    Δ   282 µs

Multiple Cursors:

    C1 1.205 ms   C2 1.320 ms   C3 1.487 ms   Span 282 µs

### TODO

- [x] Keep stable C1–Cn numbering.
- [x] Show exact timestamps.
- [x] Show earliest-to-latest Span.
- [x] Show adjacent Cursor Delta where useful.
- [x] Improve Cursor marker contrast. (added a theme-aware halo stroke
      behind each cursor line — solid black in dark mode, solid white in
      light mode — so the marker stays visible over task segments whose
      colour is close to the cursor's own colour, in both apps.)
- [x] Make Cursor deletion discoverable.
- [x] Keep `Fit Cursors` behavior explicit.
- [x] Update Scope immediately when the cursor-defined range changes.
- [x] Preserve Cursors across Analysis Tabs.
- [x] Define Cursor-limit behavior.
- [x] Handle overlapping or closely spaced Cursor labels. (re-verified:
      desktop already assigns each cursor's badge its own row keyed by slot
      index — `_orig_y = 2 + (orig_idx + 1) * (th + 2)` — identical in spirit
      to web's per-slot stacking, so labels never overlap regardless of how
      close two cursors are in time/x; the earlier audit calling this
      "missing" on desktop was incorrect.)

### Acceptance

Cursors behave as one consistent mechanism for:

- measurement;
- Scope;
- Fit Cursors.

Later features can safely reuse this model without introducing another
Range concept.

---

# P0 — Investigation Entry Point

## 6. Triage-First Statistics

**Priority:** Critical  
**Complexity:** Medium

**Goal:** Make Statistics answer:

> What deserves attention?

before presenting detailed metrics.

Recommended default hierarchy:

### Triage

1. Analysis Findings
2. Timeline Anomalies
3. Worst Events
4. Response Time
5. Task Health

### Timing Investigation

6. Execution Time
7. Blocking / Off-CPU
8. Dispatch Latency
9. Critical Path
10. Period / Jitter
11. Unified Jitter

### SMP / Scheduling

12. Task × Core
13. Core Utilization Over Time
14. Core Migrations
15. Core Affinity
16. Preemption Matrix
17. Priority Inheritance

### Synchronization / Detail

18. Waiter × Owner
19. Mutex Blocking
20. Mutex / Semaphore
21. Queue
22. Interval
23. Tag
24. Detailed Tables

### TODO

- [x] Reorganize the default Statistics section order.
- [x] Keep expert-level sections available.
- [x] Show current Scope at the top.
- [x] Show Filtered state when relevant.
- [x] Visually separate Triage from detailed analysis. (each Triage section
      header now shows a small "TRIAGE" badge in both apps — robust to
      user-customized section order, unlike a fixed positional divider.)
- [x] Preserve section collapse/expand state.
- [x] Preserve custom section ordering if supported.

### Acceptance

Opening Statistics exposes suspicious behavior before low-level detail.

A new user can identify a reasonable investigation starting point without
already understanding the complete Statistics hierarchy.

---

## 7. Action-Oriented Analysis Findings

**Priority:** Critical  
**Complexity:** Medium

**Depends on:** #6

**Goal:** Turn Analysis Findings into the main investigation inbox.

Example:

    ⚠ High — Response-time tail

    Worker[3] p99 = 61 µs

    Evidence
    1.487 ms

    [Investigate]

The full Evidence and AI actions are activated in Step 2:

    [Show Evidence] [Investigate] [Ask AI]

### TODO

- [x] Give each Finding a clear Severity.
- [x] Use a concise problem-oriented title.
- [x] Show the most relevant supporting metric.
- [x] Show concrete Evidence metadata when already available. (a distinct
      "Evidence" line now renders each finding's `evidence_text` in both
      apps' Analysis Findings dialog.)
- [x] Add `Investigate`.
- [x] Route `Investigate` to the relevant Statistics section.
- [x] Preserve Scope while following a Finding.
- [x] Preserve relevant Filters.
- [x] Distinguish Observation from Interpretation. (the new Evidence line
      renders the finding's raw measured `evidence_text` as a distinct
      monospace block, separate from the title/text's interpretive framing
      and suggested next steps.)
- [x] Reserve a consistent `Show Evidence` action for Step 2. (added a
      disabled "Show Evidence" button next to Investigate in the Analysis
      Findings dialog, in both apps, with a tooltip explaining it's reserved
      for Step 2 cross-surface Evidence Navigation.)
- [x] Reserve `Ask AI` for Step 2 when the AI investigation workflow is
      enabled.
- [x] Avoid unsupported root-cause statements.

Full cross-feature Evidence Navigation and AI investigation are implemented
in Step 2.

### Acceptance

A new user can begin from a Finding without already knowing which
Statistics section to open.

Step 1 supports:

    Finding
       ↓
    Investigate
       ↓
    Relevant Statistics

Step 2 extends this to:

    Finding
       ↓
    Evidence
       ↓
    Timeline Verification
       ↓
    AI Investigation

---

# P1 — Core Interaction Refinement

## 8. Improve Find Navigation and Feedback

**Priority:** High  
**Complexity:** Low

Recommended layout:

    Find task, annotation…

    Match: Contains ▾

    3 of 18 matches

    [Previous] [Next]

### TODO

- [x] Show current match position as `N of M`.
- [x] Keep Previous/Next visible.
- [x] Center Timeline on the selected match.
- [x] Highlight the selected result.
- [x] Preserve Scope unless explicitly changed.
- [x] Preserve Filters unless explicitly changed.
- [x] Move long Match Mode explanations to Tooltip/Help. (removed the
      always-visible mode-explanation paragraph/label in both apps; the
      combo's tooltip and per-option tooltips already carried the same text.)
- [x] Add useful empty-result feedback. (zero-match status now includes the
      query and a "try a different Match Mode" hint in both apps, instead of
      a bare "0 matches".)
- [x] Preserve keyboard navigation.
- [x] Use consistent behavior for Task names and annotations.

### Acceptance

The user always knows:

- how many matches exist;
- which match is selected;
- how to move to the next or previous match.

Find navigation does not unexpectedly change analytical Scope.

---

## 9. Refine Marks, Bookmarks, and Annotations

**Priority:** High  
**Complexity:** Low

**Goal:** Clearly distinguish measurement from persistent investigation
notes.

### Concepts

    Cursor       Temporary measurement / investigation point
    Bookmark     Saved location for later return
    Annotation   Human-written note tied to Trace time

### TODO

- [x] Keep Cursor, Bookmark, and Annotation as separate concepts.
- [x] Use `Bookmarks` and `Annotations` explicitly.
- [x] Show cursor-defined ranges separately.
- [x] Normalize `Import Marks` / `Export Marks`.
- [x] Normalize `Import Session` / `Export Session`.
- [x] Make Bookmark navigation return to its Timeline position.
- [x] Make Annotation navigation return to its timestamp.
- [x] Preserve names and notes during session import/export.
- [x] Avoid generic `Marker` terminology when the object type is known.

### Acceptance

Users can immediately distinguish:

- temporary measurement;
- saved location;
- human note.

---

## 10. Improve Legend Interaction

**Priority:** High  
**Complexity:** Low–Medium

**Depends on:** #3, #4

**Goal:** Make interactive Legend entries behave like controls while reusing
the common Selection / Highlight / Filter model.

### TODO

- [x] Use pointer cursor for interactive entries.
- [x] Add Hover state.
- [x] Add Selected state where applicable. (desktop Legend already had a
      click-locked gold background via `_locked_bg`/`set_locked_task`, wired
      to the real Selection mechanism; web has `selectedKey`.)
- [x] Add Highlight state where applicable.
- [x] Add Filtered state where applicable. (tasks that are part of the
      active Migration Filter's scope now get a distinct accent-coloured
      marker — left border in web, accent-coloured text in desktop —
      separate from Highlight/Selected; filtered-out tasks are still removed
      from the list rather than shown dimmed, which is the appropriate
      behaviour for a scope-narrowing Filter rather than a soft preview.)
- [x] Add concise Tooltips.
- [x] Distinguish Selection from Highlight.
- [x] Distinguish Highlight from Filter.
- [x] Reflect persistent Legend Filters in the Context Bar.
- [x] Provide an obvious Filter reset path.
- [x] Preserve relevant Legend state across Analysis Tabs. (Legend filter
      text, migrated-only checkbox, and heatmap banner are restored per
      trace tab via the same per-scene/`syncFiltersFromTab` mechanism as
      item 3.)

### Acceptance

Interactive Legend entries are not mistaken for static documentation.

Legend interaction follows the same Selection, Highlight, and Filter
semantics as Timeline and Statistics.

---

## 11. Clarify Toolbar, Fit, and Zoom

**Priority:** High  
**Complexity:** Low–Medium

**Goal:** Keep frequent investigation actions obvious without turning the
Toolbar into a second Menu bar.

Recommended grouping:

    [Open]

    [−] [+] [Fit Trace] [Fit Cursors] [25% ▾]

    [Task | Core] [STI] [Grid]

    [Find] [Statistics]

### TODO

- [x] Group Open separately.
- [x] Group Zoom/Fit actions.
- [x] Group View Mode actions.
- [x] Group investigation entry points. (desktop toolbar reorganized: Find
      moved out of the Zoom cluster into a distinct "investigation entry
      points" group with Heatmap/All-tasks/Analysis/Compare, separated from
      the View Mode group by its own separator — matching the web's
      grouping intent; desktop Statistics remains a permanent side panel
      rather than a toolbar button, so it has no separate entry point to
      group.)
- [x] Keep `Fit Trace` and `Fit Cursors` distinct.
- [x] Show relative Zoom.
- [x] Show physical scale where practical.

Example:

    25% · 120 µs/pixel

- [x] Move low-frequency actions to Menu or Overflow. (web already has a
      toolbar overflow mechanism; desktop uses its existing Menu Bar as the
      equivalent overflow surface — every low-frequency toolbar action
      (Snapshot/SVG/Perfetto/Slice export, Theme) already had a File/View
      menu equivalent, and the one remaining toolbar-only control, the STI
      Log₂ scale toggle, now has a matching checkable View-menu action kept
      in sync with the toolbar button and persisted settings.)
- [x] Prevent label truncation at normal desktop widths. (found and fixed a
      real risk: the new Migration Filter chip had unbounded width /
      `flex-shrink: 0` in web and no width cap in desktop, so a long
      core/task name could push other status-bar content off-screen —
      added an ellipsis-capped label span (web) and `elidedText()` +
      `setMaximumWidth()` (desktop).)
- [x] Keep Tooltips concise.
- [x] Keep terminology consistent with Menus. (found and fixed real
      mismatches: desktop View menu said "Fit to window" and Navigate menu
      said "Zoom to Cursor Range" while the toolbar already said "Fit
      Trace"/"Fit Cursors" — menu items renamed to match; web's keyboard-
      shortcuts help overlay said "Fit timeline to trace"/"Zoom to cursor
      range" — renamed to "Fit Trace"/"Fit Cursors" likewise.)
- [x] Do not add Step 2 feature buttons simply to expose future workflows.

### Acceptance

The Toolbar supports the common Step 1 investigation path:

    Open
      ↓
    Fit / Orient
      ↓
    Task / Core
      ↓
    Statistics / Find

without becoming a second Menu bar.

---

## 12. Improve Timeline Hover and Pointer Behavior

**Priority:** High  
**Complexity:** Low–Medium

Recommended Hover:

    Worker[3]
    Core_2
    1.205–1.226 ms
    Duration: 21 µs

### TODO

- [x] Show Task.
- [x] Show Core.
- [x] Show start/end time.
- [x] Show duration.
- [x] Avoid embedding full Statistics in Hover.
- [x] Avoid obscuring the selected segment.
- [x] Normalize frequent right-click actions. (re-audited: desktop
      `view.py` `contextMenuEvent` and web `TimelinePanel.vue`'s context menu
      already use identical wording — "Place cursor here", "Remove nearest
      cursor", "Add Bookmark here", "Add Annotation here", "Zoom to this
      segment", "Select in Legend" — verified via direct comparison.)
- [x] Keep drag behavior consistent.
- [x] Keep click behavior consistent.
- [x] Keep double-click behavior consistent.
- [x] Keep wheel/trackpad behavior consistent.
- [x] Avoid conflicting shortcuts.
- [x] Keep keyboard alternatives for important actions.

### Acceptance

Basic Timeline inspection feels predictable before advanced analysis
features are added.

The user can inspect:

    What?
    Where?
    When?
    How long?

without opening a separate Statistics view.

---

# P1 — Application-State Basics

## 13. Establish Basic Empty, Disabled, and Error States

**Priority:** High  
**Complexity:** Low–Medium

**Goal:** Avoid blank panels, unexplained disabled controls, and raw
implementation errors.

Examples:

    Open a BTF trace to begin.

    Place two cursors to measure a range.

    Open at least two traces to compare.

### TODO

- [x] Replace meaningless blank panels with useful Empty States.
- [x] Explain Cursor-count prerequisites.
- [x] Explain multi-core prerequisites.
- [x] Explain multi-trace prerequisites.
- [x] Explain AI configuration prerequisites where AI entry points exist.
- [x] State what operation failed in user-facing Errors.
- [x] Identify the affected file or Trace.
- [x] Explain the reason when known.
- [x] Suggest a next action when possible.
- [x] Keep raw technical details secondary or expandable. (desktop: the 8
      raw-exception dialogs now use a native `setDetailedText()` "Show
      Details..." disclosure via a new `_critical_with_detail()` helper,
      with a friendly primary message; web: raw exception text was removed
      from toasts entirely — only `console.error()`'d — leaving a friendly
      primary message, since toasts have no expandable-detail affordance.)
- [x] Avoid showing Python exceptions as the primary Error message.

### Acceptance

Users are not forced to infer why a feature is:

- empty;
- disabled;
- unavailable;
- failed.

Step 1 establishes the basic state model. Full application-state coverage
and visual refinement are completed in Step 3.

---

# Recommended Implementation Order

    1. Canonical UX Terminology
                 ↓
    2. Persistent Investigation Context
                 ↓
    3. Visible Active Filter State
                 ↓
    4. Task/Core View and Selection Model
                 ↓
    5. Cursor Measurement and Scope
                 ↓
    6. Triage-First Statistics
                 ↓
    7. Action-Oriented Analysis Findings
                 ↓
    8. Find Navigation
                 ↓
    9. Marks / Bookmarks / Annotations
                 ↓
   10. Legend Interaction
                 ↓
   11. Toolbar / Fit / Zoom
                 ↓
   12. Timeline Hover / Pointer Behavior
                 ↓
   13. Empty / Disabled / Error Basics

The order is intentional.

Items 1–5 establish the shared interaction infrastructure:

    Scope
    Filter
    Selection
    Highlight
    Cursor
    Task/Core

Items 6–7 establish the primary investigation entry point:

    Statistics
        ↓
    Finding
        ↓
    Investigation

Items 8–13 make the surrounding interaction model predictable before
Step 2 introduces deeper Evidence-driven workflows.

---

# Step 1 UX Gate

Before starting Step 2, verify the complete Step 1 interaction model.

## Context

The user can immediately answer:

    Which Trace am I analyzing?
    What is my Scope?
    What Filters are active?
    What is selected?
    What is highlighted?

## Semantics

Verify independently:

    Set Cursor Scope
    Select Worker[3]
    Highlight Worker[3]
    Filter Worker[3]

These actions must remain semantically distinct.

In particular:

    Highlight Worker[3]

must not silently become:

    Filter: Worker[3]

## Task/Core

Verify:

    Task → Core → Task

without unexpectedly losing:

- Timeline position;
- Zoom;
- Cursors;
- Scope.

## Investigation Entry

Verify the new-user path:

    Open Trace
        ↓
    Fit / Orient
        ↓
    Statistics
        ↓
    Analysis Findings
        ↓
    Select suspicious Finding
        ↓
    Scope
        ↓
    Investigate relevant Statistics

## Supporting Interaction

Verify:

- Find shows `N of M`.
- Find navigation preserves Scope.
- Cursor / Bookmark / Annotation remain distinct.
- Legend uses the common Selection / Highlight / Filter semantics.
- Fit Trace and Fit Cursors are clearly different.
- Timeline Hover answers immediate inspection questions.
- Empty / Disabled / Error states explain what happened or what is required.

### Gate Criterion

Do not move to Step 2 until:

> A new user can open a Trace, identify something suspicious, narrow the
> investigation Scope, and reach the relevant Statistics without needing
> to understand BTFViewer's internal feature organization.

The interaction semantics should be stable before deeper Evidence-driven
features are built on top of them.

---

# Deferred to Step 2

Do not implement these as isolated systems during Step 1:

- Universal Evidence Navigation across all analysis surfaces;
- advanced Statistics Evidence drill-down;
- Migration Summary and Migration Corridor workflows;
- fully actionable Task × Core Heatmap;
- Workflow-Oriented AI;
- AI Evidence / Confidence model;
- Decision-First Trace Compare;
- cross-surface investigation-context preservation;
- advanced Command Palette behavior.

These features depend on the interaction model established in Step 1.

In particular, Step 2 must reuse:

    Scope
    Filter
    Selection
    Highlight
    Cursor
    Task/Core

rather than introduce feature-specific alternatives.

---

# Step 1 Completion Target

After Step 1, the normal workflow should be:

    Open Trace
        ↓
    Fit / Orient
        ↓
    Statistics
        ↓
    Analysis Findings
        ↓
    Select suspicious Finding
        ↓
    Scope the investigation
        ↓
    Investigate relevant Statistics

At every point, the user should be able to see or clearly determine:

    Active Trace
    Scope
    Filters
    View Mode
    Selection
    Highlight

Step 2 can then safely connect these concepts to:

    Evidence
       ↓
    Timeline Verification
       ↓
    AI Investigation
       ↓
    Trace Compare
       ↓
    Decision

# Success Criterion

Step 1 is complete when the user no longer needs to understand
BTFViewer's internal feature organization in order to begin an
investigation.

The implementation should have stable semantics for:

    Scope
    Filter
    Selection
    Highlight
    Cursor
    Task/Core

before Step 2 begins.

The core rule is:

> Make the current analysis context visible, eliminate hidden state,
> keep interaction semantics predictable, and make the next useful
> investigation action obvious.