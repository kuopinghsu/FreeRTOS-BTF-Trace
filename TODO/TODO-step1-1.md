# BTFViewer UX Improvement TODO — Test 1.1

This TODO isolates the Statistics category, section-header layout, default
ordering, and pinned-open behavior from `TODO-step1.md`.

The goal is to make Statistics easier to scan, provide useful system-level
context first, preserve category meaning after user reordering, and keep
important sections visible during bulk collapse operations.

> Desktop and Web share the same UX contract. Rendering implementation may
> differ between platforms.

---

# Goal

Introduce persistent Statistics categories:

    OVERVIEW
    TRIAGE
    TIMING
    SCHED
    SYNC
    DETAIL

Use the Statistics section name as the primary label and place classification
and state metadata on the right:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Task Health                   [OVERVIEW]

    ▶ Analysis Findings             [TRIAGE]
    ▶ Timeline Anomalies            [TRIAGE]
    ▶ Worst Events                  [TRIAGE]
    ▶ Recurring Patterns            [TRIAGE]

    ▶ Response Time                 [TIMING]
    ▶ Core Migrations               [SCHED]
    ▶ Mutex Blocking                [SYNC]
    ▶ Detailed Tables               [DETAIL]

The Statistics investigation flow becomes:

    OVERVIEW
       │
       │ Is the system generally healthy?
       ▼
    TRIAGE
       │
       │ What deserves attention?
       ▼
    TIMING
       │
       │ What timing behavior explains it?
       ├───────────────┐
       ▼               ▼
    SCHED             SYNC
       │               │
       └───────┬───────┘
               ▼
            DETAIL

---

# 1. Statistics Categories

**Priority:** Critical  
**Complexity:** Low–Medium  
**Applies to:** Desktop and Web

Every Statistics section belongs to exactly one primary category.

| Badge | Category | Purpose |
| --- | --- | --- |
| `OVERVIEW` | Overview | Understand overall Trace and system health |
| `TRIAGE` | Triage | Identify behavior that deserves attention |
| `TIMING` | Timing | Investigate timing and latency behavior |
| `SCHED` | Scheduling | Investigate CPU, scheduling, and SMP behavior |
| `SYNC` | Synchronization | Investigate blocking and synchronization behavior |
| `DETAIL` | Detail | Inspect supporting or lower-level measurements |

## Rules

- Category is a property of the Statistics section.
- Category is not derived from the section's current position.
- Reordering a section does not change its category.
- Each section has exactly one primary category.
- Desktop and Web use the same category mapping.
- Category remains independent from Severity and Pin state.

## TODO

- [ ] Add a canonical Statistics category model.
- [ ] Add `OVERVIEW`, `TRIAGE`, `TIMING`, `SCHED`, `SYNC`, and `DETAIL`.
- [ ] Assign every Statistics section to exactly one category.
- [ ] Keep category metadata in the shared section catalogue where practical.
- [ ] Use the same category mapping in Desktop and Web.
- [ ] Do not infer category from display order.

## Acceptance

Moving a section does not change its category or badge.

---

# 2. Section Classification

**Priority:** Critical  
**Complexity:** Low  
**Applies to:** Desktop and Web

## OVERVIEW

    Core Utilization
    Tick Health
    Task Health

Purpose:

> Is the system generally healthy?

Keep Overview intentionally small. It provides system-level orientation
rather than detailed investigation.

## TRIAGE

    Analysis Findings
    Timeline Anomalies
    Worst Events
    Recurring Patterns

Purpose:

> What deserves investigation?

Do not place detailed analysis in TRIAGE only because it may contain an
abnormal value.

## TIMING

    Response Time
    Execution Time
    Dispatch Latency
    Blocking / Off-CPU
    Critical Path
    Period / Jitter
    Unified Jitter

Purpose:

> What timing behavior explains the issue?

## SCHED

    Task × Core
    Core Utilization Over Time
    Core Migrations
    Core Affinity
    Preemption Matrix
    Priority Inheritance

Purpose:

> Is scheduling, CPU distribution, or core placement involved?

