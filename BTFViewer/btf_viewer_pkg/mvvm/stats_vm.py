"""Statistics panel state view-model (per trace tab)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PySide6.QtCore import Signal

from ..config import (
    STATS_UTIL_LABEL_W,
    default_section_collapsed,
    default_section_table_heights,
)
from .base import ViewModelBase
from .models import StatsTabModel

if TYPE_CHECKING:
    from ..stats import _StatsPanel

class StatsViewModel(ViewModelBase):
    """ViewModel for statistics panel scope and layout state."""

    scope_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model = StatsTabModel(
            section_collapsed=default_section_collapsed(),
            section_table_heights=default_section_table_heights(),
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
        self._model = StatsTabModel(**panel.capture_layout_state())
        self.changed.emit()

    def apply_to_panel(self, panel: "_StatsPanel", *, refresh_stats: bool = True) -> None:
        """Push view-model state into the statistics panel widget."""
        panel.apply_layout_state(self._model, refresh_stats=refresh_stats)
