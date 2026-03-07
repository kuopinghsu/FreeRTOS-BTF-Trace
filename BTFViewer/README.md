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

## Generating Synthetic Traces — `gen_trace.py`

`gen_trace.py` generates a synthetic FreeRTOS-style BTF trace file for testing or demo purposes.
Task names are drawn from a realistic embedded-system pool (`CAN_Rx`, `Motor_L`, `PID_Speed`, …).
The scheduler simulation includes task priorities, IDLE time, TICK ISRs, and optional STI events.

### Quick start

```bash
# defaults: 8 cores, 100 tasks, 1 M events  →  freertos_8c_100t_1m_events.btf
python3 gen_trace.py

# 4 cores, 50 tasks, 500 K events
python3 gen_trace.py -c 4 -t 50 -e 500000 -o my_trace.btf

# 16 cores, 200 tasks, 2 M events, 500 Hz tick, reproducible seed
python3 gen_trace.py -c 16 -t 200 -e 2000000 --tick-hz 500 --seed 7

# Disable STI events; pin every task to one core
python3 gen_trace.py --no-sti --no-migration
```

### Options

| Option | Default | Description |
|---|---|---|
| `-c` / `--cores` | `8` | Number of CPU cores |
| `-t` / `--tasks` | `100` | Number of worker tasks |
| `-e` / `--events` | `1 000 000` | Target non-comment event lines |
| `-o` / `--output` | auto | Output `.btf` file path |
| `--tick-hz` | `1000` | RTOS tick frequency in Hz (1000 → 1 ms per tick) |
| `--freq-hz` | `200 000 000` | CPU clock frequency in Hz (written to BTF header) |
| `--sti-interval-us` | `30 000` | Approximate µs between STI tag events |
| `--idle-prob` | `0.20` | Probability [0–1] that a core picks its IDLE task |
| `--max-burst-ticks` | `5` | Maximum ticks a task runs before being preempted |
| `--seed` | `42` | Random seed for reproducibility |
| `--no-sti` | off | Suppress all STI software-trace events |
| `--no-migration` | off | Pin each task to one core (disable migration) |

When `--output` is omitted the file is named automatically, e.g. `freertos_8c_100t_1m_events.btf`.

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