`Core Utilization` and `Core Utilization Over Time` intentionally belong to
different investigation levels:

    [OVERVIEW] Core Utilization
        → Overall CPU/core loading

    [SCHED] Core Utilization Over Time
        → How CPU/core loading changes during the Trace

## SYNC

    Mutex Blocking
    Waiter × Owner
    Mutex / Semaphore
    Queue

Purpose:

> Is blocking, contention, or synchronization involved?

## DETAIL

    Interval
    Tag
    Detailed Tables

Purpose:

> Show me supporting or lower-level measurements.

## TODO

- [ ] Apply the category mapping above.
- [ ] Confirm all existing Statistics sections are classified.
- [ ] Require new Statistics sections to receive an explicit category.
- [ ] Keep classification consistent between Desktop and Web.

---

# 3. Default Statistics Order

**Priority:** Critical  
**Complexity:** Low–Medium  
**Applies to:** Desktop and Web

Default category order:

    OVERVIEW
        ↓
    TRIAGE
        ↓
    TIMING
        ↓
    SCHED
        ↓
    SYNC
        ↓
    DETAIL

Recommended default section order:

    OVERVIEW
    ├─ Core Utilization
    ├─ Tick Health
    └─ Task Health

    TRIAGE
    ├─ Analysis Findings
    ├─ Timeline Anomalies
    ├─ Worst Events
    └─ Recurring Patterns

    TIMING
    ├─ Response Time
    ├─ Execution Time
    ├─ Dispatch Latency
    ├─ Blocking / Off-CPU
    ├─ Critical Path
    ├─ Period / Jitter
    └─ Unified Jitter

    SCHED
    ├─ Task × Core
    ├─ Core Utilization Over Time
    ├─ Core Migrations
    ├─ Core Affinity
    ├─ Preemption Matrix
    └─ Priority Inheritance

    SYNC
    ├─ Mutex Blocking
    ├─ Waiter × Owner
    ├─ Mutex / Semaphore
    └─ Queue

    DETAIL
    ├─ Interval
    ├─ Tag
    └─ Detailed Tables

## TODO

- [ ] Update the shared default section-order catalogue.
- [ ] Use the same default category order in Desktop and Web.
- [ ] Preserve user-customized ordering.
- [ ] Do not automatically regroup sections after user reordering.
- [ ] Keep category badges visible after custom reordering.
- [ ] Give new sections an explicit default position.

---

# 4. Statistics Section Header Layout

**Priority:** Critical  
**Complexity:** Low–Medium  
**Applies to:** Desktop and Web

The Statistics section name is the primary information.

Keep it left-aligned and place category and Pin state on the right.

Recommended layout:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Task Health                   [OVERVIEW]

    ▶ Analysis Findings             [TRIAGE]
    ▶ Timeline Anomalies            [TRIAGE]
    ▶ Worst Events                  [TRIAGE]
    ▶ Recurring Patterns            [TRIAGE]

    ▶ Response Time                 [TIMING]
    ▶ Execution Time                [TIMING]

    ▶ Task × Core                   [SCHED]
    ▶ Core Migrations               [SCHED]

    ▶ Mutex Blocking                [SYNC]
    ▶ Waiter × Owner                [SYNC]

    ▶ Interval                      [DETAIL]
    ▶ Detailed Tables               [DETAIL]

Conceptually:

    ┌──────────────────────────────────────────────────────┐
    │ ▼ Section Name                 [CATEGORY] [pin]      │
    │ ↑       ↑                           ↑        ↑       │
    │ state   primary label          category  Pin state   │
    └──────────────────────────────────────────────────────┘

## Layout Rules

- Expand/collapse control stays at the far left.
- Section name stays left-aligned.
- Category badge is right-aligned.
- Pin indicator appears after the category badge.
- Reserve a consistent right-side metadata area.
- Section name receives the flexible width.
- Long names elide before overlapping metadata.
- Expanding/collapsing does not shift metadata unexpectedly.
- Reordering does not change header alignment.
- Badge and Pin remain visually secondary to the section name.

## TODO

