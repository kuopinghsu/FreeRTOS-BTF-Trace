# BTFViewer UX Improvement TODO — Step 2

Step 2 builds on the interaction foundation established in `TODO-step1.md`.

The focus is to connect analytical results to Timeline Evidence and make
Statistics, Migration, AI, and Trace Compare work as one investigation
workflow.

## Step 2 Goal

Target workflow:

INVESTIGATE → EVIDENCE → VERIFY → COMPARE → DECIDE

Step 2 must reuse the shared models established in Step 1:

- Scope
- Filter
- Selection
- Highlight
- Cursor
- Task/Core semantics
- canonical terminology

Do not create feature-specific alternatives for these concepts.

---

# P0 — Evidence and Context Infrastructure

## 1. Universal Evidence Navigation

**Priority:** Critical  
**Complexity:** High

**Depends on:** Step 1 Context, Cursor, Task/Core, and terminology model.

**Goal:** Create one standard way to navigate from analytical results back
to concrete Timeline Evidence.

Use the same navigation pattern across:

- Statistics
- Analysis Findings
- AI
- Find
- Migration analysis
- Trace Compare

Example:

    Response p99    48 µs ↗

### TODO

- [ ] Make Evidence timestamps actionable.
- [ ] Make p95/p99/Max/WCET Evidence actionable where available.
- [ ] Center Timeline on selected Evidence.
- [ ] Place or reuse a cursor where appropriate.
- [ ] Highlight related Task/Core when useful.
- [ ] Preserve Analysis Panel state.
- [ ] Preserve Analysis Panel scroll position.
- [ ] Avoid silently changing Scope.
- [ ] Avoid silently changing Filters.
- [ ] Use one consistent Evidence affordance throughout BTFViewer.
- [ ] Define behavior when multiple representative events exist.
- [ ] Define behavior when exact Evidence cannot be located.

### Acceptance

A suspicious metric, Finding, AI statement, migration event, or comparison
result can reach Timeline Evidence with one predictable action.

---

## 2. Preserve Investigation Context Across Analysis Surfaces

**Priority:** Critical  
**Complexity:** Medium–High

**Depends on:** Step 1 Context model.

**Goal:** Prevent navigation itself from disrupting the investigation.

### TODO

- [ ] Preserve Timeline position.
- [ ] Preserve Zoom.
- [ ] Preserve Cursors.
- [ ] Preserve Scope.
- [ ] Preserve relevant Task/Core Filters.
- [ ] Preserve Statistics scroll position.
- [ ] Preserve Statistics expanded/collapsed state where practical.
- [ ] Preserve AI conversation.
- [ ] Preserve relevant Selection/Highlight state.
- [ ] Define explicit exceptions where navigation intentionally changes context.
- [ ] Ensure Evidence Navigation follows the same rules.

### Acceptance

Switching between analysis surfaces does not unexpectedly destroy the
user's current investigation state.

---

# P0 — Statistics and Findings Investigation

## 3. Standardize Statistics Section Cards

**Priority:** High  
**Complexity:** Medium

**Goal:** Give all Statistics sections a predictable interaction pattern.

Recommended header:

    ▼ Response Time                         Warning
      Scope: C1–C2

### TODO

- [ ] Standardize section-title placement.
- [ ] Standardize severity/status placement.
- [ ] Show Scope where relevant.
- [ ] Show Filtered state where relevant.
- [ ] Standardize collapse/expand controls.
- [ ] Standardize Help affordance.
- [ ] Standardize Plot actions.
- [ ] Standardize Export actions.
- [ ] Preserve collapsed/expanded state.
- [ ] Keep drag/reorder affordance consistent where supported.
- [ ] Avoid oversized headers that reduce data density.

### Acceptance

Users learn one Statistics section interaction model that works everywhere.

---

## 4. Standardize Statistical Distribution Presentation

**Priority:** High  
**Complexity:** Medium

**Goal:** Make timing distributions easier to interpret.

Use:

    Typical → Tail → Worst

Recommended presentation:

| p50 | p95 | p99 | Max |
| ---: | ---: | ---: | ---: |
| 21 µs | 38 µs | 48 µs | 113 µs |

### TODO

- [ ] Present p50 consistently.
- [ ] Present p95 consistently.
- [ ] Present p99 consistently.
- [ ] Present Max/WCET consistently.
- [ ] Keep units consistent within a column.
- [ ] Right-align numeric values.
- [ ] Use appropriate precision.
- [ ] Keep CV/outlier metrics secondary unless directly relevant.
- [ ] Avoid visually over-emphasizing Max when tail values are more informative.
- [ ] Add Evidence Navigation to representative tail events.
- [ ] Add Evidence Navigation to worst-case events.

### Acceptance

Users can distinguish typical, tail, and worst-case behavior at a glance.

