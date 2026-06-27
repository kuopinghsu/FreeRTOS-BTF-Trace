"""MVVM base types."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

class ViewModelBase(QObject):
    """Base QObject for view-models."""

    changed = Signal()