- [ ] Move category badges to the right side of section headers.
- [ ] Keep section names vertically aligned for fast scanning.
- [ ] Right-align the category/state metadata area.
- [ ] Keep expand/collapse indicators at the far left.
- [ ] Prevent long names from overlapping metadata.
- [ ] Validate narrow Analysis Panel widths.
- [ ] Validate high-DPI scaling.
- [ ] Validate Light and Dark themes.
- [ ] Preserve alignment after user reordering.

---

# 5. Category Badge Design

**Priority:** High  
**Complexity:** Low  
**Applies to:** Desktop and Web

Category badges are secondary classification metadata.

Recommended visual hierarchy:

    Section Name        → primary emphasis
    Category Badge      → secondary metadata
    Pin                 → interactive state
    Metric              → normal emphasis
    Warning/Error       → semantic emphasis

## Rules

- Badge text carries the category meaning.
- Keep badge typography and size consistent.
- Color may reinforce category but must not be required.
- Do not use Warning/Error colors for categories.
- Badge appearance must work in Light and Dark themes.
- Badge appearance must remain understandable without color.
- Desktop and Web should have visually comparable badges.

## TODO

- [ ] Define one compact badge style.
- [ ] Apply it consistently to all six categories.
- [ ] Keep category styling separate from Severity styling.
- [ ] Validate category recognition without color.
- [ ] Validate long section names beside badges.
- [ ] Verify Light and Dark theme contrast.

---

# 6. Pinned-Open Indicator

**Priority:** High  
**Complexity:** Low–Medium  
**Applies to:** Desktop and Web

The existing lock behavior protects an expanded Statistics section from
`Collapse All`.

Replace the lock icon with a theme-aware monochrome **Pin** icon.

The Pin means:

> Keep this section expanded when a bulk collapse operation is used.

It does not mean:

- disabled;
- read-only;
- category locked;
- cannot be reordered;
- cannot be manually collapsed.

---

## Pin States

### Normal — Unpinned

Do not permanently show the Pin:

    ▶ Response Time                         [TIMING]

### Hover / Focus — Unpinned

Show an outline Pin action:

    ▼ Response Time                         [TIMING] [pin-outline]

Tooltip:

    Pin open

### Pinned

Show a filled Pin persistently:

    ▼ Core Utilization                      [OVERVIEW] [pin-filled]

Tooltip:

    Pinned — stays open with Collapse All

Pinned state must remain identifiable without relying on color.

---

## Collapse All Behavior

Before:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▼ Tick Health                   [OVERVIEW]
    ▼ Response Time                 [TIMING]
    ▼ Core Migrations               [SCHED]

After `Collapse All`:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Response Time                 [TIMING]
    ▶ Core Migrations               [SCHED]

Only unpinned sections are collapsed.

---

## Manual Collapse

Pinning protects against bulk operations, not explicit user actions.

Given:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]

If the user manually collapses it:

    ▶ Core Utilization              [OVERVIEW]

the Pin is cleared.

Avoid a state such as:

    ▶ Core Utilization              [OVERVIEW] [pin-filled]

because a collapsed section cannot meaningfully be "pinned open."

---

## Shared Interaction

Desktop and Web expose the same semantics:

    outline Pin
        → available Pin action

    filled Pin
        → section is pinned open

    click/tap Pin
        → toggle Pin state

    manual collapse of pinned section
        → collapse + clear Pin

    Collapse All
        → collapse only unpinned sections

---

# 7. Desktop Pin Implementation

**Priority:** High  
**Complexity:** Low  
**Applies to:** Desktop

For the PySide6 application:

- [ ] Use a monochrome SVG/vector Pin icon.
- [ ] Use outline and filled Pin states.
- [ ] Derive icon color from the active Qt palette.
- [ ] Do not hard-code black or white.
- [ ] Do not use Unicode emoji.
- [ ] Keep the icon crisp under high-DPI scaling.
- [ ] Support Light and Dark themes.
- [ ] Provide Tooltip text.
- [ ] Provide an accessible name such as `Pin open` / `Unpin`.

Recommended:

    Unpinned + normal
        → no Pin

    Unpinned + hover
        → outline Pin

    Pinned
        → filled Pin

