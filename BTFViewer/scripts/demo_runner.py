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
``highlight``, ``clear_highlight``, ``cursors``, ``clear_cursors``,
``clear_bookmarks``, ``clear_annotations``, ``zoom_range``,
``fit_view``, ``zoom_1to1``, ``stats_section``, ``stats_reset``, ``limit``, ``jump_wcet``, ``panel``,
``view_mode``, ``cpu_load``, ``analysis``, ``tick_dist``, ``find``, ``settings``, ``ui``, ``demo_api``,
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
    <clear_bookmarks/>
    <clear_annotations/>
    <clear_highlight/>
    <fit_view/>
    <zoom_1to1/>
    <panel name="stats"/>
    <view_mode mode="core"/>
    <cpu_load on="true"/>
    <analysis/>
    <analysis close="true"/>
    <tick_dist/>
    <tick_dist close="true"/>
    <find query="CS[27]"/>
    <find clear="true"/>
    <settings page="AI"/>
    <settings close="true"/>

``--launch`` sets ``BTFVIEWER_DEMO_API=1`` automatically. Override with
``--demo-api-port`` / ``--no-demo-api``. When launching, if the preferred port
cannot be bound (common under WSL mirrored networking), the runner picks a
free localhost port and passes it to the viewer.

Audio files (pre-recorded narration)::

    <audio file="${XML_DIR}/voice/01_title.mp3"/>
    <!-- default: non-blocking — UI actions run while the clip plays;
         step end waits for the clip. Use block="true" or --audio-block to wait. -->
    <audio file="beep.wav" block="false"/>
    <wait_audio/>
    <stop_audio/>

