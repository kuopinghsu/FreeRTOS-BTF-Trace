"""Shared stdlib and PySide6 imports for btf_viewer_pkg development mode.

Stripped when bundling into the single-file btf_viewer.py (see scripts/bundle_viewer.py).
"""
from __future__ import annotations

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    QPainterPath, QPainterPathStroker, QPalette, QPen, QPixmap, QPolygonF, QShortcut, QTextCharFormat, QTextCursor, QTextOption, QTransform, QWheelEvent,
)
from PySide6.QtSvg import QSvgGenerator, QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QFormLayout, QFrame, QGridLayout, QInputDialog,
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsOpacityEffect,
    QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog, QCompleter,
    QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QScrollBar, QDoubleSpinBox, QSlider, QSpinBox, QStackedWidget,
    QStyle, QStyleFactory, QStyleOptionGraphicsItem, QAbstractItemView,
    QProxyStyle, QStyledItemDelegate, QTabBar, QTabWidget, QTableWidget, QTableWidgetItem, QToolButton, QToolTip,
    QPlainTextEdit, QTextBrowser, QTextEdit,
    QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QWidgetAction, QSizePolicy, QSplitter, QSplitterHandle, QLayout,
)

__all__ = [k for k in globals().keys() if not k.startswith("__")]
