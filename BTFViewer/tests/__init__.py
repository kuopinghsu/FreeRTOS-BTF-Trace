# BTFViewer characterization tests (stdlib unittest + PySide6 offscreen).
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Offscreen QPA emits harmless font-alias and propagateSizeHints noise.
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.qpa.fonts.warning=false;qt.qpa.offscreen.warning=false",
)


def destroy_main_window(win) -> None:
    """Close a MainWindow test fixture and actually free its C++ object.

    MainWindow never sets ``WA_DeleteOnClose`` (a single-window desktop app
    doesn't need it), so plain ``close()`` only hides the window — its whole
    widget tree stays alive and registered with ``QApplication`` for the
    rest of the process. Each GUI test builds a fresh MainWindow in the
    *same* process, and every one left behind makes every later
    ``app.setStyleSheet()``/``setPalette()`` call (theme apply, run from
    every ``MainWindow.__init__``) re-polish that dead tree too — this
    snowballs the suite's wall-clock time as more GUI tests run.

    ``deleteLater()`` alone does not free it either: PySide/Qt only runs
    deferred deletion during a genuine event-loop tick, not a bare
    ``processEvents()`` call, so pump one via a short ``app.exec()``.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    try:
        win.close()
    except RuntimeError:
        return
    win.deleteLater()
    app = QApplication.instance()
    if app is not None:
        QTimer.singleShot(0, app.quit)
        app.exec()
