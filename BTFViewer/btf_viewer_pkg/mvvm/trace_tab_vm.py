"""Per-tab trace document view-model."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal

from ..parser import BtfTrace, TraceAnnotation, TraceBookmark
from .base import ViewModelBase
from .find_logic import FIND_RECOMPUTE
from .models import PlotSessionState, TabViewportModel, TraceTabModel
from .stats_vm import StatsViewModel
from .tab_viewport import apply_viewport, capture_viewport

class TraceTabViewModel(ViewModelBase):
    """ViewModel for one open trace tab."""

    trace_changed = Signal()
    marks_changed = Signal()
    find_changed = Signal()
    undo_changed = Signal()
    plot_changed = Signal()
    viewport_changed = Signal()

    def __init__(self, path: str, trace: BtfTrace, parent=None) -> None:
        super().__init__(parent)
        self._model = TraceTabModel(path=path, trace=trace)
        self.stats = StatsViewModel(self)

    @property
    def model(self) -> TraceTabModel:
        return self._model

    @property
    def path(self) -> str:
        return self._model.path

    @property
    def trace(self) -> Optional[BtfTrace]:
        return self._model.trace

    @trace.setter
    def trace(self, value: Optional[BtfTrace]) -> None:
        if self._model.trace is value:
            return
        self._model.trace = value
        self.trace_changed.emit()
        self.changed.emit()

    @property
    def bookmarks(self) -> List[TraceBookmark]:
        return self._model.bookmarks

    @bookmarks.setter
    def bookmarks(self, value: List[TraceBookmark]) -> None:
        self._model.bookmarks = list(value)
        self.marks_changed.emit()
        self.changed.emit()

    @property
    def annotations(self) -> List[TraceAnnotation]:
        return self._model.annotations

    @annotations.setter
    def annotations(self, value: List[TraceAnnotation]) -> None:
        self._model.annotations = list(value)
        self.marks_changed.emit()
        self.changed.emit()

    @property
    def mark_next_id(self) -> int:
        return self._model.mark_next_id

    @mark_next_id.setter
    def mark_next_id(self, value: int) -> None:
        self._model.mark_next_id = int(value)
        self.marks_changed.emit()
        self.changed.emit()

    @property
    def find_hits(self) -> List[int]:
        return self._model.find_hits

    @find_hits.setter
    def find_hits(self, value: List[int]) -> None:
        self._model.find_hits = list(value)
        self.find_changed.emit()
        self.changed.emit()

    @property
    def find_hit_idx(self) -> int:
        return self._model.find_hit_idx

    @find_hit_idx.setter
    def find_hit_idx(self, value: int) -> None:
        self._model.find_hit_idx = int(value)
        self.find_changed.emit()
        self.changed.emit()

    @property
    def find_marker_ns(self) -> Optional[int]:
        return self._model.find_marker_ns

    @find_marker_ns.setter
    def find_marker_ns(self, value: Optional[int]) -> None:
        self._model.find_marker_ns = value
        self.find_changed.emit()
        self.changed.emit()

    @property
    def find_query(self) -> str:
        return self._model.find_query

    @find_query.setter
    def find_query(self, value: str) -> None:
        self._model.find_query = str(value)
        self.find_changed.emit()
        self.changed.emit()

    @property
    def find_mode(self) -> str:
        return self._model.find_mode

    @find_mode.setter
    def find_mode(self, value: str) -> None:
        self._model.find_mode = str(value) or "Contains"
        self.find_changed.emit()
        self.changed.emit()

    def recompute_find_hits(self) -> str:
        """Update find hits from current query/mode; return status message."""
        hits, status = FIND_RECOMPUTE(
            self._model.trace,
            self._model.find_query,
            self._model.find_mode,
            self._model.annotations,
        )
        self._model.find_hits = hits
        self._model.find_hit_idx = -1
        self._model.find_marker_ns = None
        self.find_changed.emit()
        self.changed.emit()
        return status

    @property
    def undo_stack(self) -> list:
        return self._model.undo_stack

    @undo_stack.setter
    def undo_stack(self, value: list) -> None:
        self._model.undo_stack = list(value)
        self.undo_changed.emit()
        self.changed.emit()

    @property
    def redo_stack(self) -> list:
        return self._model.redo_stack

    @redo_stack.setter
    def redo_stack(self, value: list) -> None:
        self._model.redo_stack = list(value)
        self.undo_changed.emit()
        self.changed.emit()

    @property
    def plot_mk(self) -> Optional[str]:
        return self._model.plot.mk

    @plot_mk.setter
    def plot_mk(self, value: Optional[str]) -> None:
        self._model.plot.mk = value
        self.plot_changed.emit()
        self.changed.emit()

    @property
    def plot_kind(self) -> Optional[str]:
        return self._model.plot.kind

    @plot_kind.setter
    def plot_kind(self, value: Optional[str]) -> None:
        self._model.plot.kind = value
        self.plot_changed.emit()
        self.changed.emit()

    @property
    def plot_preemptor(self) -> Optional[str]:
        return self._model.plot.preemptor

    @plot_preemptor.setter
    def plot_preemptor(self, value: Optional[str]) -> None:
        self._model.plot.preemptor = value
        self.plot_changed.emit()
        self.changed.emit()

    @property
    def plot_open(self) -> bool:
        return self._model.plot.open

    @plot_open.setter
    def plot_open(self, value: bool) -> None:
        self._model.plot.open = bool(value)
        self.plot_changed.emit()
        self.changed.emit()

    @property
    def plot_interval_id(self) -> Optional[str]:
        return self._model.plot.interval_id

    @plot_interval_id.setter
    def plot_interval_id(self, value: Optional[str]) -> None:
        self._model.plot.interval_id = value
        self.plot_changed.emit()
        self.changed.emit()

    def capture_plot_session(
        self,
    ) -> tuple[Optional[str], Optional[str], bool, Optional[str], Optional[str]]:
        p = self._model.plot
        return p.mk, p.kind, p.open, p.preemptor, p.interval_id

    def set_plot_session(
        self,
        mk: Optional[str],
        kind: Optional[str],
        open_: bool,
        preemptor: Optional[str],
        interval_id: Optional[str] = None,
    ) -> None:
        self._model.plot = PlotSessionState(
            mk=mk, kind=kind, open=open_, preemptor=preemptor,
            interval_id=interval_id,
        )
        self.plot_changed.emit()
        self.changed.emit()

    @property
    def viewport(self) -> TabViewportModel:
        return self._model.viewport

    @viewport.setter
    def viewport(self, value: TabViewportModel) -> None:
        self._model.viewport = value
        self.viewport_changed.emit()
        self.changed.emit()

    def capture_viewport_from_view(self, view) -> None:
        self.viewport = capture_viewport(view)

    def apply_viewport_to_view(self, view) -> None:
        apply_viewport(view, self._model.viewport)
