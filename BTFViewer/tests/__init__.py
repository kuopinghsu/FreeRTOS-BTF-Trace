# BTFViewer characterization tests (stdlib unittest + PySide6 offscreen).
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Offscreen QPA emits harmless font-alias and propagateSizeHints noise.
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.qpa.fonts.warning=false;qt.qpa.offscreen.warning=false",
)
