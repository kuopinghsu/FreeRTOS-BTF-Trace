#!/usr/bin/env python3
"""Merge btf_viewer_pkg/ into a single runnable btf_viewer.py for release.

Usage (from BTFViewer/):
    python3 scripts/bundle_viewer.py -o btf_viewer.py
"""
from __future__ import annotations

import argparse
import ast
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "btf_viewer_pkg"
DEFAULT_OUT = ROOT / "builds" / "btf_viewer.py"
MONOLITH = ROOT / "builds" / "btf_viewer.py"

SHEBANG = "#!/usr/bin/env python\n"
GENERATED_BANNER = (
    "# GENERATED — do not edit; edit btf_viewer_pkg/ and run: make -C BTFViewer bundle\n"
)

# Monolith section order for the bundled single file.
BUNDLE_MODULES: list[str] = [
    "config",
    "parser",
    "btf_slice",
    "timeline_util",
    "scene",
    "graphics_items",
    "view",
    "ai_investigation",
    "ai_tools",
    "ai_mermaid",
    "ai_assistant",
    "stats",
    "mvvm/base",
    "mvvm/models",
    "mvvm/app_settings",
    "mvvm/stats_vm",
    "mvvm/find_logic",
    "mvvm/tab_viewport",
    "mvvm/trace_tab_vm",
    "mvvm/main_vm",
    "mvvm/bindings",
    "mvvm/__init__",
    "trace_quality",
    "perfetto_export",
    "mainwindow",
    "platform",
    "cli",
]

SECTION_MARKERS: dict[str, str] = {
    "config": "# USER CONFIGURATION",
    "parser": "# BTF Parser",
    "timeline_util": "# Timeline Widget",
    "scene": "# Scene",
    "graphics_items": "# Custom graphics items",
    "view": "# Navigator Popup",
    "ai_assistant": "# AI Assistant (Ollama)",
    "stats": "# Main Window",
    "mvvm/base": "# MVVM",
    "trace_quality": "# Trace quality metadata",
    "perfetto_export": "# Perfetto export",
    "mainwindow": "# CPU Load Graph",
    "platform": "# Entry point",
    "cli": "# Entry point",
}

MACOS_STDERR_HEADER = """\
# ---------------------------------------------------------------------------
# macOS: suppress harmless TSM / HIToolbox stderr noise that macOS prints
# whenever keys or menus are used in a Qt app (CapsLock LED, NSSoftLinking, …).
# Installed from main() after QApplication() — redirecting stderr before Qt
# initialises NSApplication can abort inside _RegisterApplication on macOS.
# ---------------------------------------------------------------------------
"""

# Canonical shared imports (merged from monolith header).
SHARED_IMPORTS = """\
import os
import sys
import threading

import argparse
import base64
import configparser
import csv
import datetime
import functools
import hashlib
import html
from html.parser import HTMLParser
import ssl
import itertools
import json
import math
import time
import re
import shutil
import subprocess
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zlib
import gzip
import bz2
import zipfile
import io
from contextlib import contextmanager
from bisect import bisect_left, bisect_right
from collections import defaultdict
from operator import attrgetter as _attrgetter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QBuffer, QByteArray, QEasingCurve, QEvent, QEventLoop, QIODevice, QLineF, QMimeData,
    QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, QUrl,
    QPropertyAnimation, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QIcon, QImage, QKeySequence, QLinearGradient, QPainter,
    QPainterPath, QPainterPathStroker, QPalette, QPen, QPixmap, QPolygonF, QShortcut, QTransform, QWheelEvent,
)
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGridLayout, QInputDialog,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsOpacityEffect,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog,
    QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QScrollBar, QDoubleSpinBox, QSpinBox, QStackedWidget,
    QStyle, QStyleFactory, QStyleOptionGraphicsItem, QAbstractItemView,
    QProxyStyle, QStyledItemDelegate, QTabBar, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton, QToolTip,
    QPlainTextEdit, QTextBrowser,
    QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy, QSplitter, QLayout,
)
"""

FUTURE_IMPORT = re.compile(r"^\s*from\s+__future__\s+import\s+.+$")
RELATIVE_IMPORT = re.compile(
    r"^\s*from\s+\.+[\w.]+\s+import\s+.+$"
    r"|^\s*from\s+\.+[\w.]+\s+import\s+\(.+\)$"
    r"|^\s*from\s+\.(?:_imports|[\w.]+)\s+import\s+.+$"
    r"|^\s*from\s+\.(?:_imports|[\w.]+)\s+import\s+\(.+\)$"
)

def _is_header_import_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if FUTURE_IMPORT.match(line) or RELATIVE_IMPORT.match(line):
        return True
    if stripped.startswith("import ") or stripped.startswith("from "):
        return True
    return stripped == "# noqa: F403,F401"

