# BTF Trace Viewer

A PyQt5-based interactive visualiser for FreeRTOS context-switch traces in **Best Trace Format** (`.btf`), inspired by [Percepio Tracealyzer](https://percepio.com/tracealyzer/).

## Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│ [label col]  │ 0 µs     100 µs    200 µs    300 µs          │
│──────────────┼──────────────────────────────────────────────│
│ matrix task  │ ████████           ████████                  │
│ Tmr Svc      │          ██                    ███           │
│ IDLE0        │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│──────────────┼──────────────────────────────────────────────│
│ Core_0 STI   │ ▼   ▼▼  ▼                                    │
└─────────────────────────────────────────────────────────────┘
```

## Requirements

- Python 3.8+
- PyQt5 ≥ 5.15

```bash
pip install PyQt5
```

## Usage

```bash
python btfviewer.py [trace.btf]
```

A file can also be opened via **File → Open** or dragged onto the window.

## Features

### View Modes
| Mode | Description |
|------|-------------|
| **Task View** | One row per task across all cores; core tint applied to bars |
| **Core View** | One expandable row per CPU core; bars coloured by running task |

In **Core View**, click a core's label to **expand** (▼) or **collapse** (▶) its per-task sub-rows.

### Orientation
- **Horizontal** (default) — time runs left → right
- **Vertical** — time runs top → bottom

### Zoom & Pan
| Action | Effect |
|--------|--------|
| `Ctrl + Scroll wheel` | Zoom in / out |
| Two-finger pinch (macOS) | Zoom in / out |
| Scroll wheel / trackpad swipe | Pan left / right |
| `Ctrl+0` | Fit entire trace to window |
| `Ctrl+R` | Reset zoom to 1:1 |
| Toolbar 🔍+ / 🔍- | Zoom in / out by 2× |

### Cursors (up to 4)
| Action | Effect |
|--------|--------|
| Left-click on timeline | Place a cursor |
| Drag a cursor line | Move it to a new time position |
| Right-click on timeline | Remove the nearest cursor |
| `Shift + Right-click` | Clear all cursors |
| `C` | Place cursor at viewport centre |
| `Shift+C` | Clear all cursors |
| Click C1/C2… badge in status bar | Scroll view to that cursor |

Delta times (Δ) between consecutive cursors are shown both on the timeline and in the status bar.

### Export
**File → Save as SVG** saves the current scene (at the current zoom level) as a vector SVG file.

### Other
- Hover over any bar or STI marker for a detailed tooltip
- Toggle **STI events** and **grid lines** from the toolbar or View menu
- Colour **legend** panel (View → Show Legend)
- Drag & drop a `.btf` file onto the window to open it

## BTF Format

Lines follow the pattern:

```
timestamp, source, src_inst, event_type, target, tgt_inst, event[, note]
```

| `event_type` | Meaning |
|---|---|
| `T` | Task context-switch (`resume` / `preempt`) |
| `STI` | Software trace item (mutex take/give, etc.) |
| `C` | Core event (e.g. `set_frequence`) |

## File Structure

```
btf_viewer/
├── btf_viewer.py   # Single-file application (parser + widget + window)
└── trace.btf       # Example FreeRTOS trace
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save SVG |
| `Ctrl++` | Zoom in |
| `Ctrl+-` | Zoom out |
| `Ctrl+0` | Fit to window |
| `Ctrl+R` | Reset zoom |
| `C` | Place cursor at centre |
| `Shift+C` | Clear all cursors |
| `Ctrl+Q` | Quit |
