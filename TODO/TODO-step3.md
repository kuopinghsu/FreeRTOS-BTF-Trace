# BTFViewer UX Improvement TODO — Step 3

Step 3 is the final UX refinement and validation phase.

It assumes the following are already stable:

- Step 1: Scope, Filter, Selection/Highlight, Cursor, Task/Core, Statistics entry flow
- Step 2: Evidence Navigation, Statistics drill-down, Migration workflow, AI workflow, Trace Compare

The goal of Step 3 is to make the completed investigation workflow robust, readable, accessible, consistent, and easy to validate.

## Step 3 Goal

Target workflow:

STABILIZE → POLISH → VALIDATE

The final user workflow remains:

SEE → TRIAGE → SCOPE → INVESTIGATE → EVIDENCE → VERIFY → COMPARE → DECIDE

---

# P1 — Application-State UX

## 1. Complete Loading-State UX

**Priority:** High  
**Complexity:** Medium

**Goal:** Make long operations understandable and distinguish normal processing from an application hang.

Recommended stages:

    Reading trace…
    Parsing events…
    Building Timeline…
    Computing Statistics…

### TODO

- [ ] Identify meaningful loading stages.
- [ ] Show stage text for noticeable waits.
- [ ] Add progress indication where progress is reliable.
- [ ] Keep UI responsive where possible.
- [ ] Avoid fake percentage precision.
- [ ] Show Cancel only when cancellation is supported.
- [ ] Ensure cancellation leaves the application in a valid state.
- [ ] Keep the active Trace and current operation visible.

### Acceptance

Users can tell what BTFViewer is doing and whether the operation is still progressing.

---

## 2. Complete Empty-State Coverage

**Priority:** High  
**Complexity:** Low–Medium

**Goal:** Replace meaningless blank surfaces with useful guidance.

Examples:

    Open a BTF trace to begin.

    Place two cursors to measure a range.

    Open at least two traces to compare.

### TODO

- [ ] Audit all major Analysis Tabs.
- [ ] Audit Statistics sections with unavailable data.
- [ ] Audit Migration/SMP views.
- [ ] Audit AI states.
- [ ] Audit Trace Compare.
- [ ] Explain what prerequisite is missing.
- [ ] Provide a direct action when useful.
- [ ] Keep wording concise.
- [ ] Use terminology consistent with disabled-state messages.

### Acceptance

An empty panel explains why it is empty and what the user can do next.

---

## 3. Complete Disabled-State Coverage

**Priority:** High  
**Complexity:** Low–Medium

**Goal:** Make unavailable actions understandable.

### TODO

- [ ] Explain multi-core-only features.
- [ ] Explain cursor-count requirements.
- [ ] Explain multi-trace requirements.
- [ ] Explain AI configuration requirements.
- [ ] Explain unsupported Trace-data requirements.
- [ ] Add concise prerequisite tooltips/help.
- [ ] Keep disabled-state wording consistent with Empty States.
- [ ] Keep disabled-state wording consistent with Command Palette.
- [ ] Avoid silently hiding useful commands where showing the prerequisite is more helpful.

### Acceptance

Users know why an action is unavailable and what is required to enable it.

---

## 4. Normalize Error Handling

**Priority:** High  
**Complexity:** Medium

**Goal:** Replace raw implementation failures with actionable user-facing messages.

Recommended format:

    Could not open trace

    example.btf contains an invalid timestamp near line 482.

### TODO

- [ ] State what operation failed.
- [ ] Identify the affected file or Trace.
- [ ] Explain the reason when known.
- [ ] Suggest a next action.
- [ ] Normalize parser errors.
- [ ] Normalize file I/O errors.
- [ ] Normalize AI/provider errors.
- [ ] Normalize report/export errors.
- [ ] Normalize session import/export errors.
- [ ] Keep raw technical detail expandable/copyable for debugging.
- [ ] Avoid displaying Python traceback text as the primary error UI.

### Acceptance

Error messages are useful to ordinary users while still preserving technical detail for debugging.

---

# P1 — Visual Consistency and Readability

## 5. Typography and Information-Density Review

**Priority:** High  
**Complexity:** Low–Medium

**Goal:** Preserve engineering-tool density without sacrificing readability.

### TODO