---

## 5. Complete Analysis Findings Investigation Actions

**Priority:** Critical  
**Complexity:** Medium

**Depends on:** #1, #3

**Goal:** Complete the Finding → Evidence → Investigation workflow started
in Step 1.

Recommended Finding:

    ⚠ High — Response-time tail

    Worker[3] p99 = 61 µs

    Evidence
    1.487 ms ↗

    [Show Evidence] [Investigate] [Ask AI]

### TODO

- [ ] Activate `Show Evidence`.
- [ ] Route `Show Evidence` through Universal Evidence Navigation.
- [ ] Activate `Investigate`.
- [ ] Route `Investigate` to the relevant Statistics section.
- [ ] Add `Ask AI` when AI is enabled.
- [ ] Preserve Scope.
- [ ] Preserve relevant Filters.
- [ ] Keep severity terminology consistent.
- [ ] Keep Evidence terminology consistent.
- [ ] Distinguish observation from interpretation.
- [ ] Avoid unsupported root-cause statements.
- [ ] Allow Findings to become the main investigation inbox.

### Acceptance

The complete path works:

    Finding
       ↓
    Evidence
       ↓
    Relevant Statistics
       ↓
    Timeline Verification

---

# P1 — Migration and SMP Investigation

## 6. Add Migration Summary and Progressive Drill-Down

**Priority:** High  
**Complexity:** High

**Goal:** Make migration behavior understandable before showing complex
visualizations.

Start with:

- Total Migrations
- Migration Rate
- Most Migrated Task
- Most Active Core Pair
- Median Dwell
- Ping-pong / Thrash indication

### TODO

- [ ] Add a compact Migration Summary.
- [ ] Link Most Migrated Task to Task × Core.
- [ ] Link Most Active Core Pair to Core-Pair detail.
- [ ] Show counts as well as visual intensity.
- [ ] Show rates when Scope duration matters.
- [ ] Show dwell metrics.
- [ ] Show gap metrics where meaningful.
- [ ] Identify likely ping-pong patterns.
- [ ] Avoid overstating causality.
- [ ] Connect migration events to Timeline Evidence.
- [ ] Preserve active Scope during drill-down.
- [ ] Preserve active Task/Core Filters during drill-down.

### Acceptance

A user can understand why a migration pattern is suspicious before
interpreting a heatmap or corridor visualization.

---

## 7. Make Task × Core Heatmap Actionable

**Priority:** High  
**Complexity:** Medium–High

**Depends on:** Step 1 Task/Core model, #1, #6

**Goal:** Turn the Task × Core Heatmap into an investigation entry point.

### TODO

- [ ] Show Task/Core identity on hover.
- [ ] Show scoped execution percentage/value.
- [ ] Make cells selectable.
- [ ] Add `Highlight Task`.
- [ ] Add `Filter Timeline`.
- [ ] Add `Show Migrations`.
- [ ] Reflect persistent Filters in the Context Bar.
- [ ] Preserve selection while opening related Statistics.
- [ ] Preserve Scope.
- [ ] Reuse the Step 1 Task/Core selection model.
- [ ] Provide numeric values so color is not the only signal.

### Acceptance

Selecting a heatmap cell naturally leads to deeper investigation instead
of ending at the visualization.

---

## 8. Add Migration Corridor / Core-Pair Detail

**Priority:** Medium–High  
**Complexity:** High

**Depends on:** #1, #6, #7

Recommended view:

    Core_2 → Core_5

    47 migrations
    Task: Worker[3]
    Median dwell: …
    Ping-pong: …

    [Show Events]
    [Filter Timeline]
    [Open Statistics]

### TODO

- [ ] Show migration direction clearly.
- [ ] Show migration count.
- [ ] Show involved Tasks.
- [ ] Show median dwell.
- [ ] Show gap where useful.
- [ ] Show ping-pong indication where supported.
- [ ] Add `Show Events`.
- [ ] Add `Filter Timeline`.
- [ ] Add `Open Statistics`.
- [ ] Connect individual migration events to Timeline Evidence.
- [ ] Preserve Scope during navigation.
- [ ] Reuse the common Filter model.

### Acceptance

Migration detail leads back to concrete events and relevant Statistics.

---

# P1 — Workflow-Oriented AI

## 9. Redesign AI Around Investigation Intent

**Priority:** High  
**Complexity:** High

**Depends on:** #1, #2 and Step 1 Context model.

**Goal:** Make AI reuse BTFViewer's investigation workflow instead of
becoming an independent chatbot experience.

Recommended landing page:

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

### Group templates by intent

#### Start

- Explain Findings
- Triage Findings

#### Investigate

- Investigate
- Explain Region
- Highest Latency
- WCET / Hot CPU
- Task Profile

#### SMP

