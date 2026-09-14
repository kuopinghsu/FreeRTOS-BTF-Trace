"""Shared stdlib and PySide6 imports for btf_viewer_pkg development mode.

Stripped when bundling into the single-file btf_viewer.py (see scripts/bundle_viewer.py).
"""
from __future__ import annotations

import os
import sys
import threading

# --- Headless / GPU-less software-GL fallback -----------------------------
# Runs before the first PySide6 import. On Linux with no DRM render node
# (WSL2, containers, CI, plain SSH) Qt's OpenGL and QtWebEngine's Chromium GPU
# process fail noisily and fall back to software anyway; select software
# rendering up front so the fallback is clean and silent. A real GPU or any
# explicit override is left untouched. This block is duplicated verbatim in
# btf_viewer_pkg/_imports.py and scripts/bundle_viewer.py (SHARED_IMPORTS),
# checked by tests/test_gpu_fallback.py.
if sys.platform.startswith("linux") and not os.environ.get("BTFVIEWER_NO_GL_FALLBACK"):
    try:
        _dri_nodes = os.listdir("/dev/dri")
    except OSError:
        _dri_nodes = []
    if not any(_n.startswith("renderD") for _n in _dri_nodes):
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        _have = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
        for _flag in ("--disable-gpu", "--disable-gpu-compositing"):
            if _flag not in _have:
                _have.append(_flag)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(_have)
        del _have, _flag
    del _dri_nodes

import argparse
import base64
import configparser
import csv
import datetime
import functools
import hashlib
import html
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ssl
import struct
import itertools
import json
import math
import time
import re
import shutil
import subprocess
import tempfile
import traceback
import zlib
import gzip
import bz2
import zipfile
import io
from contextlib import contextmanager
from pathlib import Path
from bisect import bisect_left, bisect_right
from collections import defaultdict
from operator import attrgetter as _attrgetter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Any, Set, Union
import xml.etree.ElementTree as ET

from PySide6.QtCore import (
    QBuffer, QByteArray, QEasingCurve, QEvent, QEventLoop, QIODevice, QLineF, QMimeData,
    QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, QUrl,
    QPropertyAnimation, QVariantAnimation, Property, Signal, Slot,
)
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QHoverEvent, QIcon, QImage, QKeySequence, QLinearGradient, QMouseEvent, QPainter, QRawFont,
    QPainterPath, QPainterPathStroker, QPalette, QPen, QPixmap, QPolygonF, QRegion, QShortcut, QTextCharFormat, QTextCursor, QTextOption, QTransform, QWheelEvent,
)
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
# QtWebEngineWidgets must be imported before the QApplication instance is
# constructed (Qt.AA_ShareOpenGLContexts side effect) — Statistics Reference
# viewer (stats_reference.py) only imports it lazily, well after QApplication
# already exists, so this early, always-executed import is what makes that
# safe (a late-only import crashes the process once a QWebEngineView is used).
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except ImportError:
    QWebEngineView = None  # type: ignore[assignment]
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGridLayout, QInputDialog,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsOpacityEffect,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog, QCompleter,
    QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QScrollArea, QScrollBar, QDoubleSpinBox, QSlider, QSpinBox, QStackedWidget,
    QStyle, QStyleFactory, QStyleOptionGraphicsItem, QAbstractItemView,
    QProxyStyle, QStyledItemDelegate, QTabBar, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton, QToolTip,
    QPlainTextEdit, QTextBrowser, QTextEdit,
    QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QWidgetAction, QSizePolicy, QSplitter, QSplitterHandle, QLayout,
)

__all__ = [k for k in globals().keys() if not k.startswith("__")]
