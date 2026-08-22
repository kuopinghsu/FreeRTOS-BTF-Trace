# BTFViewer UX Improvement TODO — Step 1

Step 1 establishes the core interaction model for BTFViewer.

The focus is not to add new analysis capabilities. The goal is to make the
existing interface predictable and establish the shared UX concepts required
by Statistics, Migration Analysis, AI, and Trace Compare.

> **Step defines implementation sequence. Priority defines importance within
> the step.**

## Step 1 Goal

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

- [ ] Standardize `Full Trace`.
- [ ] Standardize `Scope`.
- [ ] Standardize `C1–Cn`.
- [ ] Standardize `Filter`.
- [ ] Standardize `Selection`.
- [ ] Standardize `Highlight`.
- [ ] Standardize `Evidence`.
- [ ] Standardize `Fit Trace`.
- [ ] Standardize `Fit Cursors`.
- [ ] Standardize `Baseline` and `Candidate`.
- [ ] Standardize `Regressed` and `Improved`.
- [ ] Define Scope as the analyzed time region.
- [ ] Define Filter as the included data subset inside the Scope.
- [ ] Define Selection as the object currently selected for inspection or
      interaction.
- [ ] Define Highlight as visual emphasis that does not change analytical
      input.
- [ ] Never silently convert Selection or Highlight into Filter.
- [ ] Apply the terminology consistently to GUI labels and tooltips.

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

- [ ] Show the active Trace.
- [ ] Show the active Scope.
- [ ] Show `Full Trace` when no cursor-defined Scope is active.
- [ ] Show `C1–Cn · duration` for cursor-defined Scope.
- [ ] Show current zoom state.
- [ ] Update immediately when cursors or relevant state changes.
- [ ] Keep the Context Bar compact.
- [ ] Avoid duplicating information already clearly visible nearby.

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

- [ ] Represent active Filters as visible chips.
- [ ] Show Task Filters.
- [ ] Show Core Filters where applicable.
- [ ] Show Migration Filters.
- [ ] Provide `×` to clear an individual Filter.
- [ ] Provide `Clear All`.
- [ ] Preserve Filters while switching relevant Analysis Tabs.
- [ ] Reflect Legend-originated Filters in the same model.
- [ ] Never silently convert Selection into Filter.
- [ ] Never silently convert Highlight into Filter.
- [ ] Indicate filtered state in Statistics.
- [ ] Reserve the same Filter representation for AI context in Step 2.

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

- [ ] Make Task/Core View Modes mutually exclusive.
- [ ] Clearly indicate the active View Mode.
- [ ] Preserve Timeline position when switching modes.
- [ ] Preserve Zoom when switching modes.
- [ ] Preserve Cursors when switching modes.
- [ ] Preserve Scope when switching modes.
- [ ] Define one Task Selection behavior.
- [ ] Define one Core Selection behavior.
- [ ] Define one Task Highlight behavior.
- [ ] Define one Core Highlight behavior.
- [ ] Distinguish View Mode from Selection.
- [ ] Distinguish Selection from Highlight.
- [ ] Distinguish Highlight from Filter.
- [ ] Distinguish Selection from Filter.
- [ ] Reuse the same semantics in Statistics.
- [ ] Reuse the same semantics in Legend.
- [ ] Reserve the same semantics for Migration and AI.

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

- [ ] Keep stable C1–Cn numbering.
- [ ] Show exact timestamps.
- [ ] Show earliest-to-latest Span.
- [ ] Show adjacent Cursor Delta where useful.
- [ ] Improve Cursor marker contrast.
- [ ] Make Cursor deletion discoverable.
- [ ] Keep `Fit Cursors` behavior explicit.
- [ ] Update Scope immediately when the cursor-defined range changes.
- [ ] Preserve Cursors across Analysis Tabs.
- [ ] Define Cursor-limit behavior.
- [ ] Handle overlapping or closely spaced Cursor labels.

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

- [ ] Reorganize the default Statistics section order.
- [ ] Keep expert-level sections available.
- [ ] Show current Scope at the top.
- [ ] Show Filtered state when relevant.
- [ ] Visually separate Triage from detailed analysis.
- [ ] Preserve section collapse/expand state.
- [ ] Preserve custom section ordering if supported.

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

