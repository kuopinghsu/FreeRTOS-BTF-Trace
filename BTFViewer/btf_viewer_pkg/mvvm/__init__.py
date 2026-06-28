"""MVVM layer for the desktop BTF viewer (PySide6).

Model      — dataclasses in models.py (trace, tab, stats, settings)
ViewModel  — QObject wrappers with change signals
View       — MainWindow, TimelineView, _StatsPanel, …

MainWindow mixes in MvvmSettingsMixin so legacy ``self._show_sti`` fields
delegate to ``MainViewModel.settings``.
"""
from __future__ import annotations

from .app_settings import AppSettingsViewModel
from .base import ViewModelBase
from .bindings import MvvmSettingsMixin, SESSION_ATTR_MAP, SETTINGS_ATTR_MAP
from .main_vm import MainViewModel
from .models import (
    AppSettingsModel,
    PlotSessionState,
    SessionModel,
    StatsTabModel,
    TraceTabModel,
)
from .stats_vm import StatsViewModel
from .trace_tab_vm import TraceTabViewModel
from .find_logic import recompute_find_hits

__all__ = [
    "AppSettingsModel",
    "AppSettingsViewModel",
    "MainViewModel",
    "MvvmSettingsMixin",
    "PlotSessionState",
    "SESSION_ATTR_MAP",
    "SETTINGS_ATTR_MAP",
    "SessionModel",
    "StatsTabModel",
    "StatsViewModel",
    "TraceTabModel",
    "TraceTabViewModel",
    "ViewModelBase",
    "recompute_find_hits",
]
