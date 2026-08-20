# Demo XML Guide

This document explains how to build, run, package, and extend BTFViewer in-app demos.

The same demo XML is used by the Desktop runner
([`../btf_viewer_pkg/demo_inapp.py`](../btf_viewer_pkg/demo_inapp.py))
and the Web runner
([`../web/src/utils/demoRunner.js`](../web/src/utils/demoRunner.js)).

Each complete demo has its own folder with the XML script, a frozen trace, narration text, and optional voice files.

## Contents

1. [Demo layout](#demo-layout)
2. [Run the demo](#run-the-demo)
3. [Demo action reference](#demo-action-reference)
4. [Timeline and view actions](#timeline-and-view-actions)
5. [Live UI targets](#live-ui-targets)
6. [Audio and voice packs](#audio-and-voice-packs)
7. [Shareable XTF packs](#shareable-xtf-packs)
8. [Runner behavior](#runner-behavior)

<a id="demo-layout" name="demo-layout">&#x200B;</a>

## Demo layout

| Path | Purpose |
|------|---------|
| [`demo_8cores/`](demo_8cores/) | 8-core BTFViewer recording demo |

### `demo_8cores/` folder

| Path | Purpose |
|------|---------|
| [`demo_8cores/demo_8cores.xml`](demo_8cores/demo_8cores.xml) | Runner script (steps / actions) |
| [`demo_8cores/demo_8cores.btf.gz`](demo_8cores/demo_8cores.btf.gz) | Frozen trace (stable vs `tracedata/`) |
| [`demo_8cores/text/<lang>/`](demo_8cores/text/en/) | Narration scripts (`.txt`), one folder per language |
| [`demo_8cores/voice/<lang>/`](demo_8cores/voice/en/) | TTS audio + `voice.json`, one folder per language |

<a id="run-the-demo" name="run-the-demo">&#x200B;</a>

## Run the demo

Build the bundled application once, then start the demo with `make demo`. Use `DEMO_LANG` to select another narration language.

```bash
cd BTFViewer
make bundle   # once — demo launches builds/btf_viewer.py
make demo
# Chinese narration if voice/zh-tw/*.mp3 exist (else English fallback):
make demo DEMO_LANG=zh-tw
# Shareable zip pack (Open / drag in the viewer):
make demo-pack                    # → builds/demo_8cores.xtf (en + zh-tw)

# Or run the tools directly:
python3 builds/btf_viewer.py demos/demo_8cores/demo_8cores.xml
BTFVIEWER_DEMO_LANG=zh-tw python3 builds/btf_viewer.py demos/demo_8cores/demo_8cores.xml
python3 builds/btf_viewer.py builds/demo_8cores.xtf
python3 scripts/demo_voice.py status demos/demo_8cores
python3 scripts/demo_pack.py demos/demo_8cores -o builds/demo_8cores.xtf --lang en,zh-tw
```

Settings for the demo session are stored in `builds/btf_viewer.rc` (next to the bundled app).

<a id="demo-action-reference" name="demo-action-reference">&#x200B;</a>

## Demo action reference

The XML runner provides actions for narration, pointer movement, highlighting, cursors, Statistics, timeline navigation, and view control.

See [`demo_inapp.py`](../btf_viewer_pkg/demo_inapp.py) and
[`demoRunner.js`](../web/src/utils/demoRunner.js) for the complete action implementation.

### Viewer demo API

The in-app runner calls `MainWindow._demo_handle` directly. Opt-in HTTP
`BTFVIEWER_DEMO_API=1` still serves `POST http://127.0.0.1:8765/demo` for
headless control (no extra packages).

```xml
<highlight task="CS[27]"/>
<cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>
<stats_section id="health" expand="true" collapse_others="true"/>
<jump_wcet task="CS[27]"/>
<move_view time="3.085" unit="s" task="CS[27]"/>
<show_message text="Centered demo caption" seconds="2"/>
<view_mode mode="core"/>
<zoom_1to1/>
<zoom_view/>
<fit_view/>
<zoom_in/>
<zoom_out/>
<cpu_load on="true"/>
<analysis/>
<tick_dist/>
<tick_dist close="true"/>
<find query="CS[27]"/>
<find clear="true"/>
<panel name="stats"/>
<wait_audio/>
<stats_reset/>
<clear_cursors/>
<clear_bookmarks/>
<clear_annotations/>
<clear_highlight/>
<tab_nav/>
<tab_nav dir="prev"/>
```

<a id="timeline-and-view-actions" name="timeline-and-view-actions">&#x200B;</a>

## Timeline and view actions

These actions control timeline zoom, navigation, and viewport position without relying on screen coordinates.

### Fit and zoom

`<zoom_view/>` is **Zoom Full View** (toolbar Fit / Ctrl+0): the entire
trace, even if C1–Cn exist. `<macro ref="fit"/>` (the Ctrl+0 shortcut) uses
this same action.

`<fit_view/>` is **Zoom fit to C1–Cn** (toolbar Range / Ctrl+R) when two or
more cursors are placed. With fewer than two cursors it falls back to
Zoom Full View.

`<zoom_in/>` / `<zoom_out/>` step the timeline zoom one toolbar increment
(Ctrl+= / Ctrl+-), anchored at the viewport center (or the C1–Cn midpoint
when those cursors are placed). Zooming out stops at **Zoom Full View** —
the Zoom Out control is grayed there, and `<zoom_out/>` is a no-op. After
`<fit_view/>` (C1–Cn) the view is still zoomed in, so `<zoom_out/>` still
steps out until Full View.

### Segment navigation

`<tab_nav/>` controls the timeline's Tab / Shift+Tab task-segment navigation.

- `dir="next"` is the default.
- `dir="prev"` moves backward.
- If nothing is selected, navigation starts from the earliest visible cursor, bookmark, or annotation. If none are visible, it starts from the viewport edge.
- If a task segment is already selected, navigation continues to the next or previous segment.

Use `<clear_highlight/>` first when the demo must start with no selection.

### Move the viewport

`<move_view/>` (aliases `<move_viewport/>`, `<pan_view/>`) pans the current
zoom to a time and/or centers a task row. It does not zoom or highlight.

| Attributes | Result |
|---|---|
| omitted / empty / `0` / before trace start, no `task` | Pin the trace start to the **left** of the plot and scroll the task list to the **top**. |
| omitted / empty `time`, with `task` | Center that task's **first segment** in time, and center the task row. |
| `0` / before trace start, with `task` | Pin the trace start left, and center the task row. |
| a later `time`, no `task` | Center that timestamp; leave the row scroll unchanged. |
| a later `time`, with `task` | Center that timestamp **and** the task row. |

Time uses the same `time` / `ns` / `at` plus optional `unit` as `<cursors/>`.
An unknown task name is treated as missing: leftmost time also scrolls the
task list to the top. In Core View the parent core is expanded so the task
sub-row can be centered.

```xml
<move_view time="3.085" unit="s" task="CS[27]"/>
<move_view time="0"/>
<move_view task="CS[27]"/>
```

### Show a message

`<show_message/>` displays a centered caption over the trace window. The message fades in, stays visible for the requested duration, and then fades out.

It does not block pointer overlay movement. Set the text with `text`, `message`, or the element body. Set the duration with `seconds` or `duration`; the default is **2 seconds**.

```xml
<show_message text="Watch the CS row" seconds="2.5"/>
<show_message seconds="1">Jumping to trace start</show_message>
```

Toolbar buttons, tabs, Analysis, and Find use API events instead of fixed screen positions. This keeps demos stable when the window size changes.

<a id="live-ui-targets" name="live-ui-targets">&#x200B;</a>

## Live UI targets

`<move target="…"/>` can point to a named UI element. The runner prefers live widget geometry over XML window fractions.

| Target | Widget |
|---|---|
| `toolbar_open` | Open |
| `toolbar_1to1` | 1:1 zoom |
| `toolbar_fit` | Fit / Zoom Full View |
| `toolbar_task` | Task view |
| `toolbar_core` | Core view |
| `toolbar_load` | CPU Load |
| `toolbar_heatmap` | Migration Heatmap |
| `toolbar_analysis` | Analysis |
| `stats_tab` / `find_tab` / `ai_tab` | Right-panel tabs |
| `stats_summary` / `stats_panel` | Statistics summary |
| `stats_health` | Health section header |
| `stats_tick_dist` | Tick distribution button |
| `stats_export_csv` / `stats_export_html` | Statistics export |

`toolbar_heatmap` only **points** at the Heatmap button; it does not open the
inspector. The 8-core pack also has XML-only fractions (`timeline`,
`timeline_bar`, `status`, `load_strip`, `toolbar_settings`, `toolbar_find`,
`limit_checkbox`) for canvas/status hover, not live widgets.

Expanding a section scrolls its header near the top of the Statistics panel so
the table stays on screen. `<stats_reset/>` (alias `<stats_done/>`) collapses
sections and scrolls back to the top after narration.

Statistics section ids match the desktop panel (`health`, `cores`, `tasks`,
`exec`, `block`, `priority`, `migrations`, `sync`, `queue`, `affinity`,
`lifecycle`, …).

<a id="audio-and-voice-packs" name="audio-and-voice-packs">&#x200B;</a>

## Audio and voice packs

### Audio narration

```xml
<audio file="${XML_DIR}/voice/01_title.mp3"/>
<play file="clips/step3.mp3" block="true" after="0.5"/>
<audio file="beep.wav" block="false"/>
<wait_audio/>
<stop_audio/>
```

Convert `text/<lang>/*.txt` → `voice/<lang>/*.mp3` with your TTS tool (or
`python3 scripts/demo_voice.py render …`). Write **Free-RTOS** (with a hyphen)
so speech engines pronounce it correctly. The runner also tries common
extensions (`.wav`, `.m4a`, `.aiff`, …).

### Voice packs

Every language uses the same layout. XML paths stay
`voice/01_title.mp3`; the runner looks in `voice/<lang>/` first.

```
text/<lang>/01_title.txt
voice/<lang>/01_title.mp3
voice/<lang>/voice.json
```

Shareable zip (install/export) is always:

```
voice.json          # { "schema": "btf-demo-voice", "id": "zh-tw", "label": "中文" }
text/01_title.txt
voice/01_title.mp3
```

```bash
# English is already in text/en/ and voice/en/
python3 scripts/demo_voice.py status demos/demo_8cores

# Add a language from a zip or a folder of .txt/.mp3 files
python3 scripts/demo_voice.py install demos/demo_8cores zh-tw.zip
python3 scripts/demo_voice.py install demos/demo_8cores ./zh-tw --lang zh-tw --label 中文

# Export one language for sharing
python3 scripts/demo_voice.py export demos/demo_8cores --lang en -o builds/demo_8cores-en.zip

# Render clips from scripts (macOS say / espeak; optional ffmpeg → mp3)
python3 scripts/demo_voice.py render demos/demo_8cores --lang zh-tw

# Rewrite <languages> from folders found on disk
python3 scripts/demo_voice.py sync-xml demos/demo_8cores
```

`install` also accepts a folder that is already `text/<lang>/` + `voice/<lang>/`,
or loose `*.txt` / `*.mp3` with `--lang`. Playback order is `voice/<lang>/<file>`,
then flat `voice/<file>` (legacy), then `voice/<default>/<file>`. Web shows a
**Voice** menu on the demo bar when more than one language is listed or
discovered. Desktop: `--lang zh-tw`, `make demo DEMO_LANG=zh-tw`, or
`BTFVIEWER_DEMO_LANG`. Otherwise the XML ``<languages default>`` is used
(English for `demo_8cores`).

<a id="shareable-xtf-packs" name="shareable-xtf-packs">&#x200B;</a>

## Shareable XTF packs

```bash
make demo-pack                              # en + zh-tw (default)
make demo-pack DEMO_LANGS=en                # English only
make demo-pack DEMO_LANGS=all               # every voice/<lang>/
# or:
python3 scripts/demo_pack.py demos/demo_8cores --list-voices
python3 scripts/demo_pack.py demos/demo_8cores --voice en -o builds/demo_8cores-en.xtf
python3 scripts/demo_pack.py demos/demo_8cores --voice en --voice zh-tw
python3 scripts/demo_pack.py demos/demo_8cores --all-voices -o builds/demo_8cores.xtf
```

The command creates an `.xtf` zip archive with:

- the language-filtered XML;
- the frozen `.btf.gz` trace;
- the selected voice packs.

By default, MP3 narration is converted to 24 kHz mono AAC and the packed XML is updated to use the AAC files. Use `--keep-mp3` to keep the original MP3 files.

Open or drag the `.xtf` file into the **Web** or **Desktop** viewer to play the tour.

Declare languages in `<meta>` (or generate that block with `sync-xml`):

```xml
<languages default="en">
  <language id="en" label="English"/>
  <language id="zh-tw" label="中文"/>
</languages>
```

<a id="runner-behavior" name="runner-behavior">&#x200B;</a>

## Runner behavior

### Audio playback

On Windows, playback uses the standard-library helper `scripts/play_audio_clip.py` through winmm/MCI. Other platforms use available system players such as macOS `afplay`, `ffplay`, `paplay`, or `aplay`. Desktop can also use QtMultimedia when it is available.

### Narration and UI overlap

By default `<audio>` is **non-blocking**: overlay and API actions run while the
clip plays; the runner waits for the clip at the end of each step. Use
`block="true"` or `defaults audio_block="true"` to wait per clip.

### Window-relative coordinates

`<point x="0.42" y="0.42"/>` is a fraction of the **viewer window**
(not the full screen). Live toolbar / panel targets (see the table above)
win over XML fractions. `<move>` / `<sweep>` / `<click>` drive a Qt overlay
pointer (same as Web), not the OS cursor.
