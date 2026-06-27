"""Application-wide settings view-model."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal

from ..config import (
    CPU_LOAD_ROW_H,
    FONT_SIZE,
    LABEL_WIDTH,
    ROW_GAP,
    ROW_HEIGHT,
    STI_LINE_STYLE,
    STI_ROW_H,
    STI_WAVEFORM_H,
    UI_FONT_SIZE,
    _DEFAULT_MAX_CURSORS,
    _HOVER_HIGHLIGHT_ENABLED,
    _TIMESCALE_PER_PX_DEFAULT,
)
from .base import ViewModelBase
from .models import AppSettingsModel

if TYPE_CHECKING:
    from ..stats import _RcSettings

class AppSettingsViewModel(ViewModelBase):
    """ViewModel for application-wide UI settings (not per-tab)."""

    settings_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._model = AppSettingsModel()
        self.reset_to_config_defaults()

    @property
    def model(self) -> AppSettingsModel:
        return self._model

    def reset_to_config_defaults(self) -> None:
        m = self._model
        m.view_mode = "task"
        m.is_dark = True
        m.show_sti = True
        m.show_grid = True
        m.show_legend = True
        m.show_stats = True
        m.show_cpu_load = True
        m.show_marks = True
        m.show_find = True
        m.cpu_splitter_user_sized = False
        m.cpu_splitter_bottom_h = None
        m.font_size = FONT_SIZE
        m.ui_font_size = UI_FONT_SIZE
        m.max_cursors = _DEFAULT_MAX_CURSORS
        m.label_width = LABEL_WIDTH
        m.row_height = ROW_HEIGHT
        m.row_gap = ROW_GAP
        m.sti_row_h = STI_ROW_H
        m.sti_waveform_h = STI_WAVEFORM_H
        m.sti_line_style = STI_LINE_STYLE
        m.timescale_per_px_default = _TIMESCALE_PER_PX_DEFAULT
        m.hover_highlight = _HOVER_HIGHLIGHT_ENABLED
        m.cpu_load_row_h = CPU_LOAD_ROW_H
        m.colorblind = False
        m.horizontal = True
        self.settings_changed.emit()
        self.changed.emit()

    def _touch(self) -> None:
        self.settings_changed.emit()
        self.changed.emit()

    @property
    def view_mode(self) -> str:
        return self._model.view_mode

    @view_mode.setter
    def view_mode(self, value: str) -> None:
        self._model.view_mode = value
        self._touch()

    @property
    def is_dark(self) -> bool:
        return self._model.is_dark

    @is_dark.setter
    def is_dark(self, value: bool) -> None:
        self._model.is_dark = bool(value)
        self._touch()

    @property
    def show_sti(self) -> bool:
        return self._model.show_sti

    @show_sti.setter
    def show_sti(self, value: bool) -> None:
        self._model.show_sti = bool(value)
        self._touch()

    @property
    def show_grid(self) -> bool:
        return self._model.show_grid

    @show_grid.setter
    def show_grid(self, value: bool) -> None:
        self._model.show_grid = bool(value)
        self._touch()

    @property
    def show_legend(self) -> bool:
        return self._model.show_legend

    @show_legend.setter
    def show_legend(self, value: bool) -> None:
        self._model.show_legend = bool(value)
        self._touch()

    @property
    def show_stats(self) -> bool:
        return self._model.show_stats

    @show_stats.setter
    def show_stats(self, value: bool) -> None:
        self._model.show_stats = bool(value)
        self._touch()

    @property
    def show_cpu_load(self) -> bool:
        return self._model.show_cpu_load

    @show_cpu_load.setter
    def show_cpu_load(self, value: bool) -> None:
        self._model.show_cpu_load = bool(value)
        self._touch()

    @property
    def show_marks(self) -> bool:
        return self._model.show_marks

    @show_marks.setter
    def show_marks(self, value: bool) -> None:
        self._model.show_marks = bool(value)
        self._touch()

    @property
    def show_find(self) -> bool:
        return self._model.show_find

    @show_find.setter
    def show_find(self, value: bool) -> None:
        self._model.show_find = bool(value)
        self._touch()

    @property
    def cpu_splitter_user_sized(self) -> bool:
        return self._model.cpu_splitter_user_sized

    @cpu_splitter_user_sized.setter
    def cpu_splitter_user_sized(self, value: bool) -> None:
        self._model.cpu_splitter_user_sized = bool(value)
        self._touch()

    @property
    def cpu_splitter_bottom_h(self) -> int | None:
        return self._model.cpu_splitter_bottom_h

    @cpu_splitter_bottom_h.setter
    def cpu_splitter_bottom_h(self, value: int | None) -> None:
        self._model.cpu_splitter_bottom_h = value
        self._touch()

    @property
    def font_size(self) -> int:
        return self._model.font_size

    @font_size.setter
    def font_size(self, value: int) -> None:
        self._model.font_size = int(value)
        self._touch()

    @property
    def ui_font_size(self) -> int:
        return self._model.ui_font_size

    @ui_font_size.setter
    def ui_font_size(self, value: int) -> None:
        self._model.ui_font_size = int(value)
        self._touch()

    @property
    def max_cursors(self) -> int:
        return self._model.max_cursors

    @max_cursors.setter
    def max_cursors(self, value: int) -> None:
        self._model.max_cursors = int(value)
        self._touch()

    @property
    def label_width(self) -> int:
        return self._model.label_width

    @label_width.setter
    def label_width(self, value: int) -> None:
        self._model.label_width = int(value)
        self._touch()

    @property
    def row_height(self) -> int:
        return self._model.row_height

    @row_height.setter
    def row_height(self, value: int) -> None:
        self._model.row_height = int(value)
        self._touch()

    @property
    def row_gap(self) -> int:
        return self._model.row_gap

    @row_gap.setter
    def row_gap(self, value: int) -> None:
        self._model.row_gap = int(value)
        self._touch()

    @property
    def sti_row_h(self) -> int:
        return self._model.sti_row_h

    @sti_row_h.setter
    def sti_row_h(self, value: int) -> None:
        self._model.sti_row_h = int(value)
        self._touch()

    @property
    def sti_waveform_h(self) -> int:
        return self._model.sti_waveform_h

    @sti_waveform_h.setter
    def sti_waveform_h(self, value: int) -> None:
        self._model.sti_waveform_h = int(value)
        self._touch()

    @property
    def sti_line_style(self) -> str:
        return self._model.sti_line_style

    @sti_line_style.setter
    def sti_line_style(self, value: str) -> None:
        self._model.sti_line_style = str(value)
        self._touch()

    @property
    def timescale_per_px_default(self) -> float:
        return self._model.timescale_per_px_default

    @timescale_per_px_default.setter
    def timescale_per_px_default(self, value: float) -> None:
        self._model.timescale_per_px_default = float(value)
        self._touch()

    @property
    def hover_highlight(self) -> bool:
        return self._model.hover_highlight

    @hover_highlight.setter
    def hover_highlight(self, value: bool) -> None:
        self._model.hover_highlight = bool(value)
        self._touch()

    @property
    def cpu_load_row_h(self) -> int:
        return self._model.cpu_load_row_h

    @cpu_load_row_h.setter
    def cpu_load_row_h(self, value: int) -> None:
        self._model.cpu_load_row_h = int(value)
        self._touch()

    @property
    def colorblind(self) -> bool:
        return self._model.colorblind

    @colorblind.setter
    def colorblind(self, value: bool) -> None:
        self._model.colorblind = bool(value)
        self._touch()

    @property
    def horizontal(self) -> bool:
        return self._model.horizontal

    @horizontal.setter
    def horizontal(self, value: bool) -> None:
        self._model.horizontal = bool(value)
        self._touch()

    def load_theme_from_rc(self, rc: "_RcSettings") -> None:
        self.is_dark = rc.get("view", "theme", "dark") == "dark"

    def load_view_prefs_from_rc(self, rc: "_RcSettings") -> None:
        """Load persisted view preferences from btf_viewer.rc (not window geometry)."""
        m = self._model
        m.font_size = rc.get_int("view", "font_size", FONT_SIZE)
        m.ui_font_size = rc.get_int("view", "ui_font_size", UI_FONT_SIZE)
        m.max_cursors = rc.get_int("view", "max_cursors", _DEFAULT_MAX_CURSORS)
        m.label_width = max(60, min(rc.get_int("view", "label_width", LABEL_WIDTH), 600))
        m.row_height = rc.get_int("view", "row_height", ROW_HEIGHT)
        m.row_gap = rc.get_int("view", "row_gap", ROW_GAP)
        m.timescale_per_px_default = rc.get_float(
            "view", "timescale_per_px_default", _TIMESCALE_PER_PX_DEFAULT)
        m.show_cpu_load = rc.get_bool("view", "show_cpu_load", True)
        m.cpu_load_row_h = rc.get_int("view", "cpu_load_row_h", CPU_LOAD_ROW_H)
        bottom = rc.get_int("view", "cpu_splitter_bottom_h", 0)
        m.cpu_splitter_bottom_h = bottom if bottom > 0 else None
        m.cpu_splitter_user_sized = rc.get_bool("view", "cpu_splitter_user_sized", False)
        m.sti_row_h = rc.get_int("view", "sti_row_h", STI_ROW_H)
        m.sti_waveform_h = rc.get_int("view", "sti_waveform_h", STI_WAVEFORM_H)
        m.sti_line_style = rc.get("view", "sti_line_style", STI_LINE_STYLE)
        m.hover_highlight = rc.get_bool("view", "hover_highlight", _HOVER_HIGHLIGHT_ENABLED)
        m.horizontal = rc.get_bool("view", "horizontal", True)
        m.view_mode = rc.get("view", "view_mode", "task")
        m.colorblind = rc.get_bool("view", "colorblind_safe", False)
        self.settings_changed.emit()
        self.changed.emit()
