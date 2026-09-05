"""In-app Statistics Reference viewer (Desktop).

Renders STATISTICS.md — pre-rendered to static HTML by
scripts/build_docs_html.py — inside an embedded QtWebEngine browser,
scrolled to the section the user came from. No markdown parsing happens
at app runtime.

Ships as a single ``btf_viewer.hlp`` file next to ``btf_viewer.py`` (NOT
a ``docs_html/`` folder under the repo tree) so a release can be just
those two files, copied anywhere — no BTFViewer/ package layout needed.
Content is loaded via ``setHtml()`` (not ``load(QUrl.fromLocalFile(...))``,
which would depend on Chromium's file-extension MIME sniffing recognizing
``.hlp``) and anchor-scrolled via JavaScript once loaded, with its own
back/forward history stack — mirroring how Web renders the same content
through ``<iframe srcdoc>`` (no navigable URL there either).

Web parity: web/src/components/StatsReferenceViewer.vue.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAVE_WEBENGINE = True
except ImportError:  # pragma: no cover - environment without QtWebEngine
    QWebEngineView = None  # type: ignore[assignment,misc]
    _HAVE_WEBENGINE = False

from .config import (
    STATS_CATEGORY_LABELS,
    STATS_PINNABLE_SECTIONS,
    STATS_SECTION_CATEGORIES,
    STATS_SECTION_CATEGORY,
    STATS_SECTION_TITLES,
)

HELP_FILENAME = "btf_viewer.hlp"


def help_file_path() -> Optional[Path]:
    """Resolve ``btf_viewer.hlp``.

    Same two-tier lookup as the existing ``play_audio_clip.py`` helper in
    demo_inapp.py: prefer the in-repo dev location, then fall back to
    beside the actually-invoked script — the layout a standalone release
    (just ``btf_viewer.py`` + ``btf_viewer.hlp`` copied elsewhere) has.
    """
    dev_candidate = Path(__file__).resolve().parents[1] / "builds" / HELP_FILENAME
    if dev_candidate.is_file():
        return dev_candidate
    release_candidate = Path(sys.argv[0]).resolve().parent / HELP_FILENAME
    return release_candidate if release_candidate.is_file() else None


class StatsReferenceViewer(QDialog):
    """Docs viewer: chrome bar, category-grouped TOC, embedded browser."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Statistics Reference")
        self.setObjectName("stats_reference_viewer")
        self.setSizeGripEnabled(True)
        self.resize(1040, 760)

        self._current_section: Optional[str] = None
        self._history: List[str] = []
        self._history_index: int = -1
        self._doc_loaded = False
        self._doc_html: Optional[str] = None
        self._view: Optional["QWebEngineView"] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_chrome())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.addWidget(self._build_toc())
        body.addWidget(self._build_content_pane())
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        outer.addWidget(body, 1)

    # -- construction ----------------------------------------------------
    def _build_chrome(self) -> QWidget:
        chrome = QWidget()
        chrome.setObjectName("stats_ref_chrome")
        row = QHBoxLayout(chrome)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(4)

        self._back_btn = QToolButton()
        self._back_btn.setText("←")
        self._back_btn.setToolTip("Back")
        self._back_btn.setAutoRaise(True)
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)
        row.addWidget(self._back_btn)

        self._fwd_btn = QToolButton()
        self._fwd_btn.setText("→")
        self._fwd_btn.setToolTip("Forward")
        self._fwd_btn.setAutoRaise(True)
        self._fwd_btn.setEnabled(False)
        self._fwd_btn.clicked.connect(self._go_forward)
        row.addWidget(self._fwd_btn)

        self._breadcrumb = QLabel("Statistics Reference")
        self._breadcrumb.setObjectName("stats_ref_breadcrumb")
        self._breadcrumb.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._breadcrumb, 1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search reference…")
        self._search.setFixedWidth(190)
        self._search.textChanged.connect(self._filter_toc)
        row.addWidget(self._search)

        open_ext_btn = QToolButton()
        open_ext_btn.setText("↗")
        open_ext_btn.setToolTip("Open in system browser")
        open_ext_btn.setAutoRaise(True)
        open_ext_btn.clicked.connect(self._open_in_system_browser)
        row.addWidget(open_ext_btn)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close")
        close_btn.setAutoRaise(True)
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)

        return chrome

    def _build_toc(self) -> QWidget:
        self._toc = QListWidget()
        self._toc.setObjectName("stats_ref_toc")
        self._toc.setMaximumWidth(260)
        self._toc.setMinimumWidth(200)
        self._toc.itemClicked.connect(self._on_toc_item_clicked)
        self._populate_toc()
        return self._toc

    def _build_content_pane(self) -> QWidget:
        if _HAVE_WEBENGINE:
            self._view = QWebEngineView()
            self._view.loadFinished.connect(self._on_load_finished)
            return self._view
        placeholder = QLabel(
            "QtWebEngine is not available in this environment.\n"
            "Use “Open in system browser” to view the reference.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        return placeholder

    # -- TOC ---------------------------------------------------------------
    def _populate_toc(self) -> None:
        self._toc.clear()
        for cat in STATS_SECTION_CATEGORIES:
            label = STATS_CATEGORY_LABELS.get(cat, cat)
            header = QListWidgetItem(label.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            self._toc.addItem(header)
            for sid in STATS_PINNABLE_SECTIONS:
                if STATS_SECTION_CATEGORY.get(sid) != cat:
                    continue
                title = STATS_SECTION_TITLES.get(sid, sid)
                item = QListWidgetItem(f"    {title}")
                item.setData(Qt.ItemDataRole.UserRole, sid)
                self._toc.addItem(item)

    def _filter_toc(self, text: str) -> None:
        q = text.strip().lower()
        for i in range(self._toc.count()):
            item = self._toc.item(i)
            sid = item.data(Qt.ItemDataRole.UserRole)
            if sid is None:
                continue  # category headers always visible
            item.setHidden(bool(q) and q not in item.text().lower())

    def _on_toc_item_clicked(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid:
            self.open_section(sid)

    # -- navigation ----------------------------------------------------
    def open_section(self, section_id: str) -> None:
        """Show the viewer, scrolled to *section_id* (its STATISTICS.md anchor)."""
        # Truncate any forward history, then push — a normal browser-tab history model.
        self._history = self._history[: self._history_index + 1] + [section_id]
        self._history_index = len(self._history) - 1
        self._navigate(section_id)
        self.show()
        self.raise_()
        self.activateWindow()

    def _navigate(self, section_id: str) -> None:
        self._current_section = section_id
        title = STATS_SECTION_TITLES.get(section_id, section_id)
        cat = STATS_SECTION_CATEGORY.get(section_id)
        cat_label = STATS_CATEGORY_LABELS.get(cat, cat) if cat else ""
        crumb = " › ".join(
            p for p in ("Statistics Reference", cat_label, title) if p)
        self._breadcrumb.setText(crumb)

        for i in range(self._toc.count()):
            item = self._toc.item(i)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == section_id)

        self._back_btn.setEnabled(self._history_index > 0)
        self._fwd_btn.setEnabled(self._history_index < len(self._history) - 1)

        if self._view is None:
            return
        if self._doc_html is None:
            help_path = help_file_path()
            if help_path is None:
                self._breadcrumb.setText(f"{crumb}  (reference not built)")
                return
            self._doc_html = help_path.read_text(encoding="utf-8")
        if self._doc_loaded:
            self._scroll_to(section_id)
        else:
            self._view.setHtml(self._doc_html, QUrl("about:blank"))

    def _on_load_finished(self, ok: bool) -> None:
        self._doc_loaded = bool(ok)
        if ok and self._current_section:
            self._scroll_to(self._current_section)

    def _scroll_to(self, section_id: str) -> None:
        if self._view is None:
            return
        js = (
            f"var el = document.getElementById('statistics-{section_id}');"
            "if (el) el.scrollIntoView();"
        )
        self._view.page().runJavaScript(js)

    def _go_back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._navigate(self._history[self._history_index])

    def _go_forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._navigate(self._history[self._history_index])

    def _open_in_system_browser(self) -> None:
        # btf_viewer.hlp is plain HTML but not a browser-registered extension
        # (unlike .html) — write a scratch copy with the right extension so
        # the OS file association actually opens a browser, not "no app".
        if self._doc_html is None:
            return
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8")
        try:
            tmp.write(self._doc_html)
        finally:
            tmp.close()
        url = QUrl.fromLocalFile(tmp.name)
        if self._current_section:
            url.setFragment(f"statistics-{self._current_section}")
        QDesktopServices.openUrl(url)

    # -- MainWindow's app-wide event filter (demo Esc/Space handling) crashes
    # (SIGSEGV in PySide::typeName / getWrapperForQObject) when it intercepts
    # a hover event from QWebEngineView's internal Qt Quick surface. That
    # surface delivers its first hover event synchronously from *inside*
    # QDialog.show()'s children-showing cascade (setVisible -> show_helper ->
    # showChildren -> the QWebEngineView -> its internal QQuickWidget's own
    # showEvent) — entirely before this dialog's own showEvent() ever runs,
    # so removing the filter there (a QDialog.showEvent override, tried
    # first) is already too late. Overriding show() itself, instead of
    # showEvent(), removes the filter before super().show() starts that
    # cascade. Trades away Esc/Space demo shortcuts while this viewer is
    # open — harmless, since a demo isn't driven while reading docs.
    def show(self) -> None:
        app = QApplication.instance()
        main_window = self.parent()
        if app is not None and main_window is not None:
            app.removeEventFilter(main_window)
        super().show()

    def closeEvent(self, event) -> None:  # noqa: N802
        app = QApplication.instance()
        main_window = self.parent()
        if app is not None and main_window is not None:
            app.installEventFilter(main_window)
        super().closeEvent(event)
