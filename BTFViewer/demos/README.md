# Demo XML descriptions

Generic GUI demos for [`../scripts/demo_runner.py`](../scripts/demo_runner.py).

Each full demo lives in its own folder (XML + frozen trace + narration).

| Path | Purpose |
|------|---------|
| [`demo_8cores/`](demo_8cores/) | 8-core BTFViewer recording demo |

### `demo_8cores/` layout

| Path | Purpose |
|------|---------|
| [`demo_8cores/demo_8cores.xml`](demo_8cores/demo_8cores.xml) | Runner script (steps / actions) |
| [`demo_8cores/demo_8cores.btf.gz`](demo_8cores/demo_8cores.btf.gz) | Frozen trace (stable vs `tracedata/`) |
| [`demo_8cores/text/<lang>/`](demo_8cores/text/en/) | Narration scripts (`.txt`), one folder per language |
| [`demo_8cores/voice/<lang>/`](demo_8cores/voice/en/) | TTS audio + `voice.json`, one folder per language |

```bash
cd BTFViewer
make bundle   # once — demo launches builds/btf_viewer.py
make demo
# Chinese narration if voice/zh-tw/*.mp3 exist (else English fallback):
make demo DEMO_LANG=zh-tw
# Shareable zip pack (Open / drag in the viewer):
make demo-pack                    # → builds/demo_8cores.xtf (en + zh-tw)
# or:
python3 scripts/demo_runner.py demos/demo_8cores/demo_8cores.xml --launch --interactive
python3 scripts/demo_runner.py demos/demo_8cores/demo_8cores.xml --launch --lang zh-tw
python3 scripts/demo_runner.py builds/demo_8cores.xtf --launch --lang zh-tw
python3 scripts/demo_voice.py status demos/demo_8cores
python3 scripts/demo_pack.py demos/demo_8cores -o builds/demo_8cores.xtf --lang en,zh-tw
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
<highlight task="CS[27]"/>
<cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>
<stats_section id="health" expand="true" collapse_others="true"/>
<jump_wcet task="CS[27]"/>
<view_mode mode="core"/>
<zoom_1to1/>
<fit_view/>
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

Convert `text/<lang>/*.txt` → `voice/<lang>/*.mp3` with your TTS tool (or
`python3 scripts/demo_voice.py render …`). Write **Free-RTOS** (with a hyphen)
so speech engines pronounce it correctly. The runner also tries common
extensions (`.wav`, `.m4a`, `.aiff`, …).

**Voice packs.** Every language uses the same layout. XML paths stay
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

**Shareable `.xtf` pack**

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

Writes a zip archive (``.xtf``) with a languages-filtered XML, the frozen
``.btf.gz``, and `voice/en` + `voice/zh-tw` (override with ``--lang`` /
``DEMO_LANGS``). Voice ``.mp3`` clips are converted to ``.aac``
(``ffmpeg -c:a aac -ar 24000 -ac 1 -b:a 32k``) and ``<audio file=…>`` paths in
the packed XML are rewritten to ``.aac``. Pass ``--keep-mp3`` to skip
conversion. Open or drag the file in Web to play the tour; Desktop Open
loads the pack’s BTF; ``demo_runner.py builds/demo_8cores.xtf --launch`` runs
the desktop tour.

Declare languages in `<meta>` (or generate that block with `sync-xml`):

```xml
<languages default="en">
  <language id="en" label="English"/>
  <language id="zh-tw" label="中文"/>
</languages>
```

Default players: **stdlib on Windows** (`scripts/play_audio_clip.py` via winmm/MCI — no pip),
else macOS `afplay`, `ffplay` / `paplay` / `aplay`. Optional `pygame` if you already have a wheel.  
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