- [ ] Define Section Heading size.
- [ ] Define normal Body/Metric size.
- [ ] Define Secondary Metadata size.
- [ ] Avoid persistent 9–10 px explanatory text.
- [ ] Avoid oversized headings.
- [ ] Reduce unnecessary whitespace.
- [ ] Avoid excessive card borders.
- [ ] Prevent button-label truncation.
- [ ] Avoid routine horizontal scrolling in Statistics.
- [ ] Keep dense tables readable at normal DPI and high DPI.

### Acceptance

Dense views remain readable without relying on unusually small fonts.

---

## 6. Standardize Numeric Presentation

**Priority:** High  
**Complexity:** Low

**Goal:** Make engineering values easier to scan and compare.

### TODO

- [ ] Right-align numeric values.
- [ ] Keep units consistent within a column.
- [ ] Use appropriate decimal precision.
- [ ] Align comparable values visually.
- [ ] Avoid unnecessary raw timestamps.
- [ ] Define automatic µs/ms/s conversion rules.
- [ ] Keep p50/p95/p99/Max formatting consistent.
- [ ] Apply the same numeric rules to generated reports where practical.

### Acceptance

Users can compare timing values without mentally normalizing formatting.

---

## 7. Separate Data Colors from Semantic Colors

**Priority:** High  
**Complexity:** Medium

**Goal:** Prevent Task/Core identity colors from conflicting with status meaning.

### Data Colors

Use for:

- Task identity
- Core identity
- Heatmaps
- data-series distinction

### Semantic Colors

Use for:

- Regression / Error
- Warning
- Improvement
- Selection / Focus

### TODO

- [ ] Define semantic color roles.
- [ ] Avoid using warning/error colors as arbitrary Task colors.
- [ ] Keep selection/focus colors distinct from Task identity colors.
- [ ] Pair semantic colors with icons or text.
- [ ] Apply the same meaning across Statistics, AI, Trace Compare, and Timeline.

### Acceptance

A color has a predictable meaning regardless of which analysis surface the user is viewing.

---

# P1 — Accessibility

## 8. Complete Colorblind-Safe Review

**Priority:** High  
**Complexity:** Medium

**Goal:** Ensure important information is not encoded by color alone.

### TODO

- [ ] Validate Timeline Task/Core distinction.
- [ ] Validate selection state.
- [ ] Validate Highlight state.
- [ ] Validate Regression/Improvement.
- [ ] Validate Severity.
- [ ] Validate Task × Core Heatmap.
- [ ] Validate Migration visualizations.
- [ ] Add numeric values where needed.
- [ ] Add legends where needed.
- [ ] Use icon/text reinforcement.
- [ ] Test selected/hover/disabled states.

### Acceptance

Important analytical information remains understandable without relying on color discrimination.

---

## 9. Validate Light and Dark Themes

**Priority:** High  
**Complexity:** Medium

**Goal:** Give both themes equivalent usability.

### TODO

Validate:

- [ ] Timeline background and grid.
- [ ] Task/Core colors.
- [ ] selected segments.
- [ ] cursors.
- [ ] bookmarks.
- [ ] annotations.
- [ ] Statistics tables.
- [ ] Findings cards.
- [ ] disabled controls.
- [ ] Heatmaps.
- [ ] Migration visualizations.
- [ ] AI conversation.
- [ ] Trace Compare.
- [ ] tooltips.
- [ ] Evidence links.
- [ ] semantic Warning/Error/Improvement states.

### Acceptance

Neither theme behaves like a partially supported alternative.

---

## 10. Normalize Keyboard and Pointer Accessibility

**Priority:** High  
**Complexity:** Medium

**Goal:** Avoid requiring pointer-only interaction for important investigation actions.

### TODO

- [ ] Document Wheel/Trackpad scrolling.
- [ ] Document Ctrl+Wheel / Pinch Zoom.
- [ ] Keep drag behavior consistent.
- [ ] Keep left-click cursor behavior consistent.
- [ ] Keep double-click inspect/zoom behavior consistent.
- [ ] Keep right-click Context Menu behavior consistent.
- [ ] Define Shift modifier behavior.
- [ ] Ensure important pointer actions have keyboard alternatives.
- [ ] Validate keyboard focus visibility.
- [ ] Validate keyboard traversal.
- [ ] Avoid shortcut conflicts.
- [ ] Keep shortcuts synchronized with menus and Command Palette.

