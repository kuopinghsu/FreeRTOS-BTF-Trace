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
from bisect import bisect_left, bisect_right
from collections import defaultdict
from operator import attrgetter as _attrgetter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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

__all__ = [k for k in globals().keys() if not k.startswith("__")]