- [ ] Give each Finding a clear Severity.
- [ ] Use a concise problem-oriented title.
- [ ] Show the most relevant supporting metric.
- [ ] Show concrete Evidence metadata when already available.
- [ ] Add `Investigate`.
- [ ] Route `Investigate` to the relevant Statistics section.
- [ ] Preserve Scope while following a Finding.
- [ ] Preserve relevant Filters.
- [ ] Distinguish Observation from Interpretation.
- [ ] Reserve a consistent `Show Evidence` action for Step 2.
- [ ] Reserve `Ask AI` for Step 2 when the AI investigation workflow is
      enabled.
- [ ] Avoid unsupported root-cause statements.

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

- [ ] Show current match position as `N of M`.
- [ ] Keep Previous/Next visible.
- [ ] Center Timeline on the selected match.
- [ ] Highlight the selected result.
- [ ] Preserve Scope unless explicitly changed.
- [ ] Preserve Filters unless explicitly changed.
- [ ] Move long Match Mode explanations to Tooltip/Help.
- [ ] Add useful empty-result feedback.
- [ ] Preserve keyboard navigation.
- [ ] Use consistent behavior for Task names and annotations.

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

- [ ] Keep Cursor, Bookmark, and Annotation as separate concepts.
- [ ] Use `Bookmarks` and `Annotations` explicitly.
- [ ] Show cursor-defined ranges separately.
- [ ] Normalize `Import Marks` / `Export Marks`.
- [ ] Normalize `Import Session` / `Export Session`.
- [ ] Make Bookmark navigation return to its Timeline position.
- [ ] Make Annotation navigation return to its timestamp.
- [ ] Preserve names and notes during session import/export.
- [ ] Avoid generic `Marker` terminology when the object type is known.

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

- [ ] Use pointer cursor for interactive entries.
- [ ] Add Hover state.
- [ ] Add Selected state where applicable.
- [ ] Add Highlight state where applicable.
- [ ] Add Filtered state where applicable.
- [ ] Add concise Tooltips.
- [ ] Distinguish Selection from Highlight.
- [ ] Distinguish Highlight from Filter.
- [ ] Reflect persistent Legend Filters in the Context Bar.
- [ ] Provide an obvious Filter reset path.
- [ ] Preserve relevant Legend state across Analysis Tabs.

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

- [ ] Group Open separately.
- [ ] Group Zoom/Fit actions.
- [ ] Group View Mode actions.
- [ ] Group investigation entry points.
- [ ] Keep `Fit Trace` and `Fit Cursors` distinct.
- [ ] Show relative Zoom.
- [ ] Show physical scale where practical.

Example:

    25% · 120 µs/pixel

- [ ] Move low-frequency actions to Menu or Overflow.
- [ ] Prevent label truncation at normal desktop widths.
- [ ] Keep Tooltips concise.
- [ ] Keep terminology consistent with Menus.
- [ ] Do not add Step 2 feature buttons simply to expose future workflows.

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

- [ ] Show Task.
- [ ] Show Core.
- [ ] Show start/end time.
- [ ] Show duration.
- [ ] Avoid embedding full Statistics in Hover.
- [ ] Avoid obscuring the selected segment.
- [ ] Normalize frequent right-click actions.
- [ ] Keep drag behavior consistent.
- [ ] Keep click behavior consistent.
- [ ] Keep double-click behavior consistent.
- [ ] Keep wheel/trackpad behavior consistent.
- [ ] Avoid conflicting shortcuts.
- [ ] Keep keyboard alternatives for important actions.

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

- [ ] Replace meaningless blank panels with useful Empty States.
- [ ] Explain Cursor-count prerequisites.
- [ ] Explain multi-core prerequisites.
- [ ] Explain multi-trace prerequisites.
- [ ] Explain AI configuration prerequisites where AI entry points exist.
- [ ] State what operation failed in user-facing Errors.
- [ ] Identify the affected file or Trace.
- [ ] Explain the reason when known.
- [ ] Suggest a next action when possible.
- [ ] Keep raw technical details secondary or expandable.
- [ ] Avoid showing Python exceptions as the primary Error message.

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