### Acceptance

Core investigation actions remain usable without relying exclusively on pointer interaction.

---

# P1 — High-DPI and Responsive Desktop

## 11. High-DPI Layout Review

**Priority:** High  
**Complexity:** Medium

### TODO

- [ ] Test high-DPI scaling.
- [ ] Test font scaling.
- [ ] Test cursor markers.
- [ ] Test cursor labels.
- [ ] Test Timeline row height.
- [ ] Test Statistics tables.
- [ ] Test Findings cards.
- [ ] Test AI controls.
- [ ] Test Toolbar buttons.
- [ ] Test icons.
- [ ] Test long Task names.
- [ ] Test long translated labels.

### Acceptance

Scaling does not cause clipped labels, overlapping controls, or unreadable information density.

---

## 12. Define Wide / Medium / Narrow Desktop Layout Rules

**Priority:** High  
**Complexity:** Medium–High

**Goal:** Make responsive behavior intentional rather than accidental.

### Wide

- Full Timeline + Analysis Panel.
- Full Toolbar labels where appropriate.
- Normal Statistics layout.

### Medium

- Narrower Analysis Panel.
- Shorter helper text.
- Compact Toolbar labels where necessary.
- Preserve primary investigation actions.

### Narrow

- Analysis Panel can Hide / Show.
- Secondary Toolbar actions move to overflow.
- Normal font sizes remain.
- Statistics avoid whole-window horizontal scrolling.

### TODO

- [ ] Define width thresholds or equivalent adaptive rules.
- [ ] Define minimum Analysis Panel width.
- [ ] Define Toolbar overflow behavior.
- [ ] Define helper-text reduction.
- [ ] Define which controls remain permanently visible.
- [ ] Avoid font shrinking as the primary fallback.
- [ ] Test narrow-window Statistics.
- [ ] Test narrow-window AI.
- [ ] Test narrow-window Find.
- [ ] Test Timeline label visibility.

### Acceptance

BTFViewer degrades gracefully as desktop width decreases.

---

# P2 — Settings and Workspace Persistence

## 13. Reorganize Settings by User Intent

**Priority:** Medium  
**Complexity:** Medium

Recommended structure:

### Appearance

- Theme
- UI Font
- Timeline Font
- Colorblind-safe Palette

### Display

- Grid
- STI
- Analysis Tab Visibility
- Overlays

### Layout

- Orientation
- Row Size
- Label Dimensions
- Panel Defaults
- Cursor Limits

### AI

1. Enable AI
2. Provider / Preset
3. Model
4. Authentication / Connection
5. Response Language
6. Context Level
7. Privacy / Redaction
8. Advanced Networking / TLS

### TODO

- [ ] Group Settings by user intent.
- [ ] Keep common options near the top.
- [ ] Move advanced networking/TLS out of the normal path.
- [ ] Keep AI enable/provider/model together.
- [ ] Add concise descriptions for non-obvious settings.
- [ ] Avoid exposing implementation details as primary settings.

### Acceptance

Common configuration does not require navigating expert or networking-oriented options.

---

## 14. Remember Useful Workspace State

**Priority:** Medium  
**Complexity:** Medium

**Goal:** Preserve useful preferences without restoring confusing transient state.

### TODO

- [ ] Remember Analysis Panel width.
- [ ] Remember selected theme.
- [ ] Remember appropriate Timeline layout preferences.
- [ ] Remember appropriate Statistics section state.
- [ ] Decide whether to restore the active Analysis Tab.
- [ ] Do not unexpectedly restore stale temporary Filters.
- [ ] Do not restore invalid Cursor state for another Trace.
- [ ] Do not restore a stale Scope that no longer applies.
- [ ] Define Session-persistent state.
- [ ] Define Application-persistent state.
- [ ] Document the distinction.

### Acceptance

BTFViewer reopens predictably without misleading the user about the current investigation.

---

# P2 — Onboarding and Contextual Help

## 15. Add Lightweight First-Run Guidance

**Priority:** Medium  
**Complexity:** Low–Medium

Example:

    New to BTFViewer?

    Start with Statistics → Analysis Findings.

    [Show Me] [Dismiss]

