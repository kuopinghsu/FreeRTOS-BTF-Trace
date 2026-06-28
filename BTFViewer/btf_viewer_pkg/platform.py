"""BTF Viewer — platform module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401

_STDERR_NOISE_MACOS: tuple = (
    b"TSM AdjustCapsLockLED",
    b"NSSoftLinking",
    b"HIToolbox framework",
)

def _macos_stderr_line_is_noise(line: bytes) -> bool:
    return any(p in line for p in _STDERR_NOISE_MACOS)

def _install_macos_stderr_filter() -> None:
    if sys.platform != "darwin":
        return
    if os.environ.get("BTF_NO_STDERR_FILTER"):
        return
    try:
        rfd, wfd = os.pipe()
    except OSError:
        return  # Can't create pipe; skip filter
    original_fd = os.dup(2)
    try:
        os.dup2(wfd, 2)
    except OSError:
        os.close(rfd)
        os.close(wfd)
        os.close(original_fd)
        return  # Restore fd 2 unchanged
    os.close(wfd)

    def _relay() -> None:
        leftover = b""
        try:
            with os.fdopen(rfd, "rb", buffering=0) as pipe:
                while True:
                    chunk = pipe.read(256)
                    if not chunk:
                        break
                    leftover += chunk
                    while b"\n" in leftover:
                        line, leftover = leftover.split(b"\n", 1)
                        if not _macos_stderr_line_is_noise(line):
                            try:
                                os.write(original_fd, line + b"\n")
                            except OSError:
                                pass
            if leftover and not _macos_stderr_line_is_noise(leftover):
                try:
                    os.write(original_fd, leftover)
                except OSError:
                    pass
        finally:
            try:
                os.close(original_fd)
            except OSError:
                pass

    t = threading.Thread(target=_relay, daemon=True, name="stderr-filter")
    t.start()
_XCB_CURSOR_SONAME = "libxcb-cursor.so.0"

def _find_xcb_cursor_lib() -> str:
    """Return a loadable path/soname for libxcb-cursor.so.0, or "" if absent.

    Search order (broadest first):
      1. ldconfig cache  — ctypes.util.find_library()
      2. LD_LIBRARY_PATH dirs — explicit file-existence scan
      3. Dynamic linker trial — ctypes.CDLL() (catches RPATH / other tricks)
    """
    import ctypes.util

    SONAME = _XCB_CURSOR_SONAME

    # 1. ldconfig cache
    if ctypes.util.find_library("xcb-cursor"):
        return SONAME

    # 2. LD_LIBRARY_PATH explicit scan — returns full path so caller can use it
    for d in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
        if not d:
            continue
        candidate = os.path.join(d, SONAME)
        if os.path.isfile(candidate):
            return candidate

    # 3. Dynamic-linker trial (last resort)
    import ctypes
    try:
        lib = ctypes.CDLL(SONAME)
        return lib._name or SONAME
    except OSError:
        pass

    return ""

def _platform_preflight() -> None:
    """Ensure libxcb-cursor.so.0 is available before QApplication loads the
    xcb platform plugin.

    The xcb plugin (Qt ≥ 6.5) requires libxcb-cursor at link time.  When the
    library lives outside the ldconfig cache (e.g. in $HOME/.local/lib via
    LD_LIBRARY_PATH) Qt's internal dlopen() may still fail even though the
    dynamic linker can find it — because Qt's plugin loader sometimes runs
    before the process environment is fully propagated to glibc's dl cache.

    Solution: pre-load the library into the process with RTLD_GLOBAL *before*
    QApplication() is called.  This puts all xcb-cursor symbols into the
    global namespace so the xcb plugin can resolve them unconditionally.

    This function is a no-op on non-Linux platforms; xcb is a Linux-only Qt
    platform plugin and libxcb-cursor does not exist on Windows or macOS.
    """
    if sys.platform != "linux":
        return
    if os.environ.get("QT_QPA_PLATFORM", "xcb") != "xcb":
        return

    lib_path = _find_xcb_cursor_lib()

    if lib_path:
        import ctypes
        # Pre-load with RTLD_GLOBAL: symbols become visible to every subsequent
        # dlopen() in this process, including Qt's xcb platform plugin loader.
        load_path = lib_path if os.sep in lib_path else _XCB_CURSOR_SONAME
        try:
            ctypes.CDLL(load_path, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            # Already loaded or path changed — try the bare soname as fallback
            try:
                ctypes.CDLL(_XCB_CURSOR_SONAME, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
        # Also keep LD_LIBRARY_PATH consistent so child processes benefit too
        if os.sep in lib_path:
            lib_dir = os.path.dirname(os.path.abspath(lib_path))
            parts = [p for p in os.environ.get("LD_LIBRARY_PATH", "").split(":") if p]
            if lib_dir not in parts:
                os.environ["LD_LIBRARY_PATH"] = ":".join([lib_dir] + parts)
        return

    print(
        "WARNING: The Qt xcb platform plugin requires libxcb-cursor0,\n"
        "  which was not found on this system.\n"
        "  Fix options:\n"
        "    1) Install the missing library:\n"
        "         sudo apt install libxcb-cursor0        # Debian / Ubuntu\n"
        "         sudo dnf install xcb-util-cursor       # Fedora / RHEL\n"
        "         sudo pacman -S xcb-util-cursor         # Arch\n"
        "    2) Copy libxcb-cursor.so.0 to a local dir and launch with:\n"
        "         LD_LIBRARY_PATH=/path/to/dir python btf_viewer.py\n"
        "    3) Use an alternative platform plugin:\n"
        "         QT_QPA_PLATFORM=offscreen python btf_viewer.py",
        file=sys.stderr,
    )

def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="ignore") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False

def _windows_applied_dpi() -> int | None:
    """Return the Windows user DPI (e.g. 144 @ 150 %, 192 @ 200 %) from WSL."""
    if not _is_wsl() or not shutil.which("powershell.exe"):
        return None
    try:
        out = subprocess.check_output(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "(Get-ItemProperty 'HKCU:\\Control Panel\\Desktop\\WindowMetrics' "
                "-ErrorAction SilentlyContinue).AppliedDPI",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
        dpi = int(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return dpi if dpi >= 96 else None

def _wsl_wayland_force_dpi(applied: int) -> int:
    """Partial DPI nudge for WSLg — wl_output scale already reflects Windows zoom.

    Using the full Windows AppliedDPI doubles up with native DPR (UI too large).
    Apply only ~25 % of the gap above 96 DPI (120 @ 200 %, 108 @ 150 %).
    """
    if applied <= 96:
        return 96
    return 96 + (applied - 96) // 4

def _configure_wsl_wayland_dpi() -> None:
    """WSLg + Qt Wayland: slight DPI nudge when UI renders too small.

    WSLg exposes wl_output scale matching Windows zoom, but Qt Wayland clients
    can still look undersized. Do not re-apply the full Windows DPI — that
    doubles with native scale. Override with QT_WAYLAND_FORCE_DPI; disable
    auto-tuning with BTF_WSL_DPI=0.
    """
    if not _is_wsl() or sys.platform != "linux":
        return
    if os.environ.get("BTF_WSL_DPI", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    plat = os.environ.get("QT_QPA_PLATFORM", "wayland").strip().lower()
    if plat not in ("", "wayland", "wayland-egl", "wayland-brcm"):
        return
    if os.environ.get("QT_WAYLAND_FORCE_DPI"):
        return
    applied = _windows_applied_dpi()
    if applied:
        os.environ["QT_WAYLAND_FORCE_DPI"] = str(_wsl_wayland_force_dpi(applied))

def _configure_qt_startup() -> None:
    # QT_FONT_DPI=96 was a PyQt5 workaround. Qt6 applies per-monitor DPI scaling
    # natively; forcing 96 DPI makes application fonts too small on Windows HiDPI.
    if sys.platform in ("win32", "linux"):
        os.environ.pop("QT_FONT_DPI", None)

    _configure_wsl_wayland_dpi()

    # macOS aborts inside _RegisterApplication when a headless QPA platform is
    # active (common when QT_QPA_PLATFORM=offscreen leaks from CI/IDE shells).
    if sys.platform == "darwin":
        plat = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        if plat in ("offscreen", "minimal", "vnc"):
            del os.environ["QT_QPA_PLATFORM"]

def _bootstrap_qt_app(argv: list[str] | None = None) -> QApplication:
    """Create or return QApplication with viewer font/bootstrap applied."""
    _configure_qt_startup()
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv if argv is not None else [])
    app.setFont(_application_ui_font(UI_FONT_SIZE))
    return app