- Migration Thrash
- Core Balance

#### Verify

- Verify Finding
- Explain Finding
- Auto Investigate

#### Compare

- Compare Open Traces
- Diagnostic Report

### TODO

- [ ] Show active Trace.
- [ ] Show active Scope.
- [ ] Show relevant Filters.
- [ ] Group templates by investigation intent.
- [ ] Move low-frequency templates under `More analyses`.
- [ ] Keep free-form questions available.
- [ ] Make AI timestamps actionable.
- [ ] Link AI Evidence to Statistics where appropriate.
- [ ] Support Task/Core Highlight from AI.
- [ ] Support C1–Cn navigation.
- [ ] Reuse Universal Evidence Navigation.
- [ ] Reuse the Step 1 Filter and Highlight model.
- [ ] Avoid independent AI-specific navigation semantics.

### Acceptance

AI helps users move through BTFViewer rather than creating a separate
analysis workflow.

---

## 10. Standardize AI Evidence and Confidence Model

**Priority:** High  
**Complexity:** Medium

**Depends on:** #9

**Goal:** Make analytical AI statements easy to evaluate.

Use:

    Summary

    Evidence

    Confidence

    Next check

### Confidence

- High
- Medium
- Low

### Evidence strength

- Directly observed
- Strong correlation
- Possible explanation
- Insufficient evidence

### TODO

- [ ] Separate observations from interpretations.
- [ ] Avoid presenting correlation as causation.
- [ ] Include Evidence references for important claims.
- [ ] Reuse Evidence terminology from the GUI.
- [ ] Reuse Confidence terminology consistently.
- [ ] Align Analysis Findings wording where appropriate.
- [ ] Reuse the same vocabulary in AI-generated reports.
- [ ] Provide actionable `Next check`.
- [ ] Expose actions such as:
  - [ ] Jump to Evidence.
  - [ ] Open Statistics section.
  - [ ] Highlight Task.
  - [ ] Zoom C1–Cn.

### Acceptance

Users can tell which AI statements are directly supported by the trace and
which are interpretations.

---

## 11. Improve AI Busy, Cancel, Failure, and Privacy UX

**Priority:** High  
**Complexity:** Medium

### TODO

- [ ] Keep Timeline responsive while AI runs.
- [ ] Keep existing conversation readable.
- [ ] Keep Cancel visible when cancellation is supported.
- [ ] Disable only conflicting AI actions.
- [ ] Show concise progress/status text.
- [ ] Keep Provider/Model secondary.
- [ ] Preserve the user's prompt after recoverable failures.
- [ ] Translate provider/network failures into actionable messages.
- [ ] Avoid raw exception traces as the primary error UI.
- [ ] Allow retry where appropriate.
- [ ] Clearly label Local AI.
- [ ] Clearly label Cloud AI.
- [ ] Explain the basic data path.
- [ ] Surface Privacy/Redaction settings.
- [ ] Keep endpoint/TLS settings under Advanced.

### Acceptance

AI processing does not block the trace-analysis experience, and users
understand the basic local/cloud data behavior.

---

# P1 — Trace Compare

## 12. Implement Decision-First Trace Compare

**Priority:** High  
**Complexity:** High

**Depends on:** #1 and Step 1 terminology/context model.

**Goal:** Answer the important comparison question before showing detailed
tables.

> Did the Candidate improve or regress relative to the Baseline?

Recommended header:

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

### TODO

- [ ] Show Baseline explicitly.
- [ ] Show Candidate explicitly.
- [ ] Show Scope independently for both traces.
- [ ] Show relevant Filters where applicable.
- [ ] Summarize regression count.
- [ ] Summarize improvement count.
- [ ] Summarize validation warnings.
- [ ] Surface the largest regression first.
- [ ] Show absolute delta.
- [ ] Show relative delta.
- [ ] Add concise `Why?` only when Evidence supports it.
- [ ] Sort regressions before improvements.
- [ ] Put unchanged details after meaningful changes.
- [ ] Add `Inspect Baseline`.
- [ ] Add `Inspect Candidate`.
- [ ] Connect changed metrics to Universal Evidence Navigation.

### Acceptance

The important comparison result is understandable before the user reads a
large detail table.

---

## 13. Connect Trace Compare to Decision

**Priority:** Medium–High  
**Complexity:** Medium

**Depends on:** #12

**Goal:** Make Compare support an engineering decision rather than end at
a delta table.

### TODO

- [ ] Summarize major regressions.
- [ ] Summarize meaningful improvements.
- [ ] Highlight unresolved warnings.
- [ ] Distinguish statistically small changes from engineering-significant changes where data supports it.
- [ ] Preserve Evidence links for important deltas.
- [ ] Provide a concise comparison conclusion.
- [ ] Avoid automatic pass/fail claims when thresholds are not defined.
- [ ] Make next recommended investigation explicit when results are ambiguous.