Language: every language uses the same folders ``text/<lang>/`` and
``voice/<lang>/`` (see ``scripts/demo_voice.py``). XML paths stay
``voice/<file>``; the resolver tries ``voice/<lang>/``, then flat ``voice/``,
then ``voice/<default>/``. Packs are ``voice.json`` + ``text/*.txt`` +
``voice/*.mp3``. Declare languages in ``<meta>`` or run ``demo_voice.py sync-xml``.

Window geometry: ``detect_window`` finds the BTFViewer window (pid / title /
frontmost), preferring the **largest** on-screen window for that process so
dialogs do not steal coordinates. ``<targets>`` and ``x``/``y`` are
**fractions of that window** (0..1), refreshed on each ``<focus/>`` and before
clicks. If re-detect fails, the last good box is kept (never silently replaced
with the full screen while a real windowed box is known). Override with
``--win L,T,W,H`` or ``--window-title``.

Players: ``scripts/play_audio_clip.py`` (Windows: stdlib ``winmm``/MCI — no
pip; optional pygame; else ``afplay``/``ffplay``). Override with
``--audio-cmd 'ffplay -nodisp -autoexit'``.

Move the mouse to a **screen corner** to abort (PyAutoGUI FAILSAFE).
Press **Ctrl-C twice** to exit the runner (first press warns).

On **WSL/WSLg**, the visible cursor is Windows-owned; X11 mouse injection does
not move it. The runner automatically drives the Windows host cursor via
PowerShell when ``powershell.exe`` is available.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
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

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from demo_voice import (  # noqa: E402
    discover_voice_langs,
    merge_voice_langs,
    normalize_voice_lang,
    pick_voice_lang,
    voice_path_candidates,
)

MOD = "command" if sys.platform == "darwin" else "ctrl"


# ---------------------------------------------------------------------------
# Logging / TTS / input
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[demo] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Ctrl-C: first press warns, second press (within the window) exits
# ---------------------------------------------------------------------------

CTRL_C_EXIT_WINDOW_S = 2.5


class DoubleCtrlC:
    """Require two SIGINT presses before aborting the demo."""

    def __init__(self, window_s: float = CTRL_C_EXIT_WINDOW_S) -> None:
        self.window_s = float(window_s)
        self.exit_requested = False
        self._armed_at = 0.0
        self._prev = None

    def install(self) -> None:
        self._prev = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._on_sigint)

    def restore(self) -> None:
        if self._prev is not None:
            signal.signal(signal.SIGINT, self._prev)
            self._prev = None

    def _on_sigint(self, signum, frame) -> None:  # noqa: ARG002
        now = time.monotonic()
        if self._armed_at and (now - self._armed_at) <= self.window_s:
            self.exit_requested = True
            raise KeyboardInterrupt
        self._armed_at = now
        log("Ctrl-C: press again to exit the demo")

    def check(self) -> None:
        if self.exit_requested:
            raise KeyboardInterrupt


_interrupt: Optional[DoubleCtrlC] = None


def _check_interrupt() -> None:
    hook = _interrupt
    if hook is not None:
        hook.check()


def interruptible_sleep(seconds: float) -> None:
    """Sleep that notices Ctrl-C (first press returns early; second raises)."""
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        _check_interrupt()
        remain = deadline - time.monotonic()
        if remain <= 0:
            return
        time.sleep(min(0.2, remain))


def shutil_which(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def split_cmdline(cmd: str) -> List[str]:
    """Split a shell-like command string without mangling Windows paths.

    POSIX ``shlex`` treats ``\\`` as an escape, so
    ``C:\\Users\\...\\python.exe`` becomes ``C:Users...python.exe``.
    Use MS-Windows rules on ``nt``.
    """
    return shlex.split(cmd, posix=(os.name != "nt"))


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
        subprocess.run(split_cmdline(tts_cmd) + [text], check=False)
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


def preferred_voice_lang(variables: Optional[Dict[str, str]] = None) -> str:
    """Explicit demo language only — not the process locale.

    Order: ``VOICE_LANG`` / ``LANG`` extras, then ``BTFVIEWER_DEMO_LANG``.
    Empty means the XML ``<languages default>`` (English for demo_8cores).
    """
    vars_ = variables or {}
    for cand in (
        vars_.get("VOICE_LANG"),
        vars_.get("LANG"),
        os.environ.get("BTFVIEWER_DEMO_LANG"),
    ):
        if cand and str(cand).strip():
            return str(cand).strip()
    return ""


def resolve_media_path(raw: str, variables: Dict[str, str]) -> Path:
    """Resolve an audio/media path with ${vars} and search XML_DIR / CWD / BTF.

    If the exact path is missing, try common audio extensions and sibling
    ``voice/`` / ``text/`` folders (per-demo layout). Language-specific clips
    under ``voice/<lang>/`` are preferred when ``LANG`` / ``VOICE_LANG`` is set.
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
    lang = variables.get("LANG") or variables.get("VOICE_LANG") or ""
    default_lang = variables.get("VOICE_DEFAULT") or "en"
    roots = voice_path_candidates(p, lang, default_lang) or [p]

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
        exts = (".mp3", ".aac", ".wav", ".m4a", ".aiff", ".aif", ".ogg", ".flac")
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
    for rootp in roots:
        if rootp.is_absolute():
            search.extend(_candidates(rootp))
        else:
            for base in bases:
                search.extend(_candidates((base / rootp)))
            search.extend(_candidates(rootp))

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


def _python_audio_command(path: Path) -> Optional[List[str]]:
    """Play via ``scripts/play_audio_clip.py`` (stdlib MCI on Windows; no pip)."""
    helper = SCRIPT_DIR / "play_audio_clip.py"
    if not helper.is_file():
        return None
    return [sys.executable, str(helper), str(path.resolve())]


def _windows_audio_command(path: Path) -> List[str]:
    """Last-resort Windows playback if the helper script is missing."""
    resolved = str(path.resolve())
    ps_path = resolved.replace("'", "''")
    suffix = path.suffix.lower()
    if suffix in (".wav", ".wave"):
        ps = (
            f"$p = New-Object System.Media.SoundPlayer -ArgumentList @('{ps_path}'); "
            "$p.PlaySync()"
        )
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]

    ps = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore
$mp = New-Object System.Windows.Media.MediaPlayer
try {{
  $full = (Resolve-Path -LiteralPath '{ps_path}').Path
  $mp.Open([Uri]::new($full))
  $deadline = [DateTime]::UtcNow.AddSeconds(10)
  while (-not $mp.NaturalDuration.HasTimeSpan) {{
    if ([DateTime]::UtcNow -gt $deadline) {{ throw "timeout opening audio: $full" }}
    Start-Sleep -Milliseconds 40
  }}
  $ms = [Math]::Max(1, [int][Math]::Ceiling($mp.NaturalDuration.TimeSpan.TotalMilliseconds))
  $mp.Volume = 1.0
  $mp.Play()
  Start-Sleep -Milliseconds $ms
}} finally {{
  try {{ $mp.Stop() }} catch {{}}
  try {{ $mp.Close() }} catch {{}}
}}
"""
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]


def _audio_command(path: Path, audio_cmd: Optional[str]) -> List[str]:
    if audio_cmd:
        return split_cmdline(audio_cmd) + [str(path)]
    # Prefer the Python helper: on Windows it uses stdlib winmm/MCI (no pygame).
    py_cmd = _python_audio_command(path)
    if py_cmd is not None:
        return py_cmd
    if sys.platform == "darwin" and shutil_which("afplay"):
        return ["afplay", str(path)]
    if shutil_which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    if shutil_which("paplay"):
        return ["paplay", str(path)]
    if shutil_which("aplay") and path.suffix.lower() in (".wav", ".wave"):
        return ["aplay", "-q", str(path)]
    if sys.platform == "win32":
        return _windows_audio_command(path)
    raise RuntimeError(
        f"No audio player found for {path}.\n"
        "  On Windows, scripts/play_audio_clip.py uses stdlib winmm (no pip).\n"
        "  Or install ffplay, or pass --audio-cmd 'ffplay -nodisp -autoexit'"
    )


def _popen_detached(cmd: List[str], **extra) -> subprocess.Popen:
    """Start a child outside the runner's Ctrl-C process group."""
    kwargs: Dict[str, Any] = dict(extra)
    if os.name == "nt":
        flags = int(kwargs.get("creationflags", 0) or 0)
        kwargs["creationflags"] = flags | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _stop_popen(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt" and proc.pid:
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=0.8)
    except Exception:
        try:
            if os.name != "nt" and proc.pid:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass


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
        proc = _popen_detached(cmd)
        try:
            while proc.poll() is None:
                _check_interrupt()
                try:
                    proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
        except KeyboardInterrupt:
            _stop_popen(proc)
            raise
        return None
    return _popen_detached(cmd)


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


def _ensure_xauthority() -> None:
    """Avoid Xlib crash when ~/.Xauthority is missing (common on WSL).

    python-xlib raises ``XauthError`` if ``XAUTHORITY`` / ``~/.Xauthority``
    does not exist, even when the X server allows unauthenticated local
    clients. Point at an empty private temp file instead of writing into
    ``$HOME``.
    """
    if sys.platform == "darwin" or os.name == "nt":
        return
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    configured = os.environ.get("XAUTHORITY")
    if configured and Path(configured).is_file():
        return
    home_auth = Path.home() / ".Xauthority"
    if home_auth.is_file():
        return
    tmp = Path(tempfile.gettempdir()) / f"btfviewer-xauth-{os.getuid()}"
    try:
        tmp.touch(exist_ok=True)
    except OSError:
        return
    os.environ["XAUTHORITY"] = str(tmp)


def _enable_windows_dpi_awareness() -> None:
    """Match PyAutoGUI coords to physical pixels (GetWindowRect / SetCursorPos)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _import_pyautogui():
    _ensure_xauthority()
    _enable_windows_dpi_awareness()
    try:
        import pyautogui
    except ImportError as exc:
        raise SystemExit(
            "pyautogui is required:\n"
            "  python3 -m pip install -r scripts/requirements-demo.txt\n"
            f"({exc})"
        ) from exc
    except Exception as exc:
        display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or "(unset)"
        raise SystemExit(
            "pyautogui could not open the display (needed for mouse/keyboard).\n"
            f"  DISPLAY/WAYLAND={display}\n"
            "  On WSL: enable WSLg or an X server, then retry `make -C BTFViewer demo`.\n"
            "  For a no-GUI check: python3 scripts/demo_runner.py "
            "demos/demo_8cores/demo_8cores.xml --dry-run\n"
            f"({type(exc).__name__}: {exc})"
        ) from exc
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.08
    if _is_wsl() and shutil_which("powershell.exe"):
        try:
            wrapped = _WslHostGui(pyautogui)
            log(
                "WSL/WSLg: mouse uses the Windows host cursor "
                "(X11 XTEST moves are invisible on the Windows desktop)"
            )
            return wrapped
        except Exception as exc:
            log(f"WSL host cursor unavailable ({exc}); falling back to X11 mouse")
    return pyautogui


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        return False


def _title_match_needles(title_substr: str) -> List[str]:
    """Expand ``BTFViewer`` ↔ ``BTF Viewer`` for WSLg ``msrdc`` window titles."""
    s = (title_substr or "").strip()
    if not s:
        return ["BTF Viewer"]
    out: List[str] = []
    for cand in (
        s,
        re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s),
        s.replace(" ", ""),
        "BTF Viewer" if "btf" in s.lower() else "",
    ):
        c = cand.strip()
        if c and c not in out:
            out.append(c)
    return out


class _WslHostGui:
    """PyAutoGUI-compatible wrapper: Windows cursor + keyboard via X11.

    Under WSLg the visible pointer is the Windows host cursor. PyAutoGUI's
    X11 ``XTEST`` moves only the XWayland pointer, so ``moveTo`` looks like a
    no-op. Drive mouse via ``user32`` through a persistent ``powershell.exe``.
    """

    _PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class BtfDemoInput {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  public struct POINT { public int X; public int Y; }
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
  public const uint MOUSEEVENTF_LEFTUP = 0x0004;
  public const uint MOUSEEVENTF_WHEEL = 0x0800;
}
"@
Add-Type -AssemblyName System.Windows.Forms
function Write-Ok([string]$s) { [Console]::Out.WriteLine($s); [Console]::Out.Flush() }
while (($line = [Console]::In.ReadLine()) -ne $null) {
  if ([string]::IsNullOrWhiteSpace($line)) { continue }
  $parts = $line.Split(' ', 2)
  $cmd = $parts[0].ToUpperInvariant()
  try {
    switch ($cmd) {
      'POS' {
        $p = New-Object BtfDemoInput+POINT
        [void][BtfDemoInput]::GetCursorPos([ref]$p)
        Write-Ok ("{0} {1}" -f $p.X, $p.Y)
      }
      'SIZE' {
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        Write-Ok ("{0} {1}" -f $b.Width, $b.Height)
      }
      'MOVE' {
        $xy = $parts[1].Split(' ')
        [void][BtfDemoInput]::SetCursorPos([int]$xy[0], [int]$xy[1])
        Write-Ok 'OK'
      }
      'CLICK' {
        $n = 1
        if ($parts.Length -gt 1 -and $parts[1].Trim() -ne '') { $n = [int]$parts[1].Trim() }
        for ($i = 0; $i -lt $n; $i++) {
          [BtfDemoInput]::mouse_event([BtfDemoInput]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
          [BtfDemoInput]::mouse_event([BtfDemoInput]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
        }
        Write-Ok 'OK'
      }
      'SCROLL' {
        $clicks = [int]$parts[1].Trim()
        [BtfDemoInput]::mouse_event([BtfDemoInput]::MOUSEEVENTF_WHEEL, 0, 0, [uint32]($clicks * 120), [UIntPtr]::Zero)
        Write-Ok 'OK'
      }
      'WIN' {
        $needle = if ($parts.Length -gt 1) { $parts[1].Trim() } else { 'BTF Viewer' }
        $needles = $needle.Split('|')
        $hit = $null
        foreach ($proc in Get-Process) {
          if ($proc.MainWindowHandle -eq 0) { continue }
          $title = $proc.MainWindowTitle
          if ([string]::IsNullOrWhiteSpace($title)) { continue }
          foreach ($n in $needles) {
            if ($n -and ($title -like ("*{0}*" -f $n))) { $hit = $proc; break }
          }
          if ($hit -ne $null) { break }
        }
        if ($hit -eq $null) { Write-Ok 'NONE'; continue }
        $r = New-Object BtfDemoInput+RECT
        [void][BtfDemoInput]::GetWindowRect($hit.MainWindowHandle, [ref]$r)
        $w = $r.Right - $r.Left
        $h = $r.Bottom - $r.Top
        Write-Ok ("{0} {1} {2} {3}" -f $r.Left, $r.Top, $w, $h)
      }
      'QUIT' { break }
      default { Write-Ok ('ERR unknown ' + $cmd) }
    }
  } catch {
    Write-Ok ('ERR ' + $_.Exception.Message)
  }
}
"""

    def __init__(self, pag: Any):
        self._pag = pag
        self.FAILSAFE = bool(getattr(pag, "FAILSAFE", True))
        self.PAUSE = float(getattr(pag, "PAUSE", 0.08))
        self._proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                self._PS_SCRIPT,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        # Probe — raises if powershell / user32 path is broken.
        self.size()

    def _ask(self, line: str) -> str:
        if self._proc.poll() is not None:
            raise RuntimeError("WSL host input helper exited")
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(line.rstrip() + "\n")
        self._proc.stdin.flush()
        out = self._proc.stdout.readline().strip()
        if out.startswith("ERR"):
            raise RuntimeError(out)
        return out

    def size(self) -> Any:
        from collections import namedtuple

        w, h = (int(x) for x in self._ask("SIZE").split())
        return namedtuple("Size", "width height")(w, h)

    def position(self) -> Any:
        from collections import namedtuple

        x, y = (int(v) for v in self._ask("POS").split())
        return namedtuple("Point", "x y")(x, y)

    def _failsafe_check(self, x: int, y: int) -> None:
        if not self.FAILSAFE:
            return
        try:
            sw, sh = int(self.size()[0]), int(self.size()[1])
        except Exception:
            return
        if x <= 0 or y <= 0 or x >= sw - 1 or y >= sh - 1:
            raise RuntimeError(
                "WSL mouse failsafe: target at screen edge "
                f"({x},{y}); move away from corners / disable FAILSAFE"
            )

    def moveTo(self, x: int, y: int, duration: float = 0.0) -> None:
        x, y = int(x), int(y)
        self._failsafe_check(x, y)
        dur = max(0.0, float(duration or 0.0))
        if dur <= 0.05:
            self._ask(f"MOVE {x} {y}")
        else:
            pos = self.position()
            x0, y0 = int(pos.x), int(pos.y)
            steps = max(2, int(dur / 0.02))
            for i in range(1, steps + 1):
                t = i / steps
                xi = int(x0 + (x - x0) * t)
                yi = int(y0 + (y - y0) * t)
                self._ask(f"MOVE {xi} {yi}")
                time.sleep(dur / steps)
        if self.PAUSE:
            time.sleep(self.PAUSE)

    def click(self, clicks: int = 1, **_kwargs: Any) -> None:
        self._ask(f"CLICK {max(1, int(clicks))}")
        if self.PAUSE:
            time.sleep(self.PAUSE)

    def scroll(self, clicks: int, *args: Any, **kwargs: Any) -> None:
        self._ask(f"SCROLL {int(clicks)}")
        if self.PAUSE:
            time.sleep(self.PAUSE)

    def window_bounds(self, title_substr: str) -> Optional[Tuple[int, int, int, int]]:
        needles = "|".join(_title_match_needles(title_substr))
        raw = self._ask(f"WIN {needles}")
        if raw == "NONE" or not raw:
            return None
        parts = [int(p) for p in raw.split()]
        if len(parts) != 4 or parts[2] < 200 or parts[3] < 200:
            return None
        return parts[0], parts[1], parts[2], parts[3]

    def close(self) -> None:
        try:
            if self._proc.poll() is None and self._proc.stdin:
                self._proc.stdin.write("QUIT\n")
                self._proc.stdin.flush()
                self._proc.terminate()
        except Exception:
            pass

    def hotkey(self, *args: Any, **kwargs: Any) -> None:
        return self._pag.hotkey(*args, **kwargs)

    def press(self, *args: Any, **kwargs: Any) -> None:
        return self._pag.press(*args, **kwargs)

    def write(self, *args: Any, **kwargs: Any) -> None:
        return self._pag.write(*args, **kwargs)

    def typewrite(self, *args: Any, **kwargs: Any) -> None:
        return self._pag.typewrite(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._pag, name)


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
    # WSLg: window lives on the Windows host (msrdc); prefer that rect so
    # fractional targets match the cursor we drive via user32.
    wsl_bounds = getattr(pag, "window_bounds", None)
    if callable(wsl_bounds):
        try:
            got = wsl_bounds(title_substr)
        except Exception:
            got = None
        if got:
            candidates.append(got)
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
        log(
            f"window detect fallback → full screen {w}x{h} "
            "(fractional targets will be wrong if the viewer is not maximized; "
            "pass --win L,T,W,H or ensure the window title contains 'BTF Viewer')"
        )
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
    if not pid and sys.platform != "win32":
        return
    if sys.platform == "darwin" and pid:
        script = (
            f'tell application "System Events"\n'
            f'  try\n'
            f'    set frontmost of (first process whose unix id is {int(pid)}) to true\n'
            f'  end try\n'
            f'end tell'
        )
        subprocess.run(["osascript", "-e", script], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if sys.platform == "win32":
        # Bring the viewer to the foreground so clicks land on it.
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
            )
            target = ctypes.c_void_p(0)

            def _cb(hwnd: int, _lparam: int) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = int(user32.GetWindowTextLengthW(hwnd)) + 1
                if length <= 1:
                    return True
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hwnd, buf, length)
                if not _window_title_matches(buf.value or "", "BTFViewer"):
                    return True
                if pid:
                    proc_id = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
                    if int(proc_id.value) != int(pid):
                        # Title match is enough when pid is a python launcher child.
                        pass
                target.value = hwnd
                return False  # stop enum

            user32.EnumWindows(EnumWindowsProc(_cb), 0)
            if target.value:
                user32.ShowWindow(target.value, 9)  # SW_RESTORE
                user32.SetForegroundWindow(target.value)
        except Exception:
            pass


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


def _window_title_matches(title: str, title_substr: str) -> bool:
    """True if *title* looks like the BTF Viewer (not IDE/terminal false hits)."""
    tl = (title or "").lower()
    if not tl:
        return False
    needles = [n.lower() for n in _title_match_needles(title_substr)]
    if not any(n and n in tl for n in needles):
        return False
    # Avoid matching Cursor/VS Code / Terminal paths that contain "BTF".
    deny = (
        "cursor",
        "visual studio",
        "code -",
        "windows terminal",
        "powershell",
        "cmd.exe",
        " - wsl",
    )
    if any(d in tl for d in deny) and "viewer" not in tl:
        return False
    return True


def _window_bounds_windows(
    *,
    title_substr: str = "BTFViewer",
) -> Optional[Tuple[int, int, int, int]]:
    """Return (left, top, width, height) for the largest matching Win32 window.

    Uses ``user32`` directly (no ``pygetwindow``). Matches ``BTFViewer`` and
    ``BTF Viewer`` / ``RTOS BTF Viewer`` titles. Coordinates are physical
    pixels when DPI awareness was enabled at startup.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    hits: List[Tuple[int, int, int, int, int]] = []  # score, L, T, W, H

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd)) + 1
        if length <= 1:
            return True
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value or ""
        if not _window_title_matches(title, title_substr):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = int(rect.right) - int(rect.left)
        height = int(rect.bottom) - int(rect.top)
        if width < 200 or height < 200:
            return True
        score = width * height
        if "viewer" in title.lower():
            score *= 10
        hits.append((score, int(rect.left), int(rect.top), width, height))
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(_cb), 0)
    except Exception:
        return None
    if not hits:
        # Fallback: pygetwindow if present (older installs).
        try:
            import pygetwindow as gw  # type: ignore
        except ImportError:
            return None
        try:
            for needle in _title_match_needles(title_substr):
                wins = [
                    w for w in (gw.getAllWindows() or [])
                    if w and _window_title_matches(w.title or "", needle)
                ]
                for w in wins:
                    width, height = int(w.width), int(w.height)
                    if width >= 200 and height >= 200:
                        hits.append(
                            (width * height, int(w.left), int(w.top), width, height)
                        )
        except Exception:
            return None
    if not hits:
        return None
    hits.sort(key=lambda t: t[0], reverse=True)
    _, left, top, width, height = hits[0]
    return left, top, width, height


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
            if child.tag in ("title", "description", "author", "languages"):
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


def parse_languages(root: ET.Element) -> Dict[str, Any]:
    wrap = root.find("languages")
    if wrap is None:
        meta = root.find("meta")
        if meta is not None:
            wrap = meta.find("languages")
    items: List[Dict[str, str]] = []
    default_id = "en"
    if wrap is not None:
        default_id = (
            normalize_voice_lang(
                wrap.attrib.get("default") or wrap.attrib.get("lang") or "en"
            )
            or "en"
        )
        for el in wrap.findall("language"):
            lang_id = normalize_voice_lang(
                el.attrib.get("id") or el.attrib.get("lang") or ""
            )
            if not lang_id:
                continue
            label = (
                el.attrib.get("label") or el.attrib.get("name") or lang_id
            ).strip() or lang_id
            if not any(x["id"] == lang_id for x in items):
                items.append({"id": lang_id, "label": label})
    if not items:
        items.append({"id": "en", "label": "English"})
    if not any(x["id"] == default_id for x in items):
        default_id = items[0]["id"]
    return {"defaultId": default_id, "list": items}


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
            if self.cfg.demo_api_enabled and not self.cfg.dry_run:
                try:
                    hit = self.demo_api({"op": "target", "name": name}, settle=0)
                    if isinstance(hit, dict) and "x" in hit and "y" in hit:
                        return int(hit["x"]), int(hit["y"])
                except Exception:
                    pass
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
        interruptible_sleep(max(0.0, seconds))

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
            while p.poll() is None:
                _check_interrupt()
                try:
                    p.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    break
        self.cfg.bg_audio.clear()

    def _stop_bg_audio(self) -> None:
        log(f"stop_audio ({len(self.cfg.bg_audio)})")
        if self.cfg.dry_run:
            self.cfg.bg_audio.clear()
            return
        for p in self.cfg.bg_audio:
            _stop_popen(p)
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
        except urllib.error.HTTPError as exc:
            detail = str(exc)
            try:
                raw = exc.read().decode("utf-8")
                parsed = json.loads(raw or "{}")
                detail = str(parsed.get("error") or raw or detail)
            except Exception:
                pass
            raise RuntimeError(
                f"demo API error at {self.cfg.demo_api_url}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"demo API unreachable at {self.cfg.demo_api_url}: {exc}\n"
                "Launch with BTFVIEWER_DEMO_API=1 (demo_runner --launch does this).\n"
                "If the viewer printed '[demo-api] failed to start', the port is "
                "blocked — rerun with --launch (auto-picks a free port) or "
                "--demo-api-port PORT."
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
            _check_interrupt()
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
            interruptible_sleep(0.4)
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
            elif tag == "clear_bookmarks":
                self.demo_api({"op": "clear_bookmarks"})
            elif tag == "clear_annotations":
                self.demo_api({"op": "clear_annotations"})
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
            elif tag in ("zoom_1to1", "one_to_one", "1to1"):
                self.demo_api({"op": "zoom_1to1"}, settle=0.4)
            elif tag in ("tick_dist", "tick_distribution"):
                close = "close" in el.attrib
                payload = {"op": "tick_dist"}
                if close:
                    payload["close"] = expand(el.attrib.get("close", "true"), self.cfg.vars)
                self.demo_api(payload, settle=0.4)
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
                payload = {"op": "settings"}
                for key in ("page", "name", "open", "close", "action"):
                    if key in el.attrib:
                        payload[key] = expand(el.attrib[key], self.cfg.vars)
                if "page" not in payload and "name" not in payload and "close" not in payload:
                    payload["page"] = "Appearance"
                settle = 0.5 if "close" not in el.attrib else 0.4
                self.demo_api(payload, settle=settle)
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
            _check_interrupt()
            if child.tag in ("title",):
                continue
            self.run_action(child)
        # Finish any overlapping narration before the next step.
        self._wait_bg_audio()
        self.wait(self.cfg.pause, "inter-step")


# ---------------------------------------------------------------------------
# Demo API port selection
# ---------------------------------------------------------------------------

def _localhost_port_bindable(port: int, host: str = "127.0.0.1") -> bool:
    """True if ``host:port`` can be bound exclusively for the demo API.

    Do not set ``SO_REUSEADDR`` here: with it, Linux can report a port as free
    while another process already has it bound (EADDRINUSE only appears later).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pick_free_demo_api_port(preferred: int = 8765, host: str = "127.0.0.1") -> int:
    """Return ``preferred`` if free, else another bindable localhost TCP port.

    Under WSL mirrored networking, Windows can reserve ports that never show up
    in Linux ``ss``/``netstat``; bind then fails with EADDRINUSE. Prefer the
    configured port, then nearby ports, then an OS-assigned ephemeral port.
    """
    preferred = int(preferred)
    candidates: List[int] = [preferred]
    for delta in range(1, 64):
        candidates.append(preferred + delta)
    for port in (18265, 18765, 19265, 28265, 28765, 38265):
        if port not in candidates:
            candidates.append(port)
    for port in candidates:
        if port <= 0 or port > 65535:
            continue
        if _localhost_port_bindable(port, host=host):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


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
        cmd = split_cmdline(cmd_s)
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
        # Prefer absolute python + viewer paths on Windows (CreateProcess clarity).
        if os.name == "nt" and len(cmd) >= 2:
            exe = Path(cmd[0])
            if not exe.is_file() and cmd[0].lower() in ("python", "python.exe", "py"):
                cmd[0] = sys.executable
            script = Path(cmd[1])
            if not script.is_file():
                alt = Path(cwd) / script
                if alt.is_file():
                    cmd[1] = str(alt)
            for i in range(2, len(cmd)):
                arg = Path(cmd[i])
                if arg.suffix.lower() in (".btf", ".gz", ".zip") and not arg.is_file():
                    alt = Path(cwd) / arg
                    if alt.is_file():
                        cmd[i] = str(alt)
    env = os.environ.copy()
    if demo_api:
        env["BTFVIEWER_DEMO_API"] = "1"
        env["BTFVIEWER_DEMO_API_PORT"] = str(int(demo_api_port))
    # Prefer XWayland over native Wayland so windowing matches demo tooling.
    if _is_wsl() and not env.get("QT_QPA_PLATFORM"):
        env["QT_QPA_PLATFORM"] = "xcb"
    log(f"launch: {' '.join(cmd)}  (cwd={cwd})")
    return _popen_detached(cmd, cwd=cwd, env=env)


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
        help="demo description XML or .xtf pack (default: demos/demo_8cores/demo_8cores.xml)",
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
    ap.add_argument(
        "--lang",
        default="",
        help="narration language id (en, zh-tw, …). Default: BTFVIEWER_DEMO_LANG, "
             "else the XML <languages default> (en). Clips: voice/<lang>/<file>, "
             "fallback voice/<file>.",
    )
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

    # Shareable .xtf packs are zip archives of xml + btf + voice/.
    _xtf_tmpdir = None
    if xml_path.suffix.lower() == ".xtf":
        import tempfile
        import zipfile
        if not zipfile.is_zipfile(xml_path):
            log(f"not a valid .xtf archive: {xml_path}")
            return 2
        _xtf_tmpdir = Path(tempfile.mkdtemp(prefix="btf_xtf_"))
        with zipfile.ZipFile(xml_path, "r") as zf:
            zf.extractall(_xtf_tmpdir)
        xmls = sorted(_xtf_tmpdir.glob("*.xml"))
        if not xmls:
            log(f"no .xml inside .xtf: {xml_path}")
            return 2
        demoish = [p for p in xmls if "demo" in p.name.lower()]
        xml_path = (demoish or xmls)[0]
        log(f"extracted .xtf → {xml_path}")

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
    langs = merge_voice_langs(
        parse_languages(root),
        discover_voice_langs(Path(variables.get("XML_DIR", str(xml_path.parent)))),
    )
    picked_lang = pick_voice_lang(
        (args.lang or "").strip() or preferred_voice_lang(variables),
        [item["id"] for item in langs["list"]],
        langs["defaultId"],
    )
    variables["LANG"] = picked_lang
    variables["VOICE_LANG"] = picked_lang
    variables["VOICE_DEFAULT"] = langs["defaultId"]
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
    demo_api_port = int(args.demo_api_port)
    if demo_api_enabled and args.launch and not args.dry_run:
        chosen = pick_free_demo_api_port(demo_api_port)
        if chosen != demo_api_port:
            log(
                f"demo API port {demo_api_port} unavailable; using {chosen} "
                "(WSL/Windows often reserves ports that Linux ss does not show)"
            )
        demo_api_port = chosen
    demo_api_url = f"http://127.0.0.1:{demo_api_port}/demo"
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
        f"audio_block={cfg.audio_block}  voice={picked_lang}  "
        f"demo_api={cfg.demo_api_url if demo_api_enabled else 'off'}"
    )
    log("FAILSAFE: move mouse to a screen corner to abort.")
    log("Ctrl-C twice to exit the demo.")
    log("coords: <targets> x/y are fractions of the detected app window")

    proc: Optional[subprocess.Popen] = None
    runner: Optional[DemoRunner] = None
    hook = DoubleCtrlC()
    global _interrupt
    _interrupt = hook
    hook.install()
    try:
        if args.launch:
            proc = launch_from_meta(
                root,
                variables,
                demo_api=demo_api_enabled,
                demo_api_port=demo_api_port,
            )
            if proc is None:
                log("no <launch>/<trace> in XML; continuing without launch")
            else:
                interruptible_sleep(0 if cfg.dry_run else args.attach_wait)
                focus_pid(proc.pid)
                cfg.viewer_pid = proc.pid
                if not cfg.dry_run:
                    interruptible_sleep(0.4)
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
                interruptible_sleep(1)

        runner = DemoRunner(pag, cfg, viewer_pid=proc.pid if proc else cfg.viewer_pid)
        if not cfg.dry_run:
            runner.refresh_window(force=True)
            if demo_api_enabled:
                ready = runner.wait_demo_api(
                    timeout=max(8.0, args.attach_wait + 10.0))
                if not ready:
                    raise SystemExit(
                        f"demo API not ready at {cfg.demo_api_url}\n"
                        "Check the viewer console for '[demo-api] failed to start' "
                        "(port blocked) or launch without --no-demo-api."
                    )
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
            _check_interrupt()
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
        if runner is not None:
            try:
                runner._stop_bg_audio()
            except Exception:
                pass
        return 0
    finally:
        hook.restore()
        _interrupt = None
        if proc and proc.poll() is not None:
            log(f"app exited with code {proc.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
