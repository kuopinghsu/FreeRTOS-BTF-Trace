"""Root application view-model."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Signal

from .app_settings import AppSettingsViewModel
from .base import ViewModelBase
from .models import SessionModel
from .trace_tab_vm import TraceTabViewModel

class MainViewModel(ViewModelBase):
    """Root view-model: open traces, session loading, and application settings."""

    active_tab_changed = Signal(object)
    tabs_changed = Signal()
    session_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.settings = AppSettingsViewModel(self)
        self._session = SessionModel()
        self._tabs: List[TraceTabViewModel] = []
        self._active_index: int = -1

    @property
    def session(self) -> SessionModel:
        return self._session

    @property
    def tabs(self) -> List[TraceTabViewModel]:
        return self._tabs

    @property
    def active_index(self) -> int:
        return self._active_index

    @property
    def active_tab(self) -> Optional[TraceTabViewModel]:
        if 0 <= self._active_index < len(self._tabs):
            return self._tabs[self._active_index]
        return None

    @property
    def session_restore_queue(self) -> List[str]:
        return self._session.restore_queue

    @session_restore_queue.setter
    def session_restore_queue(self, value: List[str]) -> None:
        self._session.restore_queue = list(value)
        self.session_changed.emit()
        self.changed.emit()

    @property
    def session_restore_active_idx(self) -> int:
        return self._session.restore_active_idx

    @session_restore_active_idx.setter
    def session_restore_active_idx(self, value: int) -> None:
        self._session.restore_active_idx = int(value)
        self.session_changed.emit()
        self.changed.emit()

    @property
    def load_in_progress(self) -> bool:
        return self._session.load_in_progress

    @load_in_progress.setter
    def load_in_progress(self, value: bool) -> None:
        self._session.load_in_progress = bool(value)
        self.session_changed.emit()
        self.changed.emit()

    def add_tab(self, tab_vm: TraceTabViewModel) -> int:
        self._tabs.append(tab_vm)
        idx = len(self._tabs) - 1
        self.tabs_changed.emit()
        self.changed.emit()
        return idx

    def remove_tab(self, index: int) -> None:
        if not (0 <= index < len(self._tabs)):
            return
        self._tabs.pop(index)
        if not self._tabs:
            self._active_index = -1
        elif self._active_index >= len(self._tabs):
            self._active_index = len(self._tabs) - 1
        elif index < self._active_index:
            self._active_index -= 1
        self.tabs_changed.emit()
        self.changed.emit()

    def set_active_index(self, index: int) -> None:
        if index == self._active_index:
            return
        if not self._tabs:
            self._active_index = -1
        elif 0 <= index < len(self._tabs):
            self._active_index = index
        else:
            return
        self.active_tab_changed.emit(self.active_tab)
        self.changed.emit()

    def tab_for_path(self, path: str, *, normalizer: Callable[[str], str]) -> int:
        norm = normalizer(path)
        for i, tab in enumerate(self._tabs):
            if normalizer(tab.path) == norm:
                return i
        return -1