### Acceptance

Trace Compare helps the user decide whether a change is acceptable, needs
further investigation, or should be rejected.

---

# P2 — Reports and Expert Navigation

## 14. Standardize Exported Investigation Context

**Priority:** Medium–High  
**Complexity:** Medium

**Goal:** Make reports and exports reproducible.

### TODO

- [ ] Include active Trace identity.
- [ ] Include Scope.
- [ ] Include relevant Filters.
- [ ] Include Baseline/Candidate identity for comparisons.
- [ ] Include analysis timestamp where useful.
- [ ] Include important configuration affecting interpretation.
- [ ] Keep exported terminology aligned with GUI terminology.
- [ ] Include Evidence references where practical.

### Acceptance

A report or export clearly states what data and context produced the result.

---

## 15. Improve Command Palette for Expert Navigation

**Priority:** Medium  
**Complexity:** Medium

### TODO

- [ ] Show keyboard shortcuts.
- [ ] Show useful disabled commands instead of silently hiding them.
- [ ] Explain disabled prerequisites.
- [ ] Support synonyms such as:
  - `range`
  - `migration`
  - `theme`
  - `config`
- [ ] Keep command names synchronized with menus.
- [ ] Support keyboard-only execution.
- [ ] Consider recent/frequent command ordering where practical.
- [ ] Keep uncommon actions out of the primary Toolbar.

### Acceptance

Expert users can reach uncommon commands quickly without increasing
Toolbar clutter.

---

## 16. Review Modal Analysis Flows

**Priority:** Medium  
**Complexity:** Medium–High

**Goal:** Keep Timeline Evidence visible while analytical information is
being inspected.

### TODO

- [ ] Identify analysis dialogs that block Timeline interaction.
- [ ] Move persistent analytical information to docked/non-modal surfaces where practical.
- [ ] Keep confirmation dialogs modal only when appropriate.
- [ ] Avoid hiding Evidence behind dialogs.
- [ ] Preserve keyboard focus behavior.
- [ ] Preserve Scope and Filters when opening/closing analysis surfaces.

### Acceptance

Users can inspect Timeline Evidence while reading related analytical
information.

---

# Recommended Implementation Order

    1. Universal Evidence Navigation
                 ↓
    2. Preserve Investigation Context
                 ↓
    3. Statistics Section Cards
                 ↓
    4. Statistical Distribution Presentation
                 ↓
    5. Complete Findings Actions
                 ↓
    6. Migration Summary / Drill-Down
                 ↓
    7. Task × Core Heatmap
                 ↓
    8. Migration Corridor Detail
                 ↓
    9. Workflow-Oriented AI
                 ↓
   10. AI Evidence / Confidence Model
                 ↓
   11. AI Busy / Privacy / Failure UX
                 ↓
   12. Decision-First Trace Compare
                 ↓
   13. Compare → Decision
                 ↓
   14. Exported Context
                 ↓
   15. Command Palette
                 ↓
   16. Modal Flow Review

The order is intentional.

Items 1–2 establish the shared Evidence and context-navigation
infrastructure.

Items 3–5 complete the Statistics / Findings workflow.

Items 6–8 build the SMP investigation path.

Items 9–11 make AI reuse the same interaction model.

Items 12–13 complete Compare and Decision.

Items 14–16 improve reproducibility and expert productivity after the core
investigation workflow is stable.

---

# Deferred to Step 3

Step 3 should handle cross-cutting polish and validation:

- complete Loading-state UX;
- full Empty/Disabled/Error audit;
- Typography and density;
- Numeric presentation standards;
- semantic colors;
- colorblind accessibility;
- Light/Dark validation;
- High-DPI and responsive layout;
- Settings reorganization;
- persistent workspace state;
- First-Run Guidance;
- Contextual Help;
- cross-surface terminology audit;
- keyboard accessibility audit;
- UX regression checklist;
- end-to-end new-user validation.

---

# Step 2 Completion Target

After Step 2, the complete investigation flow should be:

    Statistics / Findings
           ↓
       Investigate
           ↓
        Evidence
           ↓
    Timeline Verification
           ↓
     AI Explanation
           ↓
      Trace Compare
           ↓
        Decision

At every transition:

- Scope remains clear.
- Filters remain visible.
- Selection and Highlight remain semantically distinct.
- Evidence Navigation behaves consistently.
- Analysis context is preserved.

# Success Criterion

Step 2 is complete when BTFViewer no longer behaves like a collection of
independent analysis features.

Instead, Statistics, Migration, AI, and Trace Compare should feel like
different parts of the same evidence-driven investigation workflow.

> Every analytical result should either expose supporting Evidence or make
> the next useful investigation action obvious.