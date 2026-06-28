"""MVVM data models (no Qt widgets)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..parser import BtfTrace, TraceAnnotation, TraceBookmark

@dataclass
class TabViewportModel:
    fit_mode: bool = True
    zoom_tpp: float = -1.0
    cursors: List[int] = field(default_factory=list)
    filters: Dict[str, object] = field(default_factory=dict)

@dataclass
class PlotSessionState:
    mk: Optional[str] = None
    kind: Optional[str] = None
    preemptor: Optional[str] = None
    open: bool = False
    interval_id: Optional[str] = None

@dataclass
class StatsTabModel:
    cursor_times: List[int] = field(default_factory=list)
    scope_to_cursors: bool = True
    export_scope_override: Optional[Tuple[int, int]] = None
    section_collapsed: Dict[str, bool] = field(default_factory=dict)
    section_table_heights: Dict[str, int] = field(default_factory=dict)
    util_label_col_w: int = 0

@dataclass
class TraceTabModel:
    path: str = ""
    trace: Optional[BtfTrace] = None
    bookmarks: List[TraceBookmark] = field(default_factory=list)
    annotations: List[TraceAnnotation] = field(default_factory=list)
    mark_next_id: int = 1
    find_hits: List[int] = field(default_factory=list)
    find_hit_idx: int = -1
    find_marker_ns: Optional[int] = None
    find_query: str = ""
    find_mode: str = "Contains"
    undo_stack: list = field(default_factory=list)
    redo_stack: list = field(default_factory=list)
    plot: PlotSessionState = field(default_factory=PlotSessionState)
    stats: StatsTabModel = field(default_factory=StatsTabModel)
    viewport: TabViewportModel = field(default_factory=TabViewportModel)

@dataclass
class AppSettingsModel:
    view_mode: str = "task"
    is_dark: bool = True
    show_sti: bool = True
    show_grid: bool = True
    show_legend: bool = True
    show_stats: bool = True
    show_cpu_load: bool = True
    show_marks: bool = True
    show_find: bool = True
    cpu_splitter_user_sized: bool = False
    cpu_splitter_bottom_h: Optional[int] = None
    font_size: int = 0
    ui_font_size: int = 0
    max_cursors: int = 0
    label_width: int = 0
    row_height: int = 0
    row_gap: int = 0
    sti_row_h: int = 0
    sti_waveform_h: int = 0
    sti_line_style: str = ""
    timescale_per_px_default: float = 0.0
    hover_highlight: bool = False
    cpu_load_row_h: int = 0
    colorblind: bool = False
    horizontal: bool = True

@dataclass
class SessionModel:
    restore_queue: List[str] = field(default_factory=list)
    restore_active_idx: int = -1
    load_in_progress: bool = False
