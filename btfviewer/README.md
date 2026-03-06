# BTF Trace Viewer

A PyQt5-based interactive visualiser for FreeRTOS context-switch traces in **Best Trace Format** (`.btf`).

## Screenshot

<img src="../images/btfviewer.png" alt="BTF Viewer screenshot" width=640>

## Requirements

- Python 3.8+
- PyQt5 >= 5.15

```bash
pip install PyQt5
```

## Usage

```bash
python btf_viewer.py [trace.btf]
```

A file can also be opened via **File -> Open** (`Ctrl+O`) or dragged onto the window.

---

## View Modes

| Mode | Description |
|------|-------------|
| **Task View** | One row per task across all cores; core tint applied to segment bars |
| **Core View** | One expandable row per CPU core; bars coloured by running task |

In **Core View**, click a core label to **expand** or **collapse** its per-task sub-rows.

## Orientation

- **Horizontal** (default) - time runs left to right
- **Vertical** - time runs top to bottom

Switch orientation using the toolbar or **View -> Horizontal layout / Vertical layout**.

## Task Labels

Regular task labels show the task name and task ID, for example `MyTask[3]`.
IDLE and TICK tasks show their bare name (`IDLE`, `IDLE0`, `IDLE1`, etc.) without an ID suffix.
IDLE tasks always render in grey; each IDLE task on a different core gets a distinct shade.

---

## Task Highlight

Hovering or clicking a task name in the label column or Legend panel highlights all timeline segments for that task.

| Action | Effect |
|--------|--------|
| Hover over a task label or Legend row | Transiently highlights that task's segments |
| Hover leave | Removes the transient highlight and restores any persistent highlight |
| Click a task label or Legend row | Locks the highlight on that task persistently |
| Click the same locked task again | Cancels the persistent highlight |
| Click empty area in the label column | Cancels the persistent highlight |
| Click empty area in the Legend panel | Cancels the persistent highlight |

When a task is persistently highlighted, its row gets a colour tint, its label turns gold and bold,
and its segment bars show a white border. Hovering another task while a lock is active shows both
highlights at the same time.

---

## Cursors

Up to 4 cursors can be placed on the timeline. Delta times between consecutive cursors are shown on
the timeline and in the status bar.

### Placing and Moving

| Action | Effect |
|--------|--------|
| Left-click on the timeline area | Place a new cursor at that time position |
| Drag a cursor line | Move it to a new time position |
| `C` (keyboard) | Place a cursor at the viewport centre |

### Removing

| Action | Effect |
|--------|--------|
| Right-click on the timeline area | Remove the nearest cursor |
| `Shift+C` | Clear all cursors |
| Drag a status-bar cursor badge out of the status bar | Remove that specific cursor |

### Navigating

| Action | Effect |
|--------|--------|
| Click a `C1` / `C2` / ... badge in the status bar | Scroll the view to that cursor |

---

## Legend Panel

The Legend lists every task with its colour swatch and `Name[id]` label.

- **View -> Show Legend** (`Ctrl+L`) or the toolbar **Legend** button toggles the panel.
- The panel is a dockable window; it can be detached, closed, and re-opened.
- Hover and click Legend rows to highlight tasks using the same rules as the label column.

---

## Zoom and Pan

| Action | Effect |
|--------|--------|
| `Ctrl` + Scroll wheel | Zoom in or out centred on the pointer |
| Two-finger pinch (macOS) | Zoom in or out |
| Scroll wheel / trackpad swipe | Pan horizontally (or vertically in Vertical mode) |
| `Ctrl+0` | Fit entire trace to window |
| `Ctrl+R` | Reset zoom to default |
| Toolbar zoom+ / zoom- buttons | Zoom in or out by 2x |

---

## Export

**File -> Save as Image (PNG)** (`Ctrl+S`) saves the current viewport as a PNG file.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open `.btf` file |
| `Ctrl+S` | Save viewport as PNG |
| `Ctrl++` | Zoom in |
| `Ctrl+-` | Zoom out |
| `Ctrl+0` | Fit to window |
| `Ctrl+R` | Reset zoom |
| `Ctrl+L` | Toggle Legend panel |
| `C` | Place cursor at viewport centre |
| `Shift+C` | Clear all cursors |
| `Ctrl+Q` | Quit |

---

## Other

- Hover over any segment bar or STI marker for a detailed tooltip.
- Toggle STI events and grid lines from the toolbar or View menu.
- Drag and drop a `.btf` file onto the window to open it.

---

## BTF Format

Each line follows the pattern:

```
timestamp, source, src_inst, event_type, target, tgt_inst, event[, note]
```

| event_type | Meaning |
|---|---|
| `T` | Task context-switch (`resume` / `preempt`) |
| `STI` | Software trace item (mutex take/give, trigger, etc.) |
| `C` | Core event (e.g. `set_frequence`) |
