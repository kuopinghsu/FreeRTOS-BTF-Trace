"""In-app Statistics Reference viewer (Desktop).

Renders STATISTICS.md / STATISTICS_zh-TW.md — pre-rendered to static HTML
by scripts/build_docs_html.py — inside an embedded QtWebEngine browser,
scrolled to the section the user came from. No markdown parsing happens
at app runtime.

Ships as a single ``btf_viewer.hlp`` file next to ``btf_viewer.py`` (NOT
a ``docs_html/`` folder under the repo tree) so a release can be just
those two files, copied anywhere — no BTFViewer/ package layout needed.
The file holds a JSON envelope ``{"en": "<!doctype ...", "zh-tw": "<!doctype
..."}`` — one complete, independent HTML document per language, since both
source .md files share the same anchor ids (merging them into one DOM would
collide). ``_load_pages()`` parses it once and ``_toggle_lang()`` swaps
which language's document is loaded, persisting the choice to
``btf_viewer.rc``'s ``[help] stats_ref_lang`` key via the parent
MainWindow's ``_RcSettings`` instance.

Content is loaded via ``setHtml()`` (not ``load(QUrl.fromLocalFile(...))``,
which would depend on Chromium's file-extension MIME sniffing recognizing
``.hlp``) and anchor-scrolled via JavaScript once loaded, with its own
back/forward history stack — mirroring how Web renders the same content
through ``<iframe srcdoc>`` (no navigable URL there either).

Web parity: web/src/components/StatsReferenceViewer.vue.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

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
    STATS_SECTION_HELP,
    STATS_SECTION_TITLES,
)

HELP_FILENAME = "btf_viewer.hlp"
# btf_viewer.hlp holds a JSON envelope {"en": "<!doctype ...", "zh-tw": "<!doctype
# ..."} — one complete, independent HTML document per language (see
# scripts/build_docs_html.py's module docstring for why: both source .md
# files share the same anchor ids, so merging them into one DOM would
# collide). Web parity: web/src/components/StatsReferenceViewer.vue.
_LANG_LABELS = {"en": "EN", "zh-tw": "繁中"}
_LANG_SWITCH_TOOLTIPS = {"en": "Switch to 繁體中文", "zh-tw": "Switch to English"}
_OTHER_LANG = {"en": "zh-tw", "zh-tw": "en"}
# A second custom role (distinct from Qt.ItemDataRole.UserRole, which holds
# a top-level section id) marks a TOC row as a sub-heading within the
# active section — see scripts/build_docs_html.py's embedded
# statistics-subsections JSON for where this data comes from.
_SUB_ROLE = Qt.ItemDataRole.UserRole + 1
_SUBSECTIONS_RE = re.compile(
    r'<script type="application/json" id="statistics-subsections">(.*?)</script>', re.S)


def _parse_subsections(html: str) -> Dict[str, List[Dict[str, str]]]:
    m = _SUBSECTIONS_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


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
        self._pages: Dict[str, str] = {}
        self._doc_html: Optional[str] = None
        self._subsections: Dict[str, List[Dict[str, str]]] = {}
        self._sub_items: List[QListWidgetItem] = []
        self._view: Optional["QWebEngineView"] = None

        settings = getattr(parent, "_settings", None)
        saved_lang = settings.get("help", "stats_ref_lang", "en") if settings is not None else "en"
        self._lang: str = saved_lang if saved_lang in _LANG_LABELS else "en"

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

        self._lang_btn = QToolButton()
        self._lang_btn.setText(_LANG_LABELS[self._lang])
        self._lang_btn.setToolTip(_LANG_SWITCH_TOOLTIPS[self._lang])
        self._lang_btn.setAutoRaise(True)
        self._lang_btn.clicked.connect(self._toggle_lang)
        row.addWidget(self._lang_btn)

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
            if not q:
                item.setHidden(False)
                continue
            help_text = STATS_SECTION_HELP.get(sid, "")
            match = q in item.text().lower() or q in help_text.lower()
            item.setHidden(not match)

    def _on_toc_item_clicked(self, item: QListWidgetItem) -> None:
        sub_id = item.data(_SUB_ROLE)
        if sub_id:
            self._scroll_to(sub_id)  # same page, no history/breadcrumb change
            return
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

        if not self._pages and not self._load_pages():
            self._breadcrumb.setText(f"{crumb}  (reference not built)")
            return
        self._sync_toc_subsections(section_id)
        if self._view is None:
            return
        if self._doc_loaded:
            self._scroll_to(section_id)
        else:
            self._view.setHtml(self._doc_html, QUrl("about:blank"))

    def _load_pages(self) -> bool:
        """Parse ``btf_viewer.hlp``'s ``{"en": ..., "zh-tw": ...}`` envelope
        into ``self._pages`` and select the current language's page.

        Returns False if the file is missing or not the JSON envelope this
        build produces (e.g. a stale pre-dual-language ``.hlp``), leaving
        ``self._pages`` empty so the caller can show a "not built" message.
        """
        help_path = help_file_path()
        if help_path is None:
            return False
        try:
            pages = json.loads(help_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(pages, dict) or not pages:
            return False
        self._pages = pages
        if self._lang not in self._pages:
            self._lang = "en" if "en" in self._pages else next(iter(self._pages))
            self._lang_btn.setText(_LANG_LABELS.get(self._lang, self._lang))
            self._lang_btn.setToolTip(_LANG_SWITCH_TOOLTIPS.get(self._lang, ""))
        self._doc_html = self._pages[self._lang]
        self._subsections = _parse_subsections(self._doc_html)
        return True

    def _toggle_lang(self) -> None:
        if not self._pages:
            return
        lang = _OTHER_LANG.get(self._lang, "en")
        if lang not in self._pages or lang == self._lang:
            return
        self._lang = lang
        self._doc_html = self._pages[lang]
        self._subsections = _parse_subsections(self._doc_html)
        self._lang_btn.setText(_LANG_LABELS[lang])
        self._lang_btn.setToolTip(_LANG_SWITCH_TOOLTIPS[lang])

        settings = getattr(self.parent(), "_settings", None)
        if settings is not None:
            settings.set("help", "stats_ref_lang", lang)

        if self._current_section:
            self._sync_toc_subsections(self._current_section)
        self._doc_loaded = False
        if self._view is not None:
            self._view.setHtml(self._doc_html, QUrl("about:blank"))

    def _sync_toc_subsections(self, section_id: str) -> None:
        """Show *section_id*'s h3 sub-headings (if any) nested right under
        its TOC row; collapse whatever the previously active section had."""
        for item in self._sub_items:
            row = self._toc.row(item)
            if row >= 0:
                self._toc.takeItem(row)
        self._sub_items = []

        subs = self._subsections.get(section_id) or []
        if not subs:
            return
        parent_row = -1
        for i in range(self._toc.count()):
            if self._toc.item(i).data(Qt.ItemDataRole.UserRole) == section_id:
                parent_row = i
                break
        if parent_row < 0:
            return
        for offset, sub in enumerate(subs, start=1):
            item = QListWidgetItem(f"        {sub['title']}")
            item.setData(Qt.ItemDataRole.UserRole, "")
            item.setData(_SUB_ROLE, sub["id"])
            font = item.font()
            font.setPointSize(max(font.pointSize() - 1, 7))
            item.setFont(font)
            self._toc.insertItem(parent_row + offset, item)
            self._sub_items.append(item)

    def _on_load_finished(self, ok: bool) -> None:
        self._doc_loaded = bool(ok)
        if not ok:
            return
        main_window = self.parent()
        self.sync_theme(bool(getattr(main_window, "_is_dark", True)))
        if self._current_section:
            self._scroll_to(self._current_section)

    def sync_theme(self, is_dark: bool) -> None:
        """Match the reference's own dark/light CSS to the app's current
        theme. The page defaults to dark (see build_docs_html.py's
        <html data-theme="dark">) and nothing updates it afterward unless
        told to — this is that telling, called once when the page finishes
        loading and again whenever MainWindow._apply_theme() runs while
        this viewer is open."""
        if self._view is None or not self._doc_loaded:
            return
        theme = "dark" if is_dark else "light"
        self._view.page().runJavaScript(
            f"window.__setDocTheme && window.__setDocTheme('{theme}');"
        )

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