### TODO

- [ ] Show only when useful.
- [ ] Make it dismissible.
- [ ] Remember dismissal.
- [ ] Add `Show Me` navigation.
- [ ] Avoid blocking modal walkthroughs.
- [ ] Keep guidance synchronized with the current UI.
- [ ] Avoid explaining advanced functionality during first use.

### Acceptance

A first-time user discovers the intended investigation entry point without being forced through a tutorial.

---

## 16. Replace Persistent Helper Text with Contextual Help

**Priority:** Medium  
**Complexity:** Low

### TODO

- [ ] Move long Find explanations to tooltip/info.
- [ ] Move advanced Statistics explanations to Help affordances.
- [ ] Move advanced Migration explanations to contextual help.
- [ ] Keep critical prerequisite information visible.
- [ ] Use concise inline hints only where necessary.
- [ ] Avoid copying full documentation into panels.
- [ ] Ensure Help terminology matches documentation.

### Acceptance

Panels remain compact while non-obvious behavior remains discoverable.

---

# P1 — Cross-Surface Consistency Audit

## 17. Audit Canonical Terminology Across All Surfaces

**Priority:** High  
**Complexity:** Medium

**Depends on:** Step 1 and Step 2 complete.

This is an audit, not a new terminology design task.

### Audit surfaces

- [ ] Timeline GUI
- [ ] Toolbar
- [ ] Menus
- [ ] Tooltips
- [ ] Statistics
- [ ] Analysis Findings
- [ ] Marks
- [ ] Find
- [ ] Legend
- [ ] Migration views
- [ ] AI prompts
- [ ] AI responses
- [ ] Trace Compare
- [ ] generated reports
- [ ] CLI
- [ ] README
- [ ] WORKFLOWS documentation
- [ ] screenshots/diagrams

### Verify

- [ ] `Scope`
- [ ] `Filter`
- [ ] `Highlight`
- [ ] `Evidence`
- [ ] `C1–Cn`
- [ ] `Fit Trace`
- [ ] `Fit Cursors`
- [ ] `Baseline`
- [ ] `Candidate`
- [ ] `Regressed`
- [ ] `Improved`
- [ ] Severity terminology
- [ ] Statistics metric names

### Acceptance

A user can move from GUI to AI, reports, CLI, or documentation without relearning terminology.

---

## 18. Audit Investigation Context Preservation

**Priority:** High  
**Complexity:** Medium

**Goal:** Verify that the context-preservation behavior implemented in Step 2 is consistent everywhere.

### TODO

- [ ] Verify Timeline position preservation.
- [ ] Verify Zoom preservation.
- [ ] Verify Cursor preservation.
- [ ] Verify Scope preservation.
- [ ] Verify Filter preservation.
- [ ] Verify Statistics scroll preservation.
- [ ] Verify Analysis Tab behavior.
- [ ] Verify AI conversation preservation.
- [ ] Verify Trace-tab switching behavior.
- [ ] Document intentional exceptions.
- [ ] Verify Evidence Navigation does not accidentally reset state.

### Acceptance

Navigation changes investigation context only when the user's action explicitly requests it.

---

## 19. Audit Export and Report Consistency

**Priority:** Medium–High  
**Complexity:** Medium

### TODO

- [ ] Verify active Trace identity is included.
- [ ] Verify Scope is included.
- [ ] Verify relevant Filters are included.
- [ ] Verify Baseline/Candidate identity.
- [ ] Verify comparison Scope.
- [ ] Verify analysis timestamp where needed.
- [ ] Verify Evidence references.
- [ ] Verify numeric formatting.
- [ ] Verify terminology.
- [ ] Verify Severity/Confidence vocabulary.
- [ ] Verify Light/Dark-independent report readability where applicable.

### Acceptance

Exported output can be understood independently of the live GUI.

---

# P1 — UX Quality and Validation

## 20. Create a UX Regression Checklist

**Priority:** High  
**Complexity:** Low

For every significant UI change verify:

- [ ] Is the main action obvious?
- [ ] Is the active Trace obvious?
- [ ] Is current Scope obvious?
- [ ] Are Scope and Filter semantically distinct?
- [ ] Are active Filters visible?
- [ ] Are Filters easy to clear?
- [ ] Is Highlight distinguishable from Filter?
- [ ] Is Selection distinguishable from Highlight?
- [ ] Is Timeline context preserved where appropriate?
- [ ] Can analytical results navigate to Evidence?
- [ ] Does Evidence Navigation avoid unintended state changes?
- [ ] Are disabled states explained?
- [ ] Is the empty state useful?
- [ ] Is the loading state understandable?
- [ ] Are errors actionable?
- [ ] Does Narrow layout work?
- [ ] Does High-DPI work?
- [ ] Does Light Mode work?
- [ ] Does Dark Mode work?
- [ ] Does Colorblind-safe mode work?
- [ ] Is keyboard access preserved?
- [ ] Is terminology consistent?
- [ ] Is Hidden State minimized?
- [ ] Is there a path back to Timeline Evidence?
- [ ] Is the next useful action obvious?

### Acceptance

UX review becomes part of feature completion rather than a later cleanup phase.

---

## 21. Validate the End-to-End New-User Workflow

**Priority:** Critical  
**Complexity:** Medium

**Depends on:** Step 1 and Step 2 complete.

Test the complete workflow:

    Open Trace
        ↓
    Fit / Orient
        ↓
    Statistics / Findings
        ↓
    Scope
        ↓
    Investigate
        ↓
    Show Evidence
        ↓
    Timeline Verification
        ↓
    AI Explanation / Verification
        ↓
    Trace Compare
        ↓
    Decision

### TODO

- [ ] Test with a user unfamiliar with BTFViewer.
- [ ] Record hesitation points.
- [ ] Record Hidden State confusion.
- [ ] Record terminology mismatches.
- [ ] Record dead-end visualizations.
- [ ] Record unnecessary panel switching.
- [ ] Record cases where Evidence cannot be located.
- [ ] Record cases where Scope is unclear.
- [ ] Record cases where Filter/Highlight is confused.
- [ ] Record places where the next action is unclear.
- [ ] Fix critical workflow breaks before adding more UX features.
- [ ] Repeat after major UI changes.

### Acceptance

A new user can complete the primary investigation without detailed knowledge of BTFViewer's internal feature organization.

---

# Recommended Implementation Order

    1. Loading-State UX
               ↓
    2. Empty-State Coverage
               ↓
    3. Disabled-State Coverage
               ↓
    4. Error Handling
               ↓
    5. Typography / Density
               ↓
    6. Numeric Presentation
               ↓
    7. Data vs Semantic Colors
               ↓
    8. Colorblind-Safe Review
               ↓
    9. Light / Dark Validation
               ↓
   10. Keyboard / Pointer Accessibility
               ↓
   11. High-DPI Review
               ↓
   12. Responsive Desktop Rules
               ↓
   13. Settings Reorganization
               ↓
   14. Workspace Persistence
               ↓
   15. First-Run Guidance
               ↓
   16. Contextual Help
               ↓
   17. Terminology Audit
               ↓
   18. Context-Preservation Audit
               ↓
   19. Export / Report Audit
               ↓
   20. UX Regression Checklist
               ↓
   21. End-to-End New-User Validation

The order is intentional.

Items 1–4 make application state understandable.

Items 5–12 stabilize visual quality, accessibility, and desktop scaling.

Items 13–16 refine configuration and onboarding.

Items 17–19 audit consistency across surfaces after the interaction model is stable.

Items 20–21 turn UX validation into an ongoing development practice.

---

# Step 3 Completion Target

The complete UX roadmap becomes:

    Step 1
    Core Clarity & Investigation Foundation
             ↓
    Step 2
    Evidence-Driven Analysis & Guided Investigation
             ↓
    Step 3
    Polish, Accessibility & Validation

After all three stages, BTFViewer should support:

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

without requiring users to understand the internal structure of BTFViewer.

# Final Success Criterion

Step 3 is complete when the workflow implemented in Steps 1 and 2 remains
clear and predictable across:

- supported window sizes;
- high-DPI displays;
- Light and Dark themes;
- colorblind-safe presentation;
- keyboard and pointer interaction;
- reports and exports;
- application restart;
- first-time usage.

The final design rule is:

> Every BTFViewer analysis should make the current Scope clear, expose the
> Evidence behind the result, preserve investigation context, and make the
> next useful action obvious.