def _import_opens_paren(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith(("import ", "from ")):
        return False
    if "(" not in stripped:
        return False
    return not stripped.rstrip().endswith(")")

def _strip_module_preamble(source: str) -> str:
    """Remove module docstring and leading duplicate import block only."""
    lines = source.splitlines(keepends=True)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(('"""', "'''")):
        quote = '"""' if '"""' in lines[i] else "'''"
        if lines[i].count(quote) >= 2 and lines[i].strip().endswith(quote):
            i += 1
        else:
            i += 1
            while i < len(lines):
                if quote in lines[i]:
                    i += 1
                    break
                i += 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("if TYPE_CHECKING:"):
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
                i += 1
            continue
        if not _is_header_import_line(line):
            break
        if _import_opens_paren(line):
            i += 1
            while i < len(lines) and ")" not in lines[i]:
                i += 1
            if i < len(lines):
                i += 1
            continue
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "".join(lines[i:])

def _git_show_ref(ref: str) -> str | None:
    probe = subprocess.run(
        ["git", "cat-file", "-e", ref],
        cwd=ROOT.parent,
        capture_output=True,
    )
    if probe.returncode != 0:
        return None
    return subprocess.check_output(
        ["git", "show", ref],
        cwd=ROOT.parent,
        text=True,
    )

def _docstring_source(monolith: Path) -> Path:
    if monolith.is_file():
        head = monolith.read_text(encoding="utf-8")[:120]
        rest = head.split("\n", 1)[1] if head.startswith("#!") and "\n" in head else head
        if not rest.startswith("# GENERATED"):
            return monolith
    for ref in (
        "HEAD:BTFViewer/builds/btf_viewer.py",
        "HEAD:BTFViewer/btf_viewer.py",
    ):
        raw = _git_show_ref(ref)
        if raw is None:
            continue
        cache = ROOT / "scripts" / ".monolith_doc_cache.py"
        cache.write_text(raw, encoding="utf-8")
        return cache
    return monolith

def _strip_bundle_preamble(text: str) -> str:
    """Drop shebang + GENERATED banner so the module docstring can be parsed."""
    lines = text.splitlines(keepends=True)
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):
        i += 1
    if i < len(lines) and lines[i].startswith("# GENERATED"):
        i += 1
    return "".join(lines[i:])

def _read_docstring(monolith: Path) -> str:
    src = _docstring_source(monolith)
    if src.is_file():
        text = _strip_bundle_preamble(src.read_text(encoding="utf-8"))
        mod = ast.parse(text)
        doc = ast.get_docstring(mod, clean=False)
        if doc:
            return f'"""{doc}"""\n\n'
    return '"""\nbtf_viewer.py - Single-file RTOS BTF Viewer (PySide6).\n"""\n\n'

def _section_banner(name: str, body: str) -> str:
    marker = SECTION_MARKERS.get(name, name)
    head = body[:400].lower()
    if marker.lstrip("# ").lower() in head:
        return body
    label = marker.lstrip("# ")
    sep = "# " + "=" * 75 + "\n"
    return f"{sep}# {label}\n{sep}\n{body}"

def _split_platform(body: str) -> tuple[str, str]:
    """Return (macOS stderr block, xcb/CLI startup helpers)."""
    key = "_XCB_CURSOR_SONAME"
    idx = body.find(key)
    if idx < 0:
        return body.strip() + "\n\n", ""
    stderr = body[:idx].strip()
    rest = body[idx:].strip()
    if stderr:
        stderr += "\n\n"
    if rest:
        rest += "\n\n"
    return stderr, rest

def _module_path(pkg_dir: Path, name: str) -> Path:
    if name.endswith("/__init__"):
        sub = name[: -len("/__init__")]
        return pkg_dir / sub / "__init__.py"
    parts = name.split("/")
    if len(parts) == 1:
        return pkg_dir / f"{name}.py"
    return pkg_dir.joinpath(*parts).with_suffix(".py")

def bundle(pkg_dir: Path, out_path: Path, monolith: Path) -> None:
    parts: list[str] = [SHEBANG, GENERATED_BANNER, _read_docstring(monolith)]
    parts.append("from __future__ import annotations\n\n")
    parts.append(SHARED_IMPORTS)
    parts.append("\n")

    platform_raw = (pkg_dir / "platform.py").read_text(encoding="utf-8")
    platform_body = _strip_module_preamble(platform_raw)
    stderr_block, platform_tail = _split_platform(platform_body)
    if stderr_block.strip():
        parts.append(MACOS_STDERR_HEADER)
        parts.append(stderr_block)

    for name in BUNDLE_MODULES:
        if name == "platform":
            if not platform_tail.strip():
                continue
            body = _section_banner(name, platform_tail)
        else:
            mod_path = _module_path(pkg_dir, name)
            if not mod_path.is_file():
                raise SystemExit(f"missing module: {mod_path}")
            raw = mod_path.read_text(encoding="utf-8")
            body = _strip_module_preamble(raw)
            body = _section_banner(name, body)
        parts.append(body)
        if not body.endswith("\n"):
            parts.append("\n")

    parts.append("\nif __name__ == \"__main__\":\n    main()\n")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(parts), encoding="utf-8")
    mode = out_path.stat().st_mode
    out_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Bundled {len(BUNDLE_MODULES)} module sections -> {out_path}")

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--pkg", type=Path, default=PKG)
    ap.add_argument("--monolith-doc", type=Path, default=MONOLITH,
                    help="Source for top-level docstring (existing btf_viewer.py)")
    args = ap.parse_args()
    if not args.pkg.is_dir():
        print(f"error: package not found: {args.pkg}", file=sys.stderr)
        raise SystemExit(1)
    bundle(args.pkg, args.output, args.monolith_doc)

if __name__ == "__main__":
    main()
