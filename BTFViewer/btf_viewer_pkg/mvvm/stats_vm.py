"""Statistics panel state view-model (per trace tab)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PySide6.QtCore import Signal

from ..config import (
    STATS_TABLE_DEFAULT_H,
    STATS_TABLE_MIG_DEFAULT_H,
    STATS_UTIL_LABEL_W,
)
from .base import ViewModelBase
from .models import StatsTabModel

if TYPE_CHECKING:
    from ..stats import _StatsPanel


def _default_section_collapsed() -> Dict[str, bool]:
    return {
        "cores": False,
        "tasks": False,
        "migrations": False,
        "exec": False,
        "block": False,
        "inter": False,
        "health": False,
        "preemption": False,
        "priority": False,
        "sync": False,
        "intervals": False,
    }


def _default_section_table_heights() -> Dict[str, int]:
    return {
        "migrations": STATS_TABLE_MIG_DEFAULT_H,
        "exec": STATS_TABLE_DEFAULT_H,
        "block": STATS_TABLE_DEFAULT_H,
        "inter": STATS_TABLE_DEFAULT_H,
        "preemption": STATS_TABLE_MIG_DEFAULT_H,
        "priority": STATS_TABLE_DEFAULT_H,
        "intervals": STATS_TABLE_DEFAULT_H,
        "sync": STATS_TABLE_DEFAULT_H,
        "sync_issues": STATS_TABLE_MIG_DEFAULT_H,
        "health": STATS_TABLE_DEFAULT_H,
    }


class StatsViewModel(ViewModelBase):
    """ViewModel for statistics panel scope and layout state."""

    scope_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model = StatsTabModel(
            section_collapsed=_default_section_collapsed(),
            section_table_heights=_default_section_table_heights(),
            util_label_col_w=STATS_UTIL_LABEL_W,
        )

    @property
    def model(self) -> StatsTabModel:
        return self._model

    @property
    def cursor_times(self) -> List[int]:
        return self._model.cursor_times

    @cursor_times.setter
    def cursor_times(self, value: List[int]) -> None:
        self._model.cursor_times = list(value)
        self.scope_changed.emit()
        self.changed.emit()

    @property
    def scope_to_cursors(self) -> bool:
        return self._model.scope_to_cursors

    @scope_to_cursors.setter
    def scope_to_cursors(self, value: bool) -> None:
        self._model.scope_to_cursors = bool(value)
        self.scope_changed.emit()
        self.changed.emit()

    @property
    def export_scope_override(self) -> Optional[Tuple[int, int]]:
        return self._model.export_scope_override

    @export_scope_override.setter
    def export_scope_override(self, value: Optional[Tuple[int, int]]) -> None:
        self._model.export_scope_override = value
        self.scope_changed.emit()
        self.changed.emit()

    @property
    def section_collapsed(self) -> Dict[str, bool]:
        return self._model.section_collapsed

    @property
    def section_table_heights(self) -> Dict[str, int]:
        return self._model.section_table_heights

    @property
    def util_label_col_w(self) -> int:
        return self._model.util_label_col_w

    @util_label_col_w.setter
    def util_label_col_w(self, value: int) -> None:
        self._model.util_label_col_w = int(value)
        self.changed.emit()

    def copy_from_panel(self, panel: "_StatsPanel") -> None:
        """Snapshot live panel state into this view-model."""
        m = self._model
        m.cursor_times = list(panel._cursor_times)
        m.scope_to_cursors = bool(panel._scope_to_cursors)
        m.export_scope_override = panel._export_scope_override
        m.section_collapsed = dict(panel._section_collapsed)
        m.section_table_heights = dict(panel._section_table_heights)
        m.util_label_col_w = int(panel._util_label_col_w)
        self.changed.emit()

    def apply_to_panel(self, panel: "_StatsPanel", *, refresh_stats: bool = True) -> None:
        """Push view-model state into the statistics panel widget."""
        m = self._model
        panel._section_table_heights.update(m.section_table_heights)
        panel._util_label_col_w = m.util_label_col_w
        panel._export_scope_override = m.export_scope_override
        panel._scope_to_cursors = m.scope_to_cursors
        if hasattr(panel, "_scope_cb"):
            panel._scope_cb.blockSignals(True)
            panel._scope_cb.setChecked(m.scope_to_cursors)
            panel._scope_cb.blockSignals(False)
        for section_id, collapsed in m.section_collapsed.items():
            if section_id in panel._section_headers:
                panel._set_section_collapsed(section_id, collapsed)
        panel.set_cursor_times(m.cursor_times, refresh_stats=refresh_stats)
        panel.apply_section_table_heights(m.section_table_heights)
