#!/usr/bin/env python3
"""Play one audio file to completion (helper for the in-app demo tour).

Prefer order (first that works):
  1. Windows: stdlib ``ctypes`` + ``winmm`` MCI (no pip; MP3/WAV)
  2. Optional ``pygame`` if installed
  3. macOS ``afplay`` / Linux ``ffplay`` / ``paplay``

Designed so demo narration works on Python 3.14 Windows without compiling
native wheels (pygame has no 3.14 win wheel yet).
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


def _ignore_sigint() -> None:
    """Parent owns Ctrl-C; do not dump a traceback from afplay wait."""
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass


def _stop_proc(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=0.6)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _play_windows_mci(path: Path) -> None:
    """Block until the clip finishes using the multimedia API (no Media Player UI)."""
    import ctypes
    from ctypes import wintypes

    winmm = ctypes.WinDLL("winmm")
    mci = winmm.mciSendStringW
    mci.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.UINT,
        wintypes.HANDLE,
    ]
    mci.restype = wintypes.UINT

    buf = ctypes.create_unicode_buffer(512)
    alias = f"btfdemo{os.getpid()}"
    # Quotes required for spaces in path; MCI accepts type mpegvideo for mp3.
    open_cmds = (
        f'open "{path}" type mpegvideo alias {alias}',
        f'open "{path}" alias {alias}',
    )
    opened = False
    last_rc = 0
    for cmd in open_cmds:
        last_rc = int(mci(cmd, buf, len(buf), None))
        if last_rc == 0:
            opened = True
            break
    if not opened:
        raise RuntimeError(f"mci open failed ({last_rc}): {path}")

    try:
        rc = int(mci(f"play {alias} wait", buf, len(buf), None))
        if rc != 0:
            raise RuntimeError(f"mci play failed ({rc}): {path}")
    finally:
        mci(f"close {alias}", buf, len(buf), None)


def _play_pygame(path: Path) -> None:
    import pygame

    pygame.display.init()
    try:
        pygame.display.set_mode((1, 1), flags=pygame.HIDDEN)
    except Exception:
        pass
    pygame.mixer.init()
    try:
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        clock = pygame.time.Clock()
        while pygame.mixer.music.get_busy():
            clock.tick(25)
    finally:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        try:
            pygame.display.quit()
        except Exception:
            pass


def _play_external(path: Path, cmd: list[str]) -> None:
    proc = subprocess.Popen(cmd)
    try:
        proc.wait()
    except KeyboardInterrupt:
        _stop_proc(proc)
        raise
    finally:
        _stop_proc(proc)


def play_file(path: Path) -> None:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    errors: list[str] = []

    if sys.platform == "win32":
        try:
            _play_windows_mci(path)
            return
        except Exception as exc:
            errors.append(f"winmm/mci: {exc}")

    try:
        import pygame  # noqa: F401

        _play_pygame(path)
        return
    except ImportError:
        errors.append("pygame not installed")
    except Exception as exc:
        errors.append(f"pygame: {exc}")

    if sys.platform == "darwin" and shutil.which("afplay"):
        _play_external(path, ["afplay", str(path)])
        return
    if shutil.which("ffplay"):
        _play_external(
            path,
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        )
        return
    if shutil.which("paplay"):
        _play_external(path, ["paplay", str(path)])
        return
    if shutil.which("aplay") and path.suffix.lower() in (".wav", ".wave"):
        _play_external(path, ["aplay", "-q", str(path)])
        return

    tip = (
        "No lightweight player worked.\n"
        "  Windows: winmm MCI should work with stdlib only — see errors below.\n"
        "  Optional: python -m pip install pygame  (needs a wheel for your Python)\n"
        "  Or: install ffplay\n"
    )
    raise RuntimeError(tip + "\n".join(f"  - {e}" for e in errors))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: play_audio_clip.py FILE", file=sys.stderr)
        return 2
    _ignore_sigint()
    path = Path(args[0])
    try:
        play_file(path)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
