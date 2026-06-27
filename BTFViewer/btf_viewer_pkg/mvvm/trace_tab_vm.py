"""Per-tab trace document view-model."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal

from ..parser import BtfTrace, TraceAnnotation, TraceBookmark
from .base import ViewModelBase
from .models import PlotSessionState, TraceTabModel
from .stats_vm import StatsViewModel

class TraceTabViewModel(ViewModelBase):
    """ViewModel for one open trace tab."""

    trace_changed = Signal()
    marks_changed = Signal()
    find_changed = Signal()
    undo_changed = Signal()
    plot_changed = Signal()

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

    def capture_plot_session(self) -> tuple[Optional[str], Optional[str], bool, Optional[str]]:
        p = self._model.plot
        return p.mk, p.kind, p.open, p.preemptor

    def set_plot_session(
        self,
        mk: Optional[str],
        kind: Optional[str],
        open_: bool,
        preemptor: Optional[str],
    ) -> None:
        self._model.plot = PlotSessionState(mk=mk, kind=kind, open=open_, preemptor=preemptor)
        self.plot_changed.emit()
        self.changed.emit()
