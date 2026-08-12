# Demo XML descriptions

Generic GUI demos for [`../demo_runner.py`](../demo_runner.py).

Each full demo lives in its own folder (XML + frozen trace + narration).

| Path | Purpose |
|------|---------|
| [`demo_8cores/`](demo_8cores/) | 8-core BTFViewer recording demo |
| [`minimal.example.xml`](minimal.example.xml) | Tiny template to copy |

### `demo_8cores/` layout

| Path | Purpose |
|------|---------|
| [`demo_8cores/demo_8cores.xml`](demo_8cores/demo_8cores.xml) | Runner script (steps / actions) |
| [`demo_8cores/demo_8cores.btf.gz`](demo_8cores/demo_8cores.btf.gz) | Frozen trace (stable vs `tracedata/`) |
| [`demo_8cores/text/`](demo_8cores/text/) | Narration source (`.txt`) |
| [`demo_8cores/voice/`](demo_8cores/voice/) | Pre-rendered TTS audio (generated; gitignored) |

```bash
cd BTFViewer
make bundle   # once — demo launches builds/btf_viewer.py
make demo
# or:
python3 scripts/demo_runner.py scripts/demos/demo_8cores/demo_8cores.xml --launch --interactive
```

Settings for the demo session are stored in `builds/btf_viewer.rc` (next to the bundled app).

See the runner module docstring for the action reference
(`voice`, `audio` / `play`, `hotkey`, `click`, `macro`, `highlight`,
`cursors`, `stats_section`, …).

**Viewer demo API**

`--launch` sets `BTFVIEWER_DEMO_API=1` so the runner can drive highlight /
cursors / zoom / statistics sections over `http://127.0.0.1:8765/demo`
(override with `--demo-api-port`; disable with `--no-demo-api`).

```xml
<highlight task="CS[28]"/>
<cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>
<stats_section id="health" expand="true" collapse_others="true"/>
<jump_wcet task="CS[28]"/>
<view_mode mode="core"/>
<cpu_load on="true"/>
<analysis/>
<find query="CS[28]"/>
<find clear="true"/>
<panel name="stats"/>
<wait_audio/>
<stats_reset/>
<clear_cursors/>
<clear_highlight/>
```

Toolbar buttons, tabs, Analysis, and Find are driven by these API events — not
mouse clicks at window fractions (those miss when the window is not fullscreen).

Expanding a section scrolls its header near the top of the Statistics panel so
the table stays on screen. `<stats_reset/>` (alias `<stats_done/>`) collapses
sections and scrolls back to the top after narration.

Statistics section ids match the desktop panel (`health`, `cores`, `tasks`,
`exec`, `block`, `priority`, `migrations`, `sync`, `queue`, `affinity`,
`lifecycle`, …).

**Audio narration**

```xml
<audio file="${XML_DIR}/voice/01_title.mp3"/>
<play file="clips/step3.mp3" block="true" after="0.5"/>
<audio file="beep.wav" block="false"/>
<wait_audio/>
<stop_audio/>
```

Convert `text/*.txt` → `voice/*.mp3` with your TTS tool. Write **Free-RTOS**
(with a hyphen) so speech engines pronounce it correctly. The runner also tries
sibling `voice/` / `text/` folders and common extensions (`.wav`, `.m4a`, …).

Default players: macOS `afplay`, else `ffplay` / `paplay` / `aplay`.  
Override: `--audio-cmd 'ffplay -nodisp -autoexit'`. Skip clips: `--no-audio`.

**Narration + UI overlap**

By default `<audio>` is **non-blocking**: mouse/hotkey actions run while the
clip plays; the runner waits for the clip at the end of each step. Use
`block="true"`, `defaults audio_block="true"`, or `--audio-block` to wait
per clip.

**Window-relative coordinates**

`<point x="0.42" y="0.42"/>` is a fraction of the **detected BTFViewer window**
(not the full screen). The runner refreshes bounds on `<focus/>` and before
clicks (macOS: Accessibility / System Events; Linux: `xdotool`; or
`--win L,T,W,H` / `--window-title`). Calibrate fractions with:

```bash
python3 scripts/demo_runner.py --calibrate
```