---

# 8. Web Pin Implementation

**Priority:** High  
**Complexity:** Low  
**Applies to:** Web

For the Web application:

- [ ] Use a monochrome SVG Pin icon.
- [ ] Prefer the same visual icon family as Desktop where practical.
- [ ] Use `currentColor` for SVG stroke/fill.
- [ ] Do not hard-code Light/Dark icon colors.
- [ ] Do not use emoji.
- [ ] Support Light and Dark themes.
- [ ] Provide an accessible `aria-label`.
- [ ] Provide keyboard access.
- [ ] Provide visible keyboard focus.
- [ ] Use Tooltip text consistent with Desktop.
- [ ] Do not make Hover the only way to access Pin.

Recommended:

    Pointer hover
        → outline Pin

    Keyboard focus
        → outline Pin

    Pinned
        → filled Pin always visible

---

# 9. Touch and Non-Hover Input

**Priority:** High  
**Complexity:** Low  
**Applies to:** Web and touch-capable Desktop environments

Do not assume Hover is always available.

## Rules

- Pinned state is always visible.
- Pin action must remain discoverable without Hover.
- On touch, expose Pin through the section action/menu if necessary.
- Do not change Pin semantics between pointer and touch interaction.

## TODO

- [ ] Verify touch operation.
- [ ] Verify keyboard-only operation.
- [ ] Provide a non-Hover path to Pin/Unpin.
- [ ] Keep the filled Pin visible when pinned.

---

# 10. Theme and Icon Rules

**Priority:** High  
**Complexity:** Low  
**Applies to:** Desktop and Web

Use one semantic icon design across themes.

Preferred model:

    SVG/vector icon
           ↓
    current theme foreground
           ↓
      Light / Dark

Do not maintain separate assets such as:

    pin-light.svg
    pin-dark.svg

unless technically required.

## Rules

- Pin is monochrome.
- Pin color follows the active foreground/icon palette.
- Pin does not inherit Category color.
- Pin does not inherit Severity color.
- Filled/outline shape communicates state.
- Color is supplementary only.

## TODO

- [ ] Verify Pin at 100% scaling.
- [ ] Verify Pin at 125% scaling.
- [ ] Verify Pin at 150% scaling.
- [ ] Verify Pin at 200% scaling.
- [ ] Verify Light theme contrast.
- [ ] Verify Dark theme contrast.
- [ ] Verify pinned state without color.
- [ ] Target approximately 14–16 px visual icon size where appropriate.

---

# 11. Category, Severity, and Pin Are Independent

**Priority:** Critical  
**Complexity:** Low  
**Applies to:** Desktop and Web

These are three independent dimensions.

Example:

    ▼ Response Time        ⚠ Warning        [TIMING] [pin-filled]

Meaning:

    Section     → Response Time
    Severity    → Warning
    Category    → TIMING
    Pin         → protected from Collapse All

Category answers:

> What kind of analysis is this?

Severity answers:

> Does this analysis indicate a problem?

Pin answers:

> Should Collapse All keep this section open?

## TODO

- [ ] Keep Category, Severity, and Pin as separate state.
- [ ] Keep their visual presentation separate.
- [ ] Severity changes must not change Category.
- [ ] Severity changes must not change Pin.
- [ ] Pin changes must not change Category or Severity.
- [ ] Do not use Category badge as an alert indicator.

---

# 12. Default Expansion and Pin State

**Priority:** Critical  
**Complexity:** Medium  
**Applies to:** Desktop and Web

## SMP-Active Trace

When meaningful execution activity is observed on more than one Core:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Task Health                   [OVERVIEW]

    ▶ Analysis Findings             [TRIAGE]
    ▶ Timeline Anomalies            [TRIAGE]
    ▶ Worst Events                  [TRIAGE]
    ▶ Recurring Patterns            [TRIAGE]

    ▶ Response Time                 [TIMING]
    ▶ ...
    ▶ Core Migrations               [SCHED]
    ▶ ...
    ▶ Mutex Blocking                [SYNC]
    ▶ ...
    ▶ Detailed Tables               [DETAIL]

