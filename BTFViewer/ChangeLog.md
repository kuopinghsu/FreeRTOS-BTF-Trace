# BTFViewer Change Log

Since v1.0.0 (2026-09-13)

## 2026-09-19
- Accessibility: colorblind-safe palette setting renamed to "Colorblind-safe palette (Okabe-Ito)" with a clearer tooltip describing its task/core-color scope (desktop/web)
- Fixed: take_mutex/give_mutex STI markers relied on red/green alone; they now also use distinct triangle shapes so mutex direction is never color-only (desktop/web)

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
