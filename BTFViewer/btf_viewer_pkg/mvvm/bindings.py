"""MainWindow ↔ AppSettingsViewModel attribute mapping."""
from __future__ import annotations

# MainWindow legacy `_foo` attributes → AppSettingsViewModel property names.
SETTINGS_ATTR_MAP: dict[str, str] = {
    "_view_mode": "view_mode",
    "_is_dark": "is_dark",
    "_show_sti": "show_sti",
    "_show_grid": "show_grid",
    "_show_legend": "show_legend",
    "_show_stats": "show_stats",
    "_show_cpu_load": "show_cpu_load",
    "_show_marks": "show_marks",
    "_show_find": "show_find",
    "_cpu_splitter_user_sized": "cpu_splitter_user_sized",
    "_cpu_splitter_bottom_h": "cpu_splitter_bottom_h",
    "_font_size_val": "font_size",
    "_ui_font_size_val": "ui_font_size",
    "_max_cursors_val": "max_cursors",
    "_label_width_val": "label_width",
    "_row_height_val": "row_height",
    "_row_gap_val": "row_gap",
    "_sti_row_h_val": "sti_row_h",
    "_sti_waveform_h_val": "sti_waveform_h",
    "_sti_line_style_val": "sti_line_style",
    "_timescale_per_px_default_val": "timescale_per_px_default",
    "_hover_highlight_val": "hover_highlight",
    "_cpu_load_row_h_val": "cpu_load_row_h",
    "_colorblind_val": "colorblind",
    "_time_decimals_val": "time_decimals",
}

SESSION_ATTR_MAP: dict[str, str] = {
    "_session_restore_queue": "session_restore_queue",
    "_session_restore_active_idx": "session_restore_active_idx",
    "_load_in_progress": "load_in_progress",
}

class MvvmSettingsMixin:
    """Delegate legacy MainWindow settings/session fields to MainViewModel."""

    def __getattr__(self, name: str):
        key = SETTINGS_ATTR_MAP.get(name)
        if key is not None and "_vm" in self.__dict__:
            return getattr(self._vm.settings, key)
        key = SESSION_ATTR_MAP.get(name)
        if key is not None and "_vm" in self.__dict__:
            return getattr(self._vm, key)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        key = SETTINGS_ATTR_MAP.get(name)
        if key is not None and "_vm" in self.__dict__:
            setattr(self._vm.settings, key, value)
            return
        key = SESSION_ATTR_MAP.get(name)
        if key is not None and "_vm" in self.__dict__:
            setattr(self._vm, key, value)
            return
        super().__setattr__(name, value)