`Core Utilization` is:

1. expanded by default; and
2. pinned by default.

All other sections are collapsed and unpinned.

## Non-SMP-Active Trace

When meaningful execution activity is observed on only one Core:

    ▶ Core Utilization              [OVERVIEW]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Task Health                   [OVERVIEW]
    ▶ Analysis Findings             [TRIAGE]
    ...

All sections are collapsed and unpinned.

## Important Rule

Do not implement:

> Expand and Pin the first Statistics section.

Implement:

> Expand and Pin `Core Utilization` when the loaded Trace is SMP-active.

The behavior follows section identity and Trace capability, not display
position.

---

# 13. SMP-Active Detection

**Priority:** High  
**Complexity:** Medium  
**Applies to:** Desktop and Web

Do not use only platform-declared Core count.

Recommended rule:

    SMP active =
        meaningful execution activity is observed on more than one Core

Examples:

    8 Cores declared
    execution observed only on Core_0

        → not SMP-active for initial presentation
        → all sections collapsed and unpinned

    execution observed on Core_0, Core_1, Core_2, Core_3

        → SMP-active
        → Core Utilization expanded and pinned

This rule affects only initial Statistics presentation.

It must not change:

- Trace topology;
- parsed Core count;
- Statistics calculations;
- SMP feature availability unless intentionally defined by the same rule.

## TODO

- [ ] Define one SMP-active presentation rule.
- [ ] Base it on observed execution activity.
- [ ] Use equivalent behavior in Desktop and Web.
- [ ] Keep it separate from Trace topology metadata.
- [ ] Test multi-core metadata with execution on one Core.
- [ ] Test execution on multiple Cores.

---

# 14. Preserve User State

**Priority:** High  
**Complexity:** Low–Medium  
**Applies to:** Desktop and Web

Default expansion and Pin rules apply to the initial presentation.

After user interaction, normal investigation actions must not reset section
state.

Preserve expansion and Pin state when changing:

- Scope;
- Filters;
- Selection;
- Highlight;
- Timeline Zoom;
- Timeline position;
- Analysis Tab.

## TODO

- [ ] Preserve manual expansion state.
- [ ] Preserve Pin state.
- [ ] Do not reapply defaults after Scope changes.
- [ ] Do not reapply defaults after Filter changes.
- [ ] Do not reapply defaults after Selection or Highlight changes.
- [ ] Do not reapply defaults after Zoom changes.
- [ ] Preserve state when leaving and returning to Statistics.
- [ ] Define session import/export behavior for Pin state.
- [ ] Apply initial defaults for a newly opened Trace unless session
      restoration overrides them.

---

# 15. Custom Ordering

**Priority:** High  
**Complexity:** Medium  
**Applies to:** Desktop and Web

Ordering, Category, Pin, and expansion are separate concepts.

A custom order such as:

    ▶ Analysis Findings             [TRIAGE]
    ▶ Core Migrations               [SCHED]
    ▶ Execution Time                [TIMING]
    ▶ Mutex Blocking                [SYNC]
    ▼ Core Utilization              [OVERVIEW] [pin-filled]

is valid.

## TODO

- [ ] Preserve Category after reordering.
- [ ] Preserve Pin state after reordering.
- [ ] Preserve expansion state after reordering.
- [ ] Preserve section identity after reordering.
- [ ] Do not silently regroup custom sections.
- [ ] `Reset to Default` restores the recommended order.
- [ ] Keep right-side metadata aligned after reordering.

---

# 16. Shared UX Acceptance Tests

Run these tests in both Desktop and Web.

## Test A — Header Layout

Expected:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Tick Health                   [OVERVIEW]
    ▶ Analysis Findings             [TRIAGE]
    ▶ Response Time                 [TIMING]
    ▶ Core Migrations               [SCHED]
    ▶ Mutex Blocking                [SYNC]
    ▶ Detailed Tables               [DETAIL]

Verify:

- [ ] Section names align on the left.
- [ ] Category metadata aligns on the right.
- [ ] Expand/collapse indicators align.
- [ ] Pin indicators align.
- [ ] Long names do not overlap metadata.
- [ ] Expansion does not unexpectedly shift metadata.

## Test B — SMP-Active Trace

Open a Trace with execution activity on multiple Cores.

Verify:

- [ ] `Core Utilization` is expanded.
- [ ] `Core Utilization` is pinned.
- [ ] Every other section is collapsed.
- [ ] Every other section is unpinned.
- [ ] Every section shows the correct category.
- [ ] Overview appears before Triage.

## Test C — Single-Core Execution

Open a Trace with execution activity on one Core.

Verify:

- [ ] All sections are collapsed.
- [ ] No section is pinned.
- [ ] Category badges remain visible.
- [ ] No false SMP emphasis is introduced.

## Test D — Collapse All

Given:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▼ Response Time                 [TIMING]
    ▼ Core Migrations               [SCHED]

Run:

    Collapse All

Expected:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▶ Response Time                 [TIMING]
    ▶ Core Migrations               [SCHED]

## Test E — Manual Collapse

Given:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]

Manually collapse it.

Expected:

    ▶ Core Utilization              [OVERVIEW]

Verify:

- [ ] Section collapses.
- [ ] Pin is cleared.

## Test F — Custom Pin

Expand and Pin `Response Time`:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▼ Response Time                 [TIMING]   [pin-filled]
    ▼ Core Migrations               [SCHED]

Run `Collapse All`.

Expected:

    ▼ Core Utilization              [OVERVIEW] [pin-filled]
    ▼ Response Time                 [TIMING]   [pin-filled]
    ▶ Core Migrations               [SCHED]

## Test G — Category vs. Severity vs. Pin

Expected:

    ▼ Response Time        ⚠ Warning        [TIMING] [pin-filled]

Verify:

- [ ] Warning is visually distinct from Category.
- [ ] Pin is visually distinct from Category.
- [ ] Changing Severity does not change Category or Pin.
- [ ] Changing Pin does not change Severity or Category.

## Test H — Light/Dark Theme

Verify in both themes:

- [ ] Outline Pin is visible.
- [ ] Filled Pin is visible.
- [ ] Pin does not resemble disabled state.
- [ ] Category remains readable.
- [ ] Warning/Error remains visually distinct.

## Test I — Accessibility

Desktop:

- [ ] Pin has Tooltip/accessibility text.
- [ ] Pin can be operated without relying on color.

Web:

- [ ] Pin has accessible name.
- [ ] Pin is keyboard accessible.
- [ ] Keyboard focus is visible.
- [ ] Pin is accessible without Hover.
- [ ] Touch users have a Pin/Unpin path.

---

# Completion Criterion

`TODO-test1-1.md` is complete when Desktop and Web share the same Statistics
classification, header, expansion, and Pin semantics.

The user should understand:

    OVERVIEW → overall system state
    TRIAGE   → what deserves attention
    TIMING   → timing/latency analysis
    SCHED    → scheduling/core analysis
    SYNC     → synchronization/blocking analysis
    DETAIL   → supporting detail

The header model is:

    Section Name                      Category       State
         ↓                               ↓             ↓
    ▼ Core Utilization              [OVERVIEW]   [pin-filled]

The default initial presentation is:

    SMP-active
        → Core Utilization expanded
        → Core Utilization pinned
        → everything else collapsed and unpinned

    not SMP-active
        → everything collapsed
        → nothing pinned

Desktop and Web may use different rendering implementations:

    Desktop / PySide6
        → Qt-compatible SVG/vector
        → Qt palette

    Web
        → SVG/component icon
        → currentColor / CSS theme

but must expose the same UX semantics:

    outline Pin  = available Pin action
    filled Pin   = currently pinned
    Pin          = protected from Collapse All

The governing rule is:

> Share the UX contract, not necessarily the rendering implementation.

Section name describes what is being measured. Category describes what kind
of analysis it belongs to. Severity describes what it found. Pin determines
whether bulk collapse keeps it open. Expansion describes what the user is
currently inspecting. Ordering describes where it is shown.

These concepts must remain independent.
