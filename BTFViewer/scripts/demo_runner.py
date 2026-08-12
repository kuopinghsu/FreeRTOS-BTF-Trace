#!/usr/bin/env python3
"""Generic XML-driven GUI demo runner (PyAutoGUI + TTS).

Reads a demo description XML file and executes steps: speak, click, type,
hotkeys, waits, and interactive confirms.

Example::

    python3 scripts/demo_runner.py demos/demo_8cores/demo_8cores.xml --launch
    python3 scripts/demo_runner.py demos/my_demo.xml --dry-run --steps 1-5
    python3 scripts/demo_runner.py demos/my_demo.xml --interactive --short

XML overview
------------
See ``demos/demo_8cores/demo_8cores.xml`` for a full example.

.. code-block:: xml

    <demo name="…">
      <meta>…</meta>
      <defaults after_voice="1.5" pause="0.8"/>
      <targets>
        <point name="timeline" x="0.42" y="0.42"/>
      </targets>
      <macros>
        <macro name="fit"><hotkey keys="mod+0"/></macro>
      </macros>
      <steps>
        <step id="1" title="Intro">
          <voice>…</voice>
          <wait seconds="2"/>
          <click target="timeline"/>
        </step>
      </steps>
    </demo>

Actions: ``voice``, ``audio`` / ``play``, ``wait``, ``hotkey``, ``press``, ``type``,
``move``, ``click``, ``scroll``, ``sweep``, ``confirm``, ``focus``, ``macro``,
``highlight``, ``clear_highlight``, ``cursors``, ``clear_cursors``, ``zoom_range``,
``fit_view``, ``stats_section``, ``stats_reset``, ``limit``, ``jump_wcet``, ``panel``,
``view_mode``, ``cpu_load``, ``analysis``, ``find``, ``settings``, ``ui``, ``demo_api``,
``launch`` (usually from meta + ``--launch``).

Demo API (viewer must be started with ``BTFVIEWER_DEMO_API=1``, default port 8765)::

    <highlight task="CS[27]"/>
    <cursors times="3.085,3.310" unit="s" limit="true" zoom="true"/>
    <zoom_range start="3.085" end="3.310" unit="s"/>
    <stats_section id="health" expand="true" collapse_others="true"/>
    <stats_section id="block,priority" expand="true" collapse_others="true"/>
    <stats_reset/>
    <jump_wcet task="CS[27]"/>
    <limit on="true"/>
    <clear_cursors/>
    <clear_highlight/>
    <fit_view/>
    <panel name="stats"/>
    <view_mode mode="core"/>
    <cpu_load on="true"/>
    <analysis/>
    <analysis close="true"/>
    <find query="CS[27]"/>
    <find clear="true"/>
    <settings page="AI"/>

``--launch`` sets ``BTFVIEWER_DEMO_API=1`` automatically. Override with
``--demo-api-port`` / ``--no-demo-api``.

Audio files (pre-recorded narration)::

    <audio file="${XML_DIR}/voice/01_title.mp3"/>
    <!-- default: non-blocking — UI actions run while the clip plays;
         step end waits for the clip. Use block="true" or --audio-block to wait. -->
    <audio file="beep.wav" block="false"/>
    <wait_audio/>
    <stop_audio/>

Window geometry: ``detect_window`` finds the BTFViewer window (pid / title /
frontmost), preferring the **largest** on-screen window for that process so
dialogs do not steal coordinates. ``<targets>`` and ``x``/``y`` are
**fractions of that window** (0..1), refreshed on each ``<focus/>`` and before
clicks. If re-detect fails, the last good box is kept (never silently replaced
with the full screen while a real windowed box is known). Override with
``--win L,T,W,H`` or ``--window-title``.

Players: macOS ``afplay``, Linux ``ffplay``/``paplay``/``aplay``, Windows
PowerShell / ``start``. Override with ``--audio-cmd 'ffplay -nodisp -autoexit'``.

Move the mouse to a **screen corner** to abort (PyAutoGUI FAILSAFE).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
BTF_ROOT = SCRIPT_DIR.parent
REPO_ROOT = BTF_ROOT.parent

MOD = "command" if sys.platform == "darwin" else "ctrl"


# ---------------------------------------------------------------------------
# Logging / TTS / input
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[demo] {msg}", flush=True)


def shutil_which(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def speak(text: str, *, no_tts: bool, tts_cmd: Optional[str], tts_rate: int,
          dry_run: bool) -> None:
    text = " ".join((text or "").split())
    if not text:
        return
    if no_tts or dry_run:
        log(f"VOICE ({len(text)} chars): {text[:90]}{'…' if len(text) > 90 else ''}")
        if dry_run:
            return
        time.sleep(min(2.0, 0.3 + len(text) / 1000.0))
        return
    if tts_cmd:
        subprocess.run(shlex.split(tts_cmd) + [text], check=False)
        return
    if sys.platform == "darwin":
        subprocess.run(["say", "-r", str(tts_rate), text], check=False)
        return
    if shutil_which("espeak"):
        subprocess.run(["espeak", f"-s{tts_rate}", text], check=False)
        return
    log("No TTS backend; printing voice text.")
    print(text)
    time.sleep(min(8.0, 1.5 + len(text) / 14.0))


def resolve_media_path(raw: str, variables: Dict[str, str]) -> Path:
    """Resolve an audio/media path with ${vars} and search XML_DIR / CWD / BTF.

    If the exact path is missing, try common audio extensions and sibling
    ``voice/`` / ``text/`` folders (per-demo layout).
    """
    expanded = expand(raw, variables).strip()
    p = Path(expanded).expanduser()
    bases = [
        Path(variables.get("XML_DIR", ".")),
        Path(variables.get("CWD", ".")),
        Path(variables.get("BTF", ".")),
        Path(variables.get("REPO", ".")),
        Path("."),
    ]

    def _candidates(path: Path) -> List[Path]:
        out: List[Path] = [path]
        stem_paths = [path]
        if path.suffix:
            stem_paths.append(path.with_suffix(""))
        parent = path.parent
        name = path.name
        stem = path.stem if path.suffix else path.name
        # demo/voice/01_title.mp3 ↔ demo/01_title.mp3 ↔ demo/text/01_title.*
        alts = [
            parent / "voice" / name,
            parent / "voice" / stem,
            parent / "mp3" / name,
            parent / "mp3" / stem,
            parent / "text" / name,
            parent / "text" / stem,
            parent.parent / "voice" / name,
            parent.parent / "voice" / stem,
            parent.parent / "mp3" / name,
            parent.parent / "mp3" / stem,
            parent.parent / name,
            parent.parent / stem,
        ]
        if parent.name in ("mp3", "text", "audio", "voice"):
            alts.extend([
                parent.parent / name,
                parent.parent / stem,
                parent.parent / "voice" / name,
                parent.parent / "voice" / stem,
                parent.parent / "mp3" / name,
                parent.parent / "mp3" / stem,
            ])
        stem_paths.extend(alts)
        exts = (".mp3", ".wav", ".m4a", ".aiff", ".aif", ".ogg", ".flac")
        for sp in list(stem_paths):
            if sp.suffix:
                out.append(sp)
                for ext in exts:
                    if sp.suffix.lower() != ext:
                        out.append(sp.with_suffix(ext))
            else:
                for ext in exts:
                    out.append(sp.with_suffix(ext))
        # de-dupe preserving order
        seen = set()
        uniq: List[Path] = []
        for c in out:
            key = str(c)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(c)
        return uniq

    search: List[Path] = []
    if p.is_absolute():
        search.extend(_candidates(p))
    else:
        for base in bases:
            search.extend(_candidates((base / p)))
        search.extend(_candidates(p))

    for cand in search:
        try:
            resolved = cand.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved

    # Prefer the originally requested path for error messages
    if p.is_absolute():
        return p.resolve()
    return (Path(variables.get("XML_DIR", ".")) / p).resolve()


def _audio_command(path: Path, audio_cmd: Optional[str]) -> List[str]:
    if audio_cmd:
        return shlex.split(audio_cmd) + [str(path)]
    if sys.platform == "darwin" and shutil_which("afplay"):
        return ["afplay", str(path)]
    if shutil_which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    if shutil_which("paplay"):
        return ["paplay", str(path)]
    if shutil_which("aplay") and path.suffix.lower() in (".wav", ".wave"):
        return ["aplay", "-q", str(path)]
    if sys.platform == "win32":
        # PowerShell SoundPlayer works for WAV; otherwise start default app and hope.
        if path.suffix.lower() in (".wav", ".wave"):
            ps = (
                f"$p = New-Object System.Media.SoundPlayer '{path}'; "
                f"$p.PlaySync()"
            )
            return ["powershell", "-NoProfile", "-Command", ps]
        return ["cmd", "/c", "start", "/wait", "", str(path)]
    raise RuntimeError(
        f"No audio player found for {path}. Install afplay/ffplay/paplay, "
        "or pass --audio-cmd 'ffplay -nodisp -autoexit'"
    )


def play_audio(
    path: Path,
    *,
    block: bool = True,
    dry_run: bool = False,
    no_audio: bool = False,
    audio_cmd: Optional[str] = None,
) -> Optional[subprocess.Popen]:
    """Play an audio file. Returns Popen when block=False; None otherwise."""
    if no_audio or dry_run:
        log(f"AUDIO {'(skip) ' if no_audio else ''}{path}  block={block}")
        return None
    if not path.is_file():
        raise FileNotFoundError(f"audio file not found: {path}")
    cmd = _audio_command(path, audio_cmd)
    log(f"AUDIO play {' '.join(cmd)}")
    if block:
        subprocess.run(cmd, check=False)
        return None
    return subprocess.Popen(cmd)


# ---------------------------------------------------------------------------
# Config / window
# ---------------------------------------------------------------------------

@dataclass
class RunnerConfig:
    win: Tuple[int, int, int, int]
    targets: Dict[str, Tuple[float, float]]
    macros: Dict[str, List[ET.Element]]
    vars: Dict[str, str]
    defaults: Dict[str, float]
    pause: float
    after_voice: float
    ai_wait: float
    interactive: bool
    no_tts: bool
    no_audio: bool
    tts_cmd: Optional[str]
    audio_cmd: Optional[str]
    tts_rate: int
    dry_run: bool
    skip_optional: bool
    skip_tags: set = field(default_factory=set)
    # Background audio processes started with block="false"
    bg_audio: List[subprocess.Popen] = field(default_factory=list)
    # When True (default), <audio> plays while later actions run; wait at step end.
    audio_block: bool = False
    window_title: str = "BTFViewer"
    # If set, detect_window always uses this instead of auto-detect.
    win_fixed: Optional[Tuple[int, int, int, int]] = None
    pag: Any = None
    viewer_pid: Optional[int] = None
    # Localhost demo control API (BTFVIEWER_DEMO_API on the viewer).
    demo_api_url: str = "http://127.0.0.1:8765/demo"
    demo_api_enabled: bool = True


def _import_pyautogui():
    try:
        import pyautogui
    except ImportError as exc:
        raise SystemExit(
            "pyautogui is required:\n"
            "  python3 -m pip install -r scripts/requirements-demo.txt\n"
            f"({exc})"
        ) from exc
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08
    return pyautogui


def _window_area(bounds: Tuple[int, int, int, int]) -> int:
    return max(0, int(bounds[2])) * max(0, int(bounds[3]))


def _is_plausible_window(
    bounds: Tuple[int, int, int, int],
    *,
    min_w: int = 200,
    min_h: int = 200,
) -> bool:
    return bounds[2] >= min_w and bounds[3] >= min_h


def _is_full_screen_box(
    bounds: Tuple[int, int, int, int],
    screen: Tuple[int, int],
    *,
    area_frac: float = 0.92,
) -> bool:
    """True when *bounds* look like a whole-display fallback, not a windowed app."""
    sw, sh = int(screen[0]), int(screen[1])
    if sw < 200 or sh < 200:
        return False
    left, top, width, height = bounds
    if left > 8 or top > 8:
        return False
    return _window_area(bounds) >= int(area_frac * sw * sh)


def choose_window_bounds(
    candidates: List[Tuple[int, int, int, int]],
    *,
    prev: Optional[Tuple[int, int, int, int]] = None,
    screen: Optional[Tuple[int, int]] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """Pick the best app window from *candidates*.

    Prefers the largest plausible window. Rejects a sudden shrink vs *prev*
    (typical modal/dialog steal) and avoids replacing a known windowed box with
    a full-screen-sized guess when better candidates exist.
    """
    plausible = [b for b in candidates if _is_plausible_window(b)]
    if not plausible and prev and _is_plausible_window(prev):
        return prev
    if not plausible:
        return None

    # Largest first.
    plausible.sort(key=_window_area, reverse=True)
    best = plausible[0]

    if prev and _is_plausible_window(prev):
        prev_area = _window_area(prev)
        best_area = _window_area(best)
        # Dialog / sheet often becomes "window 1"; keep the main frame.
        if prev_area >= 400 * 300 and best_area < int(0.45 * prev_area):
            return prev
        if (
            screen is not None
            and _is_full_screen_box(best, screen)
            and not _is_full_screen_box(prev, screen)
        ):
            # Prefer the last known windowed box over a display-sized miss.
            return prev
    return best


def detect_window(
    pag,
    *,
    pid: Optional[int] = None,
    title_substr: str = "BTFViewer",
    prev: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[int, int, int, int]:
    """Return (left, top, width, height) for the target app window.

    Prefers the launched process (pid; largest window), then a window whose
    title contains *title_substr*, then the frontmost window. If detection
    fails, keeps *prev* when it looks like a real window instead of jumping to
    the full screen (which breaks fractional coords for windowed demos).
    Fractions in ``<targets>`` / ``x``/``y`` are relative to this box.
    """
    try:
        screen = (int(pag.size()[0]), int(pag.size()[1]))
    except Exception:
        screen = (0, 0)

    candidates: List[Tuple[int, int, int, int]] = []
    for getter in (
        lambda: _window_bounds_macos(pid=pid, title_substr=title_substr),
        lambda: _window_bounds_linux(title_substr=title_substr),
        lambda: _window_bounds_windows(title_substr=title_substr),
    ):
        try:
            got = getter()
        except Exception:
            got = None
        if isinstance(got, list):
            candidates.extend(got)
        elif got:
            candidates.append(got)

    chosen = choose_window_bounds(candidates, prev=prev, screen=screen)
    if chosen is not None:
        return chosen

    if prev and _is_plausible_window(prev):
        if not _is_full_screen_box(prev, screen) or screen[0] < 200:
            log(f"window detect failed; keeping last good L,T,W,H={prev}")
            return prev

    w, h = screen
    if w < 200 or h < 200:
        # Headless / no display (e.g. CI dry-run): keep a synthetic desktop box.
        w, h = max(w, 1280), max(h, 800)
        log(f"window detect fallback → synthetic {w}x{h}")
    else:
        log(f"window detect fallback → full screen {w}x{h}")
    return 0, 0, w, h


def _parse_l_t_w_h(text: str) -> Optional[Tuple[int, int, int, int]]:
    text = (text or "").strip().replace(" ", "")
    if not text:
        return None
    parts = re.split(r"[,x]", text)
    if len(parts) != 4:
        return None
    try:
        left, top, width, height = (int(float(p)) for p in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def _parse_l_t_w_h_list(text: str) -> List[Tuple[int, int, int, int]]:
    """Parse one-or-more ``L,T,W,H`` records separated by ``;`` or newlines."""
    out: List[Tuple[int, int, int, int]] = []
    for chunk in re.split(r"[;\n]+", text or ""):
        parsed = _parse_l_t_w_h(chunk)
        if parsed:
            out.append(parsed)
    return out


def _window_bounds_macos_quartz(
    *,
    pid: Optional[int] = None,
    title_substr: str = "BTFViewer",
) -> List[Tuple[int, int, int, int]]:
    """On-screen window boxes via CoreGraphics (layer 0 only)."""
    if sys.platform != "darwin":
        return []
    try:
        import Quartz  # type: ignore
    except Exception:
        return []
    try:
        opts = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        infos = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
    except Exception:
        return []
    title_l = (title_substr or "").lower()
    by_pid: List[Tuple[int, int, int, int]] = []
    by_title: List[Tuple[int, int, int, int]] = []
    for info in infos:
        try:
            layer = int(info.get(Quartz.kCGWindowLayer, 0) or 0)
            if layer != 0:
                continue
            owner_pid = int(info.get(Quartz.kCGWindowOwnerPID, 0) or 0)
            name = str(info.get(Quartz.kCGWindowName, "") or "")
            bounds = info.get(Quartz.kCGWindowBounds) or {}
            left = int(bounds.get("X", 0))
            top = int(bounds.get("Y", 0))
            width = int(bounds.get("Width", 0))
            height = int(bounds.get("Height", 0))
        except Exception:
            continue
        box = (left, top, width, height)
        if not _is_plausible_window(box):
            continue
        if pid is not None and owner_pid == int(pid):
            by_pid.append(box)
        elif title_l and title_l in name.lower():
            by_title.append(box)
    return by_pid or by_title


def focus_pid(pid: Optional[int]) -> None:
    if sys.platform != "darwin" or not pid:
        return
    script = (
        f'tell application "System Events"\n'
        f'  try\n'
        f'    set frontmost of (first process whose unix id is {int(pid)}) to true\n'
        f'  end try\n'
        f'end tell'
    )
    subprocess.run(["osascript", "-e", script], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _window_bounds_macos(
    *,
    pid: Optional[int] = None,
    title_substr: str = "BTFViewer",
) -> List[Tuple[int, int, int, int]]:
    if sys.platform != "darwin":
        return []
    found = _window_bounds_macos_quartz(pid=pid, title_substr=title_substr)
    if found:
        return found

    title = title_substr.replace("\\", "\\\\").replace('"', '\\"')
    scripts: List[str] = []
    if pid:
        # Return every accessible window; Python picks the largest.
        scripts.append(
            f'''
            tell application "System Events"
              try
                set p to first process whose unix id is {int(pid)}
                set out to ""
                repeat with w in windows of p
                  try
                    set {{x, y}} to position of w
                    set {{ww, hh}} to size of w
                    if ww ≥ 200 and hh ≥ 200 then
                      set rec to (x as text) & "," & (y as text) & "," & (ww as text) & "," & (hh as text)
                      if out is "" then
                        set out to rec
                      else
                        set out to out & ";" & rec
                      end if
                    end if
                  end try
                end repeat
                return out
              end try
            end tell
            '''
        )
    scripts.append(
        f'''
        tell application "System Events"
          set out to ""
          repeat with p in application processes
            try
              repeat with w in windows of p
                try
                  set nm to name of w as text
                  if nm contains "{title}" then
                    set {{x, y}} to position of w
                    set {{ww, hh}} to size of w
                    if ww ≥ 200 and hh ≥ 200 then
                      set rec to (x as text) & "," & (y as text) & "," & (ww as text) & "," & (hh as text)
                      if out is "" then
                        set out to rec
                      else
                        set out to out & ";" & rec
                      end if
                    end if
                  end if
                end try
              end repeat
            end try
          end repeat
          return out
        end tell
        '''
    )
    # Frontmost only as a last AppleScript resort (may be Terminal/IDE).
    scripts.append(
        '''
        tell application "System Events"
          try
            set p to first application process whose frontmost is true
            set out to ""
            repeat with w in windows of p
              try
                set {x, y} to position of w
                set {ww, hh} to size of w
                if ww ≥ 200 and hh ≥ 200 then
                  set rec to (x as text) & "," & (y as text) & "," & (ww as text) & "," & (hh as text)
                  if out is "" then
                    set out to rec
                  else
                    set out to out & ";" & rec
                  end if
                end if
              end try
            end repeat
            return out
          end try
        end tell
        '''
    )
    for script in scripts:
        try:
            out = subprocess.check_output(
                ["osascript", "-e", script],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            continue
        parsed = _parse_l_t_w_h_list(out)
        if parsed:
            return parsed
    return []


def _window_bounds_linux(
    *,
    title_substr: str = "BTFViewer",
) -> Optional[Tuple[int, int, int, int]]:
    if not sys.platform.startswith("linux"):
        return None
    if not shutil_which("xdotool"):
        return None
    try:
        wid = subprocess.check_output(
            ["xdotool", "search", "--name", title_substr],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip().splitlines()
        if not wid:
            wid = subprocess.check_output(
                ["xdotool", "getactivewindow"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip().splitlines()
        if not wid:
            return None
        geo = subprocess.check_output(
            ["xdotool", "getwindowgeometry", "--shell", wid[0].strip()],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    vals: Dict[str, int] = {}
    for line in geo.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                vals[k.strip()] = int(v.strip())
            except ValueError:
                pass
    if not {"X", "Y", "WIDTH", "HEIGHT"} <= vals.keys():
        return None
    return vals["X"], vals["Y"], vals["WIDTH"], vals["HEIGHT"]


def _window_bounds_windows(
    *,
    title_substr: str = "BTFViewer",
) -> Optional[Tuple[int, int, int, int]]:
    if sys.platform != "win32":
        return None
    try:
        import pygetwindow as gw  # type: ignore
    except ImportError:
        return None
    try:
        wins = gw.getWindowsWithTitle(title_substr) or []
        if not wins:
            wins = [w for w in gw.getAllWindows() if title_substr.lower() in (w.title or "").lower()]
        if not wins:
            active = gw.getActiveWindow()
            wins = [active] if active else []
        for w in wins:
            if w is None:
                continue
            left, top = int(w.left), int(w.top)
            width, height = int(w.width), int(w.height)
            if width >= 200 and height >= 200:
                return left, top, width, height
    except Exception:
        return None
    return None


def parse_win(s: str) -> Tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in s.replace("x", ",").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected L,T,W,H")
    return parts[0], parts[1], parts[2], parts[3]


# ---------------------------------------------------------------------------
# XML load + variable expansion
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\$\{([A-Za-z0-9_./-]+)\}")


def expand(text: Optional[str], variables: Dict[str, str]) -> str:
    if text is None:
        return ""

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in variables:
            return variables[key]
        # Allow nested path-like defaults
        return m.group(0)

    # Expand repeatedly for nested ${…}
    out = text
    for _ in range(8):
        nxt = _VAR_RE.sub(repl, out)
        if nxt == out:
            break
        out = nxt
    return out


def text_content(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    parts: List[str] = [el.text or ""]
    for child in el:
        parts.append(text_content(child))
        parts.append(child.tail or "")
    return "".join(parts).strip()


def load_demo_xml(path: Path) -> ET.Element:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "demo":
        raise SystemExit(f"root element must be <demo>, got <{root.tag}>")
    return root


def build_variables(root: ET.Element, xml_path: Path, extras: Dict[str, str]) -> Dict[str, str]:
    meta = root.find("meta")
    vars_: Dict[str, str] = {
        "REPO": str(REPO_ROOT),
        "BTF": str(BTF_ROOT),
        "PYTHON": sys.executable,
        "MOD": MOD,
        "XML": str(xml_path.resolve()),
        "XML_DIR": str(xml_path.resolve().parent),
        "HOME": str(Path.home()),
        "CWD": str(Path.cwd()),
    }
    if meta is not None:
        for child in meta:
            if child.tag in ("title", "description", "author"):
                continue
            if child.tag == "var":
                name = child.attrib.get("name", "").strip()
                if name:
                    vars_[name] = expand(text_content(child) or child.attrib.get("value", ""), vars_)
                continue
            # <trace>, <cwd>, …
            vars_[child.tag] = expand(text_content(child) or child.attrib.get("value", ""), vars_)
    vars_.update(extras)
    # Re-expand so extras can reference meta and vice versa
    for _ in range(3):
        vars_ = {k: expand(v, vars_) for k, v in vars_.items()}
    return vars_


def parse_targets(root: ET.Element) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    targets = root.find("targets")
    if targets is None:
        return out
    for pt in targets.findall("point"):
        name = pt.attrib.get("name", "").strip()
        if not name:
            continue
        out[name] = (float(pt.attrib["x"]), float(pt.attrib["y"]))
    return out


def parse_macros(root: ET.Element) -> Dict[str, List[ET.Element]]:
    out: Dict[str, List[ET.Element]] = {}
    macros = root.find("macros")
    if macros is None:
        return out
    for macro in macros.findall("macro"):
        name = macro.attrib.get("name", "").strip()
        if name:
            out[name] = list(macro)
    return out


def parse_defaults(root: ET.Element) -> Dict[str, float]:
    el = root.find("defaults")
    if el is None:
        return {
            "after_voice": 1.5,
            "pause": 0.8,
            "ai_wait": 35.0,
            "move_duration": 0.35,
            "audio_block": 0.0,
        }
    def f(name: str, default: float) -> float:
        return float(el.attrib.get(name, default))

    def flag(name: str, default: bool) -> float:
        raw = el.attrib.get(name)
        if raw is None:
            return 1.0 if default else 0.0
        return 1.0 if raw.lower() not in ("0", "false", "no") else 0.0

    return {
        "after_voice": f("after_voice", 1.5),
        "pause": f("pause", 0.8),
        "ai_wait": f("ai_wait", 35.0),
        "move_duration": f("move_duration", 0.35),
        # 0 = overlap UI with narration (default); 1 = wait for each clip
        "audio_block": flag("audio_block", False),
    }


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------

class DemoRunner:
    def __init__(self, pag: Any, cfg: RunnerConfig, viewer_pid: Optional[int] = None):
        self.pag = pag
        self.cfg = cfg
        self.viewer_pid = viewer_pid if viewer_pid is not None else cfg.viewer_pid
        self.cfg.pag = pag
        self.cfg.viewer_pid = self.viewer_pid
        self._macro_depth = 0

    # -- geometry -----------------------------------------------------------

    def refresh_window(self, *, force: bool = False) -> Tuple[int, int, int, int]:
        """Re-read the target window box so relative x/y stay accurate."""
        if self.cfg.win_fixed is not None:
            self.cfg.win = self.cfg.win_fixed
            return self.cfg.win
        if self.cfg.dry_run and not force:
            # Keep last known / synthetic box; avoid clobbering with 0x0.
            left, top, width, height = self.cfg.win
            if width >= 200 and height >= 200:
                return self.cfg.win
        prev = self.cfg.win
        bounds = detect_window(
            self.pag,
            pid=self.viewer_pid,
            title_substr=self.cfg.window_title,
            prev=prev if _is_plausible_window(prev) else None,
        )
        self.cfg.win = bounds
        if bounds != prev:
            log(f"window L,T,W,H={bounds}")
        return bounds

    def resolve_xy(self, el: ET.Element) -> Tuple[int, int]:
        self.refresh_window()
        left, top, width, height = self.cfg.win
        if width <= 0 or height <= 0:
            raise RuntimeError(f"invalid window size {self.cfg.win}")
        if "target" in el.attrib:
            name = el.attrib["target"]
            if name not in self.cfg.targets:
                raise KeyError(f"unknown target {name!r} (define <point> in <targets>)")
            fx, fy = self.cfg.targets[name]
        else:
            fx = float(el.attrib.get("x", "0.5"))
            fy = float(el.attrib.get("y", "0.5"))
        # Absolute pixel coords if |value| > 1 (escape hatch)
        if abs(fx) > 1.0 or abs(fy) > 1.0:
            x = int(left + fx) if abs(fx) > 1.0 else int(left + fx * width)
            y = int(top + fy) if abs(fy) > 1.0 else int(top + fy * height)
        else:
            x = int(left + fx * width)
            y = int(top + fy * height)
        return x, y

    # -- primitives ---------------------------------------------------------

    def wait(self, seconds: float, why: str = "") -> None:
        if why:
            log(f"wait {seconds:.1f}s — {why}")
        if self.cfg.dry_run:
            return
        time.sleep(max(0.0, seconds))

    def confirm(self, prompt: str) -> None:
        if self.cfg.dry_run:
            log(f"(dry-run) {prompt}")
            return
        if not self.cfg.interactive:
            return
        input(f"[demo] {prompt}  [Enter] ")

    def focus(self) -> None:
        focus_pid(self.viewer_pid)
        # Frontmost window may take a beat to settle before bounds are readable.
        if not self.cfg.dry_run:
            time.sleep(0.25)
        self.refresh_window(force=True)

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> None:
        dur = self.cfg.defaults["move_duration"] if duration is None else duration
        log(f"move → ({x},{y})")
        if self.cfg.dry_run:
            return
        self.pag.moveTo(x, y, duration=max(0.0, dur))

    def click_xy(self, x: int, y: int, clicks: int = 1) -> None:
        self.move_to(x, y, duration=0.25)
        if self.cfg.dry_run:
            return
        self.pag.click(clicks=clicks)

    def hotkey(self, keys: str) -> None:
        parts = [p.strip() for p in keys.replace("-", "+").split("+") if p.strip()]
        mapped = []
        for p in parts:
            low = p.lower()
            if low in ("mod", "meta", "cmd", "command"):
                mapped.append(MOD)
            elif low == "ctrl":
                mapped.append("ctrl" if sys.platform != "darwin" else MOD)
            elif low == "control":
                mapped.append(MOD if sys.platform == "darwin" else "ctrl")
            else:
                mapped.append(low)
        log(f"hotkey {'+'.join(mapped)}")
        if self.cfg.dry_run:
            return
        self.pag.hotkey(*mapped)

    def press(self, key: str, times: int = 1) -> None:
        log(f"press {key} x{times}")
        if self.cfg.dry_run:
            return
        for _ in range(times):
            self.pag.press(key)

    def type_text(self, text: str, interval: float = 0.03) -> None:
        text = expand(text, self.cfg.vars)
        log(f"type {text!r}")
        if self.cfg.dry_run:
            return
        # Prefer clipboard paste for non-ASCII / speed
        try:
            self.pag.write(text, interval=interval)
        except Exception:
            self.pag.typewrite(text, interval=interval)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        log(f"scroll {clicks}")
        if self.cfg.dry_run:
            return
        if x is not None and y is not None:
            self.pag.moveTo(x, y, duration=0.2)
        self.pag.scroll(clicks)

    def _play_audio_action(self, el: ET.Element) -> None:
        raw = (
            el.attrib.get("file")
            or el.attrib.get("src")
            or el.attrib.get("path")
            or text_content(el)
        )
        raw = expand(raw, self.cfg.vars).strip()
        if not raw:
            raise ValueError("<audio>/<play> requires file= or text path")
        path = resolve_media_path(raw, self.cfg.vars)
        if "block" in el.attrib:
            block = el.attrib.get("block", "true").lower() not in ("0", "false", "no")
        else:
            block = bool(self.cfg.audio_block)
        after = float(el.attrib.get("after", "0"))
        # Overlap mode: stop prior narration, start this clip, continue UI actions.
        if not block and self.cfg.bg_audio:
            self._stop_bg_audio()
        proc = play_audio(
            path,
            block=block,
            dry_run=self.cfg.dry_run,
            no_audio=self.cfg.no_audio,
            audio_cmd=self.cfg.audio_cmd,
        )
        if proc is not None:
            self.cfg.bg_audio.append(proc)
        if after > 0:
            self.wait(after, "after audio")
        elif not block:
            # Brief lead-in so the first words are audible before the next click.
            self.wait(0.35, "audio lead-in")

    def _wait_bg_audio(self) -> None:
        alive = [p for p in self.cfg.bg_audio if p.poll() is None]
        if not alive:
            self.cfg.bg_audio.clear()
            return
        log(f"wait_audio ({len(alive)} clip(s))")
        if self.cfg.dry_run:
            self.cfg.bg_audio.clear()
            return
        for p in alive:
            try:
                p.wait()
            except Exception:
                pass
        self.cfg.bg_audio.clear()

    def _stop_bg_audio(self) -> None:
        log(f"stop_audio ({len(self.cfg.bg_audio)})")
        if self.cfg.dry_run:
            self.cfg.bg_audio.clear()
            return
        for p in self.cfg.bg_audio:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self.cfg.bg_audio.clear()

    # -- demo HTTP API ------------------------------------------------------

    def demo_api(self, payload: Dict[str, Any], *, settle: float = 0.35) -> Any:
        """POST JSON to the viewer's opt-in demo control API."""
        op = payload.get("op", "?")
        log(f"demo_api {op} { {k: v for k, v in payload.items() if k != 'op'} }")
        if self.cfg.dry_run or not self.cfg.demo_api_enabled:
            return {"ok": True, "dry_run": True}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.cfg.demo_api_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"demo API unreachable at {self.cfg.demo_api_url}: {exc}\n"
                "Launch with BTFVIEWER_DEMO_API=1 (demo_runner --launch does this)."
            ) from exc
        if not body.get("ok", False):
            raise RuntimeError(f"demo API error: {body.get('error') or body}")
        if settle > 0:
            time.sleep(settle)
        return body.get("result")

    def wait_demo_api(self, timeout: float = 30.0) -> bool:
        """Wait until POST/GET health succeeds and a trace is ready (if possible)."""
        if self.cfg.dry_run or not self.cfg.demo_api_enabled:
            return True
        base = self.cfg.demo_api_url.rstrip("/")
        health = base if base.endswith("/demo") else f"{base}/demo"
        deadline = time.time() + max(1.0, timeout)
        last_err = ""
        while time.time() < deadline:
            try:
                req = urllib.request.Request(
                    health,
                    data=json.dumps({"op": "ping"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    body = json.loads(resp.read().decode("utf-8") or "{}")
                if body.get("ok"):
                    result = body.get("result") or {}
                    if result.get("ready", True):
                        log("demo API ready")
                        return True
                    last_err = "viewer up; waiting for trace…"
                else:
                    last_err = str(body.get("error") or body)
            except Exception as exc:
                last_err = str(exc)
            time.sleep(0.4)
        log(f"demo API not ready ({last_err})")
        return False

    # -- action dispatch ----------------------------------------------------

    def run_action(self, el: ET.Element, step_vars: Optional[Dict[str, str]] = None) -> None:
        tag = el.tag
        # Merge step-local vars for this action
        saved = None
        if step_vars:
            saved = dict(self.cfg.vars)
            self.cfg.vars.update(step_vars)

        try:
            if tag == "voice":
                speak(
                    expand(text_content(el), self.cfg.vars),
                    no_tts=self.cfg.no_tts,
                    tts_cmd=self.cfg.tts_cmd,
                    tts_rate=self.cfg.tts_rate,
                    dry_run=self.cfg.dry_run,
                )
                after = float(el.attrib.get("after", self.cfg.after_voice))
                self.wait(after, "after voice")
            elif tag in ("audio", "play"):
                self._play_audio_action(el)
            elif tag == "wait_audio":
                self._wait_bg_audio()
            elif tag == "stop_audio":
                self._stop_bg_audio()
            elif tag == "wait":
                why = expand(el.attrib.get("why", ""), self.cfg.vars)
                if el.attrib.get("ai", "").lower() in ("1", "true", "yes"):
                    sec = float(el.attrib.get("seconds", self.cfg.ai_wait))
                else:
                    sec = float(el.attrib.get("seconds", "1"))
                self.wait(sec, why or "wait")
            elif tag == "hotkey":
                self.hotkey(expand(el.attrib.get("keys", ""), self.cfg.vars))
            elif tag == "press":
                self.press(
                    expand(el.attrib.get("key", ""), self.cfg.vars),
                    times=int(el.attrib.get("times", "1")),
                )
            elif tag == "type":
                self.type_text(
                    expand(el.attrib.get("text", "") or text_content(el), self.cfg.vars),
                    interval=float(el.attrib.get("interval", "0.03")),
                )
            elif tag == "move":
                x, y = self.resolve_xy(el)
                dur = float(el.attrib["duration"]) if "duration" in el.attrib else None
                self.move_to(x, y, duration=dur)
            elif tag == "click":
                x, y = self.resolve_xy(el)
                self.click_xy(x, y, clicks=int(el.attrib.get("clicks", "1")))
            elif tag == "scroll":
                clicks = int(el.attrib.get("clicks", "1"))
                if "target" in el.attrib or "x" in el.attrib:
                    x, y = self.resolve_xy(el)
                    self.scroll(clicks, x, y)
                else:
                    self.scroll(clicks)
            elif tag == "sweep":
                # Horizontal mouse sweep at y (fraction) from x0→x1
                self.refresh_window()
                left, top, width, height = self.cfg.win
                yf = float(el.attrib.get("y", "0.055"))
                x0 = float(el.attrib.get("x0", "0.1"))
                x1 = float(el.attrib.get("x1", "0.85"))
                steps = int(el.attrib.get("steps", "8"))
                pause = float(el.attrib.get("pause", "0.3"))
                y = int(top + yf * height)
                log(f"sweep y={yf} {x0}→{x1}  win={self.cfg.win}")
                if not self.cfg.dry_run:
                    for i in range(steps):
                        fx = x0 + (x1 - x0) * (i / max(1, steps - 1))
                        self.pag.moveTo(int(left + fx * width), y, duration=0.2)
                        time.sleep(pause)
            elif tag == "confirm":
                self.confirm(expand(el.attrib.get("prompt", "") or text_content(el), self.cfg.vars))
            elif tag == "focus":
                self.focus()
            elif tag == "macro":
                self.run_macro(
                    expand(el.attrib.get("ref", el.attrib.get("name", "")), self.cfg.vars),
                    el,
                )
            elif tag == "highlight":
                task = expand(el.attrib.get("task", el.attrib.get("name", "")), self.cfg.vars)
                self.demo_api({"op": "highlight", "task": task})
            elif tag == "clear_highlight":
                self.demo_api({"op": "clear_highlight"})
            elif tag == "cursors":
                payload: Dict[str, Any] = {
                    "op": "cursors",
                    "times": expand(
                        el.attrib.get("times", el.attrib.get("timestamps", "")),
                        self.cfg.vars,
                    ),
                }
                if "unit" in el.attrib:
                    payload["unit"] = expand(el.attrib["unit"], self.cfg.vars)
                if "limit" in el.attrib:
                    payload["limit"] = expand(el.attrib["limit"], self.cfg.vars)
                if "zoom" in el.attrib:
                    payload["zoom"] = expand(el.attrib["zoom"], self.cfg.vars)
                self.demo_api(payload, settle=0.5)
            elif tag == "clear_cursors":
                self.demo_api({"op": "clear_cursors"})
            elif tag == "zoom_range":
                payload = {
                    "op": "zoom_range",
                    "start": expand(el.attrib.get("start", ""), self.cfg.vars),
                    "end": expand(el.attrib.get("end", ""), self.cfg.vars),
                }
                if "unit" in el.attrib:
                    payload["unit"] = expand(el.attrib["unit"], self.cfg.vars)
                if not payload["start"] and el.attrib.get("times"):
                    payload["times"] = expand(el.attrib["times"], self.cfg.vars)
                    payload.pop("start", None)
                    payload.pop("end", None)
                self.demo_api(payload, settle=0.6)
            elif tag in ("fit_view", "fit_api"):
                self.demo_api({"op": "fit"}, settle=0.4)
            elif tag == "limit":
                on = expand(
                    el.attrib.get("on", el.attrib.get("enabled", "true")),
                    self.cfg.vars,
                )
                self.demo_api({"op": "limit", "on": on})
            elif tag == "stats_section":
                payload = {
                    "op": "stats_section",
                    "id": expand(
                        el.attrib.get("id", el.attrib.get("section", "")),
                        self.cfg.vars,
                    ),
                }
                for key in ("expand", "collapse_others", "scroll"):
                    if key in el.attrib:
                        payload[key] = expand(el.attrib[key], self.cfg.vars)
                # Expanding tall tables needs a moment for layout + scroll settle.
                settle = 0.55
                if str(payload.get("expand", "true")).lower() in ("0", "false", "no", "off"):
                    settle = 0.35
                self.demo_api(payload, settle=settle)
            elif tag in ("stats_reset", "stats_done"):
                # Collapse sections and return the Statistics list to the top.
                self.demo_api(
                    {
                        "op": "stats_section",
                        "id": "",
                        "expand": "false",
                        "collapse_others": "true",
                        "scroll": "top",
                    },
                    settle=0.4,
                )
            elif tag == "jump_wcet":
                task = expand(el.attrib.get("task", el.attrib.get("name", "")), self.cfg.vars)
                self.demo_api({"op": "jump_wcet", "task": task}, settle=0.7)
            elif tag == "panel":
                name = expand(
                    el.attrib.get("name", el.attrib.get("tab", "stats")),
                    self.cfg.vars,
                )
                self.demo_api({"op": "panel", "name": name})
            elif tag in ("view_mode", "view"):
                mode = expand(
                    el.attrib.get("mode", el.attrib.get("name", "task")),
                    self.cfg.vars,
                )
                self.demo_api({"op": "view_mode", "mode": mode}, settle=0.45)
            elif tag in ("cpu_load", "load"):
                on = expand(
                    el.attrib.get("on", el.attrib.get("enabled", "true")),
                    self.cfg.vars,
                )
                self.demo_api({"op": "cpu_load", "on": on}, settle=0.4)
            elif tag == "analysis":
                payload = {"op": "analysis"}
                for key in ("open", "close", "action"):
                    if key in el.attrib:
                        payload[key] = expand(el.attrib[key], self.cfg.vars)
                settle = 0.7 if "close" not in el.attrib else 0.45
                self.demo_api(payload, settle=settle)
            elif tag == "find":
                payload = {"op": "find"}
                for key in ("query", "text", "q", "clear", "next"):
                    if key in el.attrib:
                        payload[key] = expand(el.attrib[key], self.cfg.vars)
                if not any(k in payload for k in ("query", "text", "q", "clear")):
                    payload["query"] = expand(text_content(el), self.cfg.vars)
                self.demo_api(payload, settle=0.45)
            elif tag == "settings":
                page = expand(
                    el.attrib.get("page", el.attrib.get("name", "Appearance")),
                    self.cfg.vars,
                )
                self.demo_api({"op": "settings", "page": page}, settle=0.5)
            elif tag in ("ui", "command"):
                payload = {"op": "ui"}
                for k, v in el.attrib.items():
                    payload[k] = expand(v, self.cfg.vars)
                self.demo_api(payload)
            elif tag == "demo_api":
                payload = {"op": expand(el.attrib.get("op", ""), self.cfg.vars)}
                for k, v in el.attrib.items():
                    if k == "op":
                        continue
                    payload[k] = expand(v, self.cfg.vars)
                self.demo_api(payload)
            elif tag == "log":
                log(expand(el.attrib.get("message", "") or text_content(el), self.cfg.vars))
            elif tag in ("note", "comment"):
                pass
            else:
                log(f"unknown action <{tag}>, skip")
        finally:
            if saved is not None:
                self.cfg.vars = saved

    def run_macro(self, name: str, call_el: Optional[ET.Element] = None) -> None:
        if name not in self.cfg.macros:
            raise KeyError(f"unknown macro {name!r}")
        if self._macro_depth > 20:
            raise RuntimeError("macro recursion limit")
        # Params: <macro ref="place_cursor" time="3.085"/> or <param name="time">…
        local: Dict[str, str] = {}
        if call_el is not None:
            for k, v in call_el.attrib.items():
                if k in ("ref", "name"):
                    continue
                local[k] = expand(v, self.cfg.vars)
            for p in call_el.findall("param"):
                pn = p.attrib.get("name", "")
                if pn:
                    local[pn] = expand(text_content(p) or p.attrib.get("value", ""), self.cfg.vars)
        log(f"macro {name} {local or ''}")
        self._macro_depth += 1
        try:
            saved = dict(self.cfg.vars)
            self.cfg.vars.update(local)
            for child in self.cfg.macros[name]:
                self.run_action(child)
            self.cfg.vars = saved
        finally:
            self._macro_depth -= 1

    def run_step(self, step: ET.Element) -> None:
        sid = step.attrib.get("id", "?")
        title = step.attrib.get("title", "")
        optional = step.attrib.get("optional", "").lower() in ("1", "true", "yes")
        tags = {t.strip() for t in step.attrib.get("tags", "").split(",") if t.strip()}
        if optional and self.cfg.skip_optional:
            log(f"skip optional step {sid} ({title})")
            return
        if tags & self.cfg.skip_tags:
            log(f"skip step {sid} tags={tags & self.cfg.skip_tags}")
            return
        log(f"==== Step {sid} — {title} ====")
        self.confirm(f"Ready for step {sid}?")
        self.focus()
        for child in step:
            if child.tag in ("title",):
                continue
            self.run_action(child)
        # Finish any overlapping narration before the next step.
        self._wait_bg_audio()
        self.wait(self.cfg.pause, "inter-step")


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------

def launch_from_meta(
    root: ET.Element,
    variables: Dict[str, str],
    *,
    demo_api: bool = True,
    demo_api_port: int = 8765,
) -> Optional[subprocess.Popen]:
    meta = root.find("meta")
    if meta is None:
        return None
    launch = meta.find("launch")
    if launch is None:
        # Convenience: <trace> alone → bundled desktop app
        trace = variables.get("trace", "")
        if not trace:
            return None
        bundled = BTF_ROOT / "builds" / "btf_viewer.py"
        if not bundled.is_file():
            raise SystemExit(
                f"bundled viewer missing: {bundled}\n"
                "  Run: make -C BTFViewer bundle"
            )
        cmd = [sys.executable, str(bundled), trace]
        cwd = variables.get("cwd", str(BTF_ROOT))
    else:
        cmd_s = expand(launch.attrib.get("cmd") or text_content(launch), variables)
        cmd = shlex.split(cmd_s)
        cwd = expand(launch.attrib.get("cwd", variables.get("cwd", str(BTF_ROOT))), variables)
        if not cmd:
            raise SystemExit("<launch> produced an empty command")
        # Relative viewer path → resolve against cwd / BTF_ROOT for a clear error.
        viewer = Path(cmd[1]) if len(cmd) >= 2 and cmd[0] and not cmd[1].startswith("-") else None
        if viewer is not None and viewer.suffix == ".py" and not viewer.is_file():
            alt = Path(cwd) / viewer
            if not alt.is_file():
                raise SystemExit(
                    f"launch viewer not found: {viewer}\n"
                    "  Run: make -C BTFViewer bundle"
                )
    env = os.environ.copy()
    if demo_api:
        env["BTFVIEWER_DEMO_API"] = "1"
        env["BTFVIEWER_DEMO_API_PORT"] = str(int(demo_api_port))
    log(f"launch: {' '.join(cmd)}  (cwd={cwd})")
    return subprocess.Popen(cmd, cwd=cwd, env=env)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_steps(s: str) -> Optional[List[str]]:
    """Return list of step id strings, or None for all."""
    if not s or s.strip().lower() in ("all", "*"):
        return None
    out: List[str] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part and part[0].isdigit():
            a, b = part.split("-", 1)
            out.extend(str(i) for i in range(int(a), int(b) + 1))
        else:
            out.append(part)
    return out


def calibrate(pag) -> None:
    log("Move the mouse over the BTFViewer window; Ctrl+C to quit.")
    log("Shows screen px and fraction within the detected app window.")
    prev = None
    try:
        while True:
            x, y = pag.position()
            win = detect_window(pag, title_substr="BTFViewer", prev=prev)
            prev = win
            left, top, width, height = win
            if width > 0 and height > 0:
                fx = (x - left) / width
                fy = (y - top) / height
                print(
                    f"\r  screen=({x}, {y})  win={win}  frac=({fx:.3f}, {fy:.3f})   ",
                    end="",
                    flush=True,
                )
            else:
                print(f"\r  mouse=({x}, {y})   ", end="", flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="XML-driven GUI demo runner (PyAutoGUI + TTS)",
    )
    ap.add_argument(
        "xml",
        type=Path,
        nargs="?",
        default=BTF_ROOT / "demos" / "demo_8cores" / "demo_8cores.xml",
        help="demo description XML (default: demos/demo_8cores/demo_8cores.xml)",
    )
    ap.add_argument("--launch", action="store_true", help="start app from <meta>/<launch> or <trace>")
    ap.add_argument("--attach-wait", type=float, default=4.0, help="wait after launch")
    ap.add_argument("--win", type=parse_win, default=None,
                    help="fixed window L,T,W,H (skips auto-detect of the app window)")
    ap.add_argument(
        "--window-title",
        default="BTFViewer",
        help="title substring used when auto-detecting the app window",
    )
    ap.add_argument(
        "--audio-block",
        action="store_true",
        help="wait for each <audio> before the next action (default: play while UI runs)",
    )
    ap.add_argument("--steps", type=str, default="all", help="step ids, e.g. 1-5,12 or all")
    ap.add_argument("--pause", type=float, default=None, help="override defaults.pause")
    ap.add_argument("--after-voice", type=float, default=None)
    ap.add_argument("--ai-wait", type=float, default=None)
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--no-tts", action="store_true", help="skip <voice> TTS (still logs text)")
    ap.add_argument("--no-audio", action="store_true", help="skip <audio>/<play> clips")
    ap.add_argument("--tts-cmd", default=None,
                    help='TTS command prefix; text appended as one arg (e.g. "say -r 170")')
    ap.add_argument(
        "--audio-cmd",
        default=None,
        help='Audio player prefix; file path appended (e.g. "afplay" or "ffplay -nodisp -autoexit")',
    )
    ap.add_argument("--tts-rate", type=int, default=170)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--short", action="store_true", help="skip steps marked optional=\"true\"")
    ap.add_argument(
        "--skip-tags",
        default="",
        help="comma-separated tags to skip (e.g. ai,optional)",
    )
    ap.add_argument("--var", action="append", default=[], metavar="NAME=VALUE",
                    help="override/extra ${NAME} variable")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--countdown", type=float, default=3.0)
    ap.add_argument(
        "--demo-api-port",
        type=int,
        default=int(os.environ.get("BTFVIEWER_DEMO_API_PORT") or "8765"),
        help="viewer demo HTTP API port (default 8765)",
    )
    ap.add_argument(
        "--no-demo-api",
        action="store_true",
        help="do not enable/use the viewer demo HTTP API",
    )
    args = ap.parse_args(argv)

    xml_path = args.xml.resolve()
    if not xml_path.is_file():
        log(f"XML not found: {xml_path}")
        return 2

    pag = _import_pyautogui()
    if args.calibrate:
        calibrate(pag)
        return 0

    root = load_demo_xml(xml_path)
    extras: Dict[str, str] = {}
    for item in args.var:
        if "=" not in item:
            raise SystemExit(f"--var expects NAME=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        extras[k.strip()] = v
    variables = build_variables(root, xml_path, extras)
    defaults = parse_defaults(root)
    if args.pause is not None:
        defaults["pause"] = args.pause
    if args.after_voice is not None:
        defaults["after_voice"] = args.after_voice
    if args.ai_wait is not None:
        defaults["ai_wait"] = args.ai_wait

    skip_tags = {t.strip() for t in args.skip_tags.split(",") if t.strip()}
    if args.short:
        # short mode also skips tag "long"
        skip_tags.add("long")

    audio_block = bool(defaults.get("audio_block", 0.0)) or args.audio_block
    win_fixed = args.win
    demo_api_enabled = not args.no_demo_api
    demo_api_url = f"http://127.0.0.1:{int(args.demo_api_port)}/demo"
    # Initial guess; refreshed after launch / focus against the real app window.
    win0 = win_fixed or detect_window(pag, title_substr=args.window_title)
    cfg = RunnerConfig(
        win=win0,
        targets=parse_targets(root),
        macros=parse_macros(root),
        vars=variables,
        defaults=defaults,
        pause=defaults["pause"],
        after_voice=defaults["after_voice"],
        ai_wait=defaults["ai_wait"],
        interactive=args.interactive,
        no_tts=args.no_tts,
        no_audio=args.no_audio,
        tts_cmd=args.tts_cmd,
        audio_cmd=args.audio_cmd,
        tts_rate=args.tts_rate,
        dry_run=args.dry_run,
        skip_optional=args.short,
        skip_tags=skip_tags,
        audio_block=audio_block,
        window_title=args.window_title,
        win_fixed=win_fixed,
        pag=pag,
        demo_api_url=demo_api_url,
        demo_api_enabled=demo_api_enabled,
    )

    name = root.attrib.get("name", xml_path.stem)
    log(f"demo={name!r}  xml={xml_path}")
    log(
        f"window L,T,W,H={cfg.win}  platform={platform.system()}  mod={MOD}  "
        f"audio_block={cfg.audio_block}  demo_api={cfg.demo_api_url if demo_api_enabled else 'off'}"
    )
    log("FAILSAFE: move mouse to a screen corner to abort.")
    log("coords: <targets> x/y are fractions of the detected app window")

    proc: Optional[subprocess.Popen] = None
    try:
        if args.launch:
            proc = launch_from_meta(
                root,
                variables,
                demo_api=demo_api_enabled,
                demo_api_port=args.demo_api_port,
            )
            if proc is None:
                log("no <launch>/<trace> in XML; continuing without launch")
            else:
                time.sleep(0 if cfg.dry_run else args.attach_wait)
                focus_pid(proc.pid)
                cfg.viewer_pid = proc.pid
                if not cfg.dry_run:
                    time.sleep(0.4)
                    cfg.win = detect_window(
                        pag,
                        pid=proc.pid,
                        title_substr=cfg.window_title,
                        prev=cfg.win if _is_plausible_window(cfg.win) else None,
                    )
                    if cfg.win_fixed is None:
                        log(f"window (after launch) L,T,W,H={cfg.win}")
        else:
            log("Assuming the target app is already open.")
            if args.interactive or cfg.dry_run:
                DemoRunner(pag, cfg).confirm("Focus the target window now")
            if not cfg.dry_run and cfg.win_fixed is None:
                cfg.win = detect_window(
                    pag,
                    title_substr=cfg.window_title,
                    prev=cfg.win if _is_plausible_window(cfg.win) else None,
                )
                log(f"window (frontmost/title) L,T,W,H={cfg.win}")

        if args.countdown > 0 and not cfg.dry_run:
            for i in range(int(args.countdown), 0, -1):
                log(f"starting in {i}…")
                time.sleep(1)

        runner = DemoRunner(pag, cfg, viewer_pid=proc.pid if proc else cfg.viewer_pid)
        if not cfg.dry_run:
            runner.refresh_window(force=True)
            if demo_api_enabled:
                runner.wait_demo_api(timeout=max(8.0, args.attach_wait + 10.0))
        want = parse_steps(args.steps)
        steps_el = root.find("steps")
        if steps_el is None:
            raise SystemExit("XML missing <steps>")

        def _step_wanted(sid: str) -> bool:
            if want is None:
                return True
            norm = {w.lstrip("0") or "0" for w in want}
            sid_n = sid.lstrip("0") or "0"
            return sid in want or sid_n in norm

        for step in steps_el.findall("step"):
            sid = step.attrib.get("id", "")
            if not _step_wanted(sid):
                continue
            try:
                runner.run_step(step)
            except Exception as exc:
                log(f"step {sid} error: {exc}")
                if cfg.interactive:
                    runner.confirm("Continue after error?")
                else:
                    raise
        log("demo finished")
        return 0
    except KeyboardInterrupt:
        log("aborted")
        return 130
    finally:
        if proc and proc.poll() is not None:
            log(f"app exited with code {proc.